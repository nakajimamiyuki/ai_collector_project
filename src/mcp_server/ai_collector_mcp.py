"""ai_collector_project 的 MCP Server。

v3.1 Phase 1 目标：把 v3.0 的核心检索能力暴露给 MCP 客户端
（Claude Desktop / Cursor / Hermes Agent 等）。

当前暴露 3 个工具：
- search_jobs(keyword, city, top_k)        关键词匹配（标题/公司/JD/技能）
- query_rag(question, top_k)               bge-m3 语义检索（Milvus + Ollama）
- get_skill_gap(top_n)                     市场技能热度 + 个人画像缺口对照

运行方式（stdio）：
    python src/mcp_server/ai_collector_mcp.py
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any

# macOS 上 milvus-lite/faiss + ollama 在同一进程会触发 OpenMP 双库初始化 abort
# （OMP: Error #15: Initializing libomp.dylib, but found libomp.dylib already initialized）。
# 必须在任何 import faiss/milvus 之前设这个环境变量。
# 这里在模块顶部就设，覆盖所有后续延迟 import 的场景（query_rag 走 milvus）。
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

# 把项目根加入 sys.path —— 子进程以脚本方式启动时（python src/mcp_server/...py），
# 默认 sys.path 只有脚本所在目录，找不到顶层的 `src` 包；
# 这里手动注入项目根，保证 `from src.agent.tools import ...` 能跑。
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from mcp.server.fastmcp import FastMCP

DB_PATH = PROJECT_ROOT / "data" / "collector.db"

mcp = FastMCP("ai-collector")


# ======================================================================
# 共用：SQLite 读取
# ======================================================================
def _load_boss_rows() -> list[dict[str, Any]]:
    """从 SQLite 读取 Boss 直聘结构化结果。"""
    if not DB_PATH.exists():
        raise FileNotFoundError(f"collector.db not found: {DB_PATH}")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT id, url, structured_json, processed_at "
            "FROM final_results "
            "WHERE source_type = 'boss_zhipin' "
            "ORDER BY id DESC"
        ).fetchall()
    finally:
        conn.close()

    results: list[dict[str, Any]] = []
    for row in rows:
        try:
            structured = json.loads(row["structured_json"] or "{}")
        except json.JSONDecodeError:
            continue

        boss = structured.get("_boss") or {}
        results.append(
            {
                "id": row["id"],
                "url": row["url"],
                "processed_at": row["processed_at"],
                "title": structured.get("title") or "",
                "summary": structured.get("summary") or "",
                "key_points": structured.get("key_points") or [],
                "tags": structured.get("tags") or [],
                "company": boss.get("brand_name") or boss.get("company_name") or "",
                "city": boss.get("city") or "",
                "salary": boss.get("salary_desc") or "",
                "experience": boss.get("experience_name") or "",
                "degree": boss.get("degree_name") or "",
                "skills": boss.get("skills") or [],
                "description": boss.get("post_description") or "",
                "boss_name": boss.get("boss_name") or "",
                "boss_title": boss.get("boss_title") or "",
                "address": boss.get("address") or "",
            }
        )
    return results


def _contains(text: str, keyword: str) -> bool:
    """大小写不敏感的包含判断；空 keyword 视为匹配。"""
    if not keyword:
        return True
    return keyword.lower() in text.lower()


# ======================================================================
# Tool 1: search_jobs —— 关键词匹配
# ======================================================================
@mcp.tool()
def search_jobs(keyword: str, city: str = "", top_k: int = 5) -> str:
    """搜索已采集的 Boss 直聘岗位。

    Args:
        keyword: 搜索关键词，例如 "LangChain"、"MCP"、"AI Agent"。
                 会同时匹配标题、公司、技能、摘要和 JD 正文。
        city: 城市过滤，例如 "杭州"、"苏州"。空字符串表示不过滤城市。
        top_k: 返回数量，默认 5，最大 20。

    Returns:
        JSON 字符串，包含匹配岗位列表和总匹配数。
    """
    top_k = max(1, min(int(top_k), 20))
    keyword = (keyword or "").strip()
    city = (city or "").strip()

    matches: list[dict[str, Any]] = []
    total_matched = 0

    for job in _load_boss_rows():
        if city and job["city"] != city:
            continue

        haystack = "\n".join(
            [
                job["title"],
                job["company"],
                job["summary"],
                job["description"],
                " ".join(str(s) for s in job["skills"]),
                " ".join(str(t) for t in job["tags"]),
            ]
        )
        if not _contains(haystack, keyword):
            continue

        total_matched += 1
        if len(matches) >= top_k:
            continue

        matches.append(
            {
                "id": job["id"],
                "title": job["title"],
                "company": job["company"],
                "city": job["city"],
                "salary": job["salary"],
                "experience": job["experience"],
                "degree": job["degree"],
                "skills": job["skills"],
                "summary": job["summary"],
                "url": job["url"],
            }
        )

    payload = {
        "query": {"keyword": keyword, "city": city, "top_k": top_k},
        "total_matched": total_matched,
        "returned": len(matches),
        "jobs": matches,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


# ======================================================================
# Tool 2: query_rag —— bge-m3 语义检索
# ======================================================================
@mcp.tool()
def query_rag(question: str, top_k: int = 5) -> str:
    """用自然语言对 Boss 直聘岗位做向量检索（bge-m3 + Milvus Lite）。

    跟 search_jobs 的区别：
    - search_jobs 是字面包含匹配（要求 keyword 真的出现在 JD 里）
    - query_rag 是语义匹配，比如问"会用 LangGraph 做反思决策的岗位"
      也能召回写了"Agent 工作流编排"的 JD

    依赖本地 ollama 服务（运行 bge-m3:latest 模型）和已建好的
    data/vector.db Milvus Lite 向量库。

    Args:
        question: 自然语言查询，例如 "找会用 RAG + LangGraph 的中高级岗位"。
        top_k: 返回数量，默认 5，最大 20。

    Returns:
        JSON 字符串，每条岗位包含 url / title / score（0-1 余弦相似度）
        和完整的结构化字段。
    """
    # 延迟 import：让没装 ollama / milvus 的环境也能 import 本模块
    from src.agent.tools import vector_search_jobs

    top_k = max(1, min(int(top_k), 20))
    question = (question or "").strip()
    if not question:
        return json.dumps(
            {
                "query": {"question": question, "top_k": top_k},
                "error": "question 不能为空",
                "hits": [],
            },
            ensure_ascii=False,
            indent=2,
        )

    try:
        records = vector_search_jobs(question, top_k=top_k)
    except Exception as e:
        # 把基础设施故障（ollama 没起 / vector.db 不存在）翻译成 JSON 错误
        # 而不是抛异常，让 MCP 客户端能直接拿到可读信息
        return json.dumps(
            {
                "query": {"question": question, "top_k": top_k},
                "error": f"向量检索失败：{type(e).__name__}: {e}",
                "hint": "确认 ollama 在运行（ollama serve），bge-m3 已 pull，"
                        "且执行过 scripts/index_final_results.py 建好向量库。",
                "hits": [],
            },
            ensure_ascii=False,
            indent=2,
        )

    hits = [
        {
            "url": r.url,
            "title": r.title,
            "score": round(r.score, 4),
            "company": r.brand,
            "city": r.city,
            "salary": r.salary_desc,
            "experience": r.experience,
            "degree": r.degree,
            "skills": r.skills,
            "short_desc": r.short_desc,
        }
        for r in records
    ]

    payload = {
        "query": {"question": question, "top_k": top_k},
        "returned": len(hits),
        "hits": hits,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


# ======================================================================
# Tool 3: get_skill_gap —— 市场技能热度 + 我的画像缺口
# ======================================================================
@mcp.tool()
def get_skill_gap(top_n: int = 10) -> str:
    """在已采集的 Boss 岗位里聚合技能热度，对照 my_profile.yaml 算缺口。

    用途：让客户端（Hermes / Claude）一句话知道"我现在该补哪些技能"。

    返回字段：
    - market_top_skills      市场上出现次数最多的技能 Top N（含我已具备的）
    - skill_gap              我未掌握、但市场高频出现的技能（按命中次数降序）
    - already_have_hits      我已具备且市场上确实在要的技能（验证我没学偏）
    - learning_hits          我正在学的技能在市场上的热度（验证学习方向）
    - total_jobs_analyzed    本次统计基于多少条岗位

    Args:
        top_n: 各列表的截断长度，默认 10，最大 30。

    Returns:
        JSON 字符串。
    """
    # 延迟 import，复用 v3.0 Agent 工具
    from src.agent.tools import (
        JobRecord,
        _build_record,
        compute_skill_gap,
        load_profile,
    )

    top_n = max(1, min(int(top_n), 30))

    # 加载画像
    profile = load_profile()
    already_have_set = {s.lower() for s in (profile.get("already_have") or [])}
    learning_set = {s.lower() for s in (profile.get("learning") or [])}

    # 把 SQLite 里全部 boss_zhipin 岗位拍成 JobRecord
    rows = _load_boss_rows()
    records: list[JobRecord] = []
    for row in rows:
        try:
            conn = sqlite3.connect(DB_PATH)
            try:
                full = conn.execute(
                    "SELECT structured_json FROM final_results WHERE id = ?",
                    (row["id"],),
                ).fetchone()
            finally:
                conn.close()
            if not full:
                continue
            structured = json.loads(full[0] or "{}")
        except (json.JSONDecodeError, sqlite3.Error):
            continue
        records.append(
            _build_record(
                url=row["url"],
                score=0.0,
                title=row["title"],
                structured=structured,
            )
        )

    # 缺口：profile 未掌握、但 JD 反复出现的技能
    gap = compute_skill_gap(records, profile)[:top_n]

    # 市场总热度（不区分 have/learning），重新算一次便于客户端横向看
    # 用 compute_skill_gap 内部的 skill_dict 太麻烦，这里就地复刻一份最小版本
    skill_dict = [
        "LangChain", "LangGraph", "LlamaIndex", "RAG", "Milvus", "Qdrant",
        "Pinecone", "Chroma", "Weaviate", "FAISS", "Embedding",
        "Agent", "MCP", "Coze", "Dify", "AutoGen", "CrewAI",
        "Prompt", "Function Calling", "Tool Use", "ReAct",
        "GPT", "Claude", "Gemini", "GLM", "Qwen", "Llama",
        "Ollama", "vLLM", "LMDeploy", "TGI",
        "LoRA", "QLoRA", "RLHF", "DPO", "GRPO", "SFT", "Fine-tuning", "微调",
        "PyTorch", "TensorFlow", "Transformers",
        "Docker", "Kubernetes", "K8s",
        "FastAPI", "Flask", "Django",
        "Python", "Java", "Go", "Rust", "C++", "JavaScript", "TypeScript",
        "React", "Vue",
        "PostgreSQL", "MySQL", "MongoDB", "Redis", "Elasticsearch",
        "AWS", "Azure", "阿里云", "腾讯云",
        "Selenium", "Pytest", "Playwright",
        "Spring", "Mybatis",
        "OpenCV", "SLAM", "ROS",
        "AIGC", "多模态", "OCR", "ASR", "TTS",
        "知识图谱", "Neo4j", "向量数据库",
    ]

    market_counter: dict[str, int] = {}
    for j in records:
        blob = f"{j.title} {j.post_description}".lower()
        for s in skill_dict:
            if s.lower() in blob:
                market_counter[s] = market_counter.get(s, 0) + 1
    market_top = sorted(
        market_counter.items(), key=lambda x: x[1], reverse=True
    )[:top_n]

    already_have_hits = [
        {"skill": s, "hits": n}
        for s, n in market_top  # 仅展示进 top N 的
        if s.lower() in already_have_set
    ]
    learning_hits = [
        {"skill": s, "hits": n}
        for s, n in sorted(market_counter.items(), key=lambda x: x[1], reverse=True)
        if s.lower() in learning_set
    ][:top_n]

    payload = {
        "total_jobs_analyzed": len(records),
        "market_top_skills": [
            {"skill": s, "hits": n} for s, n in market_top
        ],
        "skill_gap": [
            {"skill": s, "hits": n, "is_learning": s.lower() in learning_set}
            for s, n in gap
        ],
        "already_have_hits": already_have_hits,
        "learning_hits": learning_hits,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    mcp.run(transport="stdio")
