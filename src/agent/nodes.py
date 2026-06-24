"""
LangGraph 节点定义。每个节点是一个**纯函数**：state -> partial state update。

设计原则
--------
- 节点只做"一件事"：parse / retrieve / filter / reflect / summarize
- 决策类节点（parse_intent / reflect / summarize）调 LLM
- 检索/过滤是确定性逻辑，不调 LLM —— 省 token 也省 latency
- 所有节点都在 state["trace"] 里追加一条记录，便于后续回放/调试
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from src.agent.prompts import (
    PARSE_INTENT_SYSTEM,
    PARSE_INTENT_USER_TEMPLATE,
    REFLECT_SYSTEM,
    SUMMARIZE_SYSTEM,
)
from src.agent.tools import (
    JobRecord,
    compute_skill_gap,
    filter_jobs,
    load_profile,
    vector_search_jobs,
)

logger = logging.getLogger(__name__)

# 最多反思重试次数（防止死循环）
MAX_RETRY_ROUNDS = 3


# ----------------------------------------------------------------------
# State：在节点间流动的全局上下文
# ----------------------------------------------------------------------
class AgentState(TypedDict, total=False):
    # 输入
    query: str
    profile: dict

    # parse_intent 节点产出
    intent: dict          # {keywords, cities_include/exclude, salary_min, ...}

    # retrieve / filter 节点产出
    raw_hits: list[JobRecord]
    filtered_jobs: list[JobRecord]
    filter_stats: dict

    # reflect 节点产出
    reflect_round: int    # 当前反思轮次
    decision: str         # "done" | "retry"
    tried_keywords: list[list[str]]  # 已经搜过哪几组关键词

    # summarize 节点产出
    skill_gap: list[tuple[str, int]]
    final_report: str

    # 追踪
    trace: list[str]


# ----------------------------------------------------------------------
# LLM 客户端（复用 .env 里的火山引擎 OpenAI 兼容配置）
# ----------------------------------------------------------------------
def _llm() -> ChatOpenAI:
    api_key = os.getenv("LLM_API_KEY")
    base_url = os.getenv("LLM_API_BASE")
    model = os.getenv("LLM_MODEL")
    if not all([api_key, base_url, model]):
        raise RuntimeError(
            "Missing LLM_API_KEY / LLM_API_BASE / LLM_MODEL in .env"
        )
    return ChatOpenAI(
        api_key=api_key,
        base_url=base_url,
        model=model,
        temperature=0.2,
        timeout=180,
        max_retries=2,
    )


def _extract_json(text: str) -> dict:
    """从 LLM 响应里提 JSON 对象，容忍 ```json``` 包裹和多余文字。"""
    # 1) 先剥代码块
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        candidate = m.group(1)
    else:
        # 2) 找第一个 { ... } 块
        m = re.search(r"\{.*\}", text, re.DOTALL)
        candidate = m.group(0) if m else text
    return json.loads(candidate)


def _trace(state: AgentState, msg: str) -> None:
    state.setdefault("trace", []).append(msg)
    logger.info(msg)


# ----------------------------------------------------------------------
# Node 1: parse_intent
# ----------------------------------------------------------------------
def parse_intent(state: AgentState) -> AgentState:
    query = state["query"]
    llm = _llm()
    msgs = [
        SystemMessage(content=PARSE_INTENT_SYSTEM),
        HumanMessage(content=PARSE_INTENT_USER_TEMPLATE.format(query=query)),
    ]
    resp = llm.invoke(msgs)
    raw = resp.content if isinstance(resp.content, str) else str(resp.content)
    try:
        intent = _extract_json(raw)
    except Exception as e:
        logger.warning(f"parse_intent 解析失败，使用兜底意图：{e}\n原始: {raw[:200]}")
        intent = {"keywords": [query], "direction": "未明确"}

    intent.setdefault("keywords", [query])
    state["intent"] = intent
    state["tried_keywords"] = []
    state["reflect_round"] = 0
    _trace(state, f"[parse_intent] 解析结果: {json.dumps(intent, ensure_ascii=False)}")
    return state


# ----------------------------------------------------------------------
# Node 2: retrieve（确定性，不调 LLM）
# ----------------------------------------------------------------------
def retrieve(state: AgentState) -> AgentState:
    intent = state["intent"]
    keywords = intent.get("keywords") or [state["query"]]
    # 把关键词拼成一句给 embedding，比逐个搜性价比高
    embed_query = " ".join(keywords)
    if intent.get("direction") and intent["direction"] != "未明确":
        embed_query += f" {intent['direction']}"
    if intent.get("salary_min"):
        embed_query += f" 薪资 {intent['salary_min'] // 1000}K+"
    if intent.get("experience"):
        embed_query += f" {intent['experience']}"

    hits = vector_search_jobs(embed_query, top_k=30)
    state["raw_hits"] = hits
    state["tried_keywords"].append(list(keywords))
    _trace(state, f"[retrieve] embed_query={embed_query!r} → {len(hits)} 条")
    return state


# ----------------------------------------------------------------------
# Node 3: filter（确定性，不调 LLM）
# ----------------------------------------------------------------------
def filter_node(state: AgentState) -> AgentState:
    intent = state["intent"]
    profile = state["profile"]

    cities_inc = intent.get("cities_include") or profile.get("target_cities") or None
    cities_exc = intent.get("cities_exclude") or None
    salary_min = intent.get("salary_min") or profile.get("salary_min") or None

    # 学历：尊重用户在 query 里明说的，否则用 profile
    degree = intent.get("degree")
    if degree and degree != "学历不限":
        degree_allow = [degree, "学历不限"]
    elif profile.get("degree"):
        # 用 profile 学历但宽松一点（你本科可以投本科/大专/学历不限）
        if profile["degree"] == "本科":
            degree_allow = ["本科", "大专", "学历不限"]
        else:
            degree_allow = [profile["degree"], "学历不限"]
    else:
        degree_allow = None

    # 经验：意图里有就用意图的，否则按 profile 年限映射
    exp = intent.get("experience")
    if exp:
        experience_allow = [exp, "经验不限"]
    elif profile.get("years_of_experience"):
        y = profile["years_of_experience"]
        if y <= 1:
            experience_allow = ["在校/应届", "经验不限", "1-3年"]
        elif y <= 3:
            experience_allow = ["1-3年", "经验不限"]
        else:
            experience_allow = ["3-5年", "1-3年", "经验不限"]
    else:
        experience_allow = None

    blacklist = profile.get("want_to_avoid") or []

    kept, stats = filter_jobs(
        state["raw_hits"],
        salary_min=salary_min,
        cities_include=cities_inc,
        cities_exclude=cities_exc,
        degree_allow=degree_allow,
        experience_allow=experience_allow,
        blacklist_keywords=blacklist,
    )
    state["filtered_jobs"] = kept
    state["filter_stats"] = stats
    _trace(
        state,
        f"[filter] {stats['input']} → {stats['kept']}（薪资 -{stats['by_salary']} / "
        f"城市 -{stats['by_city_include'] + stats['by_city_exclude']} / "
        f"学历 -{stats['by_degree']} / 经验 -{stats['by_experience']} / "
        f"黑名单 -{stats['by_blacklist']}）"
    )
    return state


# ----------------------------------------------------------------------
# Node 4: reflect（决策是否需要换关键词再搜）
# ----------------------------------------------------------------------
def reflect(state: AgentState) -> AgentState:
    state["reflect_round"] = state.get("reflect_round", 0) + 1
    kept = state["filtered_jobs"]

    # 简单兜底：足够 ≥ 5 条或重试 ≥ 3 轮，直接 done
    if len(kept) >= 5 or state["reflect_round"] >= MAX_RETRY_ROUNDS:
        state["decision"] = "done"
        _trace(state, f"[reflect] decision=done（kept={len(kept)} / round={state['reflect_round']}）")
        return state

    # 否则调 LLM 决策：要不要换关键词
    intent = state["intent"]
    profile = state["profile"]
    summary = "\n".join(
        f"- [{j.city}] {j.title} | {j.salary_desc} | {j.experience} {j.degree}"
        for j in kept[:10]
    ) or "（空）"

    user = (
        f"用户原始需求: {state['query']}\n"
        f"已解析意图: {json.dumps(intent, ensure_ascii=False)}\n"
        f"画像主投方向: {profile.get('primary_directions')}\n"
        f"画像保底方向: {profile.get('fallback_directions')}\n"
        f"已尝试过的关键词组: {state['tried_keywords']}\n"
        f"当前已通过过滤的岗位（{len(kept)} 条）:\n{summary}\n\n"
        f"是否需要再搜一轮？"
    )

    llm = _llm()
    msgs = [SystemMessage(content=REFLECT_SYSTEM), HumanMessage(content=user)]
    resp = llm.invoke(msgs)
    raw = resp.content if isinstance(resp.content, str) else str(resp.content)
    try:
        result = _extract_json(raw)
    except Exception:
        logger.warning(f"reflect 解析失败，强制 done。原始: {raw[:200]}")
        result = {"decision": "done"}

    if result.get("decision") == "retry":
        next_kw_raw = result.get("next_keywords") or []
        # 强壮化：LLM 偶尔会把 next_keywords 返回成嵌套结构（[["xxx"]]）或
        # 单字符串而不是 list；统一拍平成 str 列表，不可哈希的直接跳过。
        next_kw: list[str] = []
        if isinstance(next_kw_raw, str):
            next_kw = [next_kw_raw]
        elif isinstance(next_kw_raw, list):
            for item in next_kw_raw:
                if isinstance(item, str):
                    next_kw.append(item)
                elif isinstance(item, list):
                    # 嵌套 → 拍平一层
                    next_kw.extend(s for s in item if isinstance(s, str))
                # 其它非字符串/列表的类型（dict / None）直接忽略

        # 至少要换出一个新关键词，否则强制 done 防死循环
        already_tried: set[str] = set()
        for trial in state["tried_keywords"]:
            for kw in trial:
                if isinstance(kw, str):
                    already_tried.add(kw)
        new_kw = [k for k in next_kw if k not in already_tried]
        if not new_kw:
            state["decision"] = "done"
            _trace(state, "[reflect] LLM 想 retry 但没给出新关键词 → 强制 done")
        else:
            state["intent"]["keywords"] = new_kw
            if result.get("next_cities"):
                state["intent"]["cities_include"] = result["next_cities"]
            state["decision"] = "retry"
            _trace(state, f"[reflect] retry: 新关键词={new_kw} 理由={result.get('reason', '')}")
    else:
        state["decision"] = "done"
        _trace(state, f"[reflect] decision=done 理由={result.get('reason', '')}")
    return state


def route_after_reflect(state: AgentState) -> str:
    return "retrieve" if state["decision"] == "retry" else "summarize"


# ----------------------------------------------------------------------
# Node 5: summarize
# ----------------------------------------------------------------------
def summarize(state: AgentState) -> AgentState:
    jobs = state["filtered_jobs"]
    profile = state["profile"]

    # 先算技能差距（确定性，不调 LLM）
    gap = compute_skill_gap(jobs, profile)
    state["skill_gap"] = gap

    # 按 score 排序，最多给 LLM 看前 10 条（控制 prompt 长度）
    jobs_sorted = sorted(jobs, key=lambda j: j.score, reverse=True)
    show = jobs_sorted[:10]

    # 把每个岗位拍成紧凑结构，给 LLM 当输入
    jobs_payload = [
        {
            "city": j.city,
            "title": j.title,
            "brand": j.brand,
            "salary": j.salary_desc,
            "experience": j.experience,
            "degree": j.degree,
            "url": j.url,
            "score": round(j.score, 3),
            "jd_excerpt": j.short_desc,
        }
        for j in show
    ]

    user = (
        f"# 用户原始需求\n{state['query']}\n\n"
        f"# 用户画像\n{json.dumps(profile, ensure_ascii=False, indent=2)}\n\n"
        f"# 已通过过滤的岗位（按相似度降序，共 {len(jobs)} 条，展示前 {len(show)} 条）\n"
        f"{json.dumps(jobs_payload, ensure_ascii=False, indent=2)}\n\n"
        f"# 技能差距统计（这批岗位反复出现但用户 profile 还没掌握的技能）\n"
        f"{json.dumps(gap[:10], ensure_ascii=False)}\n"
    )

    llm = _llm()
    msgs = [SystemMessage(content=SUMMARIZE_SYSTEM), HumanMessage(content=user)]
    resp = llm.invoke(msgs)
    state["final_report"] = (
        resp.content if isinstance(resp.content, str) else str(resp.content)
    )
    _trace(state, f"[summarize] 报告生成完毕，{len(state['final_report'])} 字")
    return state
