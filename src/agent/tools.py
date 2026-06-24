"""
Agent 用到的工具：RAG 检索 + 硬过滤 + Profile 加载。

设计目的
--------
把 v2.1 RAG 层和 v3.0 Boss 数据，封装成 LangGraph 节点能直接调用的纯函数。
工具自己不做决策，决策交给 graph.py 里的节点。
"""
from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SQLITE_PATH = PROJECT_ROOT / "data" / "collector.db"
VECTOR_DB_PATH = PROJECT_ROOT / "data" / "vector.db"
PROFILE_PATH = Path(__file__).parent / "my_profile.yaml"


# ----------------------------------------------------------------------
# 数据类
# ----------------------------------------------------------------------
@dataclass
class JobRecord:
    """从 SQLite 拼装的岗位完整记录（向量召回 + 详情合并）。"""

    url: str
    title: str
    score: float                        # 向量相似度
    salary_desc: str
    salary_min: int                     # 解析后的下限（元/月）
    salary_max: int                     # 解析后的上限
    city: str
    experience: str                     # 1-3年 / 经验不限 ...
    degree: str                         # 本科 / 大专 ...
    brand: str                          # 公司名
    keyword_hit: str                    # 命中的搜索关键词
    skills: list[str] = field(default_factory=list)
    job_labels: list[str] = field(default_factory=list)
    post_description: str = ""
    raw_structured: dict = field(default_factory=dict)

    @property
    def short_desc(self) -> str:
        """JD 正文摘要（前 120 字，去掉多余空白）。"""
        s = re.sub(r"\s+", " ", self.post_description)
        return s[:120]


# ----------------------------------------------------------------------
# Profile
# ----------------------------------------------------------------------
def load_profile() -> dict:
    """加载 my_profile.yaml；不存在则返回空字典。"""
    if not PROFILE_PATH.exists():
        return {}
    with open(PROFILE_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


# ----------------------------------------------------------------------
# 工具 1：向量检索 + 详情合并
# ----------------------------------------------------------------------
def vector_search_jobs(
    query_text: str,
    top_k: int = 20,
) -> list[JobRecord]:
    """语义检索 Boss 岗位，返回完整 JobRecord（自动 join SQLite 拿详情）。"""
    # 延迟 import：让 tools 模块本身能在没装 ollama 时也能被静态分析
    from src.rag.embedder import OllamaEmbedder
    from src.rag.vector_store import VectorStore

    embedder = OllamaEmbedder()
    store = VectorStore(db_path=str(VECTOR_DB_PATH))

    query_vec = embedder.embed_one(query_text)
    hits = store.search(query_vec, top_k=top_k, source_type="boss_zhipin")

    if not hits:
        return []

    # 一次性把所有命中的 structured_json 从 SQLite 读出
    urls = [h.url for h in hits]
    placeholders = ",".join("?" for _ in urls)
    conn = sqlite3.connect(SQLITE_PATH)
    rows = conn.execute(
        f"SELECT url, structured_json FROM final_results "
        f"WHERE source_type='boss_zhipin' AND url IN ({placeholders})",
        urls,
    ).fetchall()
    conn.close()

    by_url = {url: sj for url, sj in rows}

    records: list[JobRecord] = []
    for hit in hits:
        sj_raw = by_url.get(hit.url)
        if not sj_raw:
            continue
        try:
            structured = json.loads(sj_raw)
        except json.JSONDecodeError:
            continue
        records.append(_build_record(hit.url, hit.score, hit.title, structured))
    return records


def _build_record(url: str, score: float, title: str, structured: dict) -> JobRecord:
    """把 SQLite 里的 structured_json 拍平成 JobRecord。"""
    b = structured.get("_boss", {}) or {}
    salary_desc = b.get("salary_desc", "")
    sal_min, sal_max = _parse_salary(salary_desc)

    return JobRecord(
        url=url,
        title=structured.get("title") or title or "(无标题)",
        score=score,
        salary_desc=salary_desc,
        salary_min=sal_min,
        salary_max=sal_max,
        city=b.get("city", "") or "",
        experience=b.get("experience_name", "") or "",
        degree=b.get("degree_name", "") or "",
        brand=b.get("brand_name", "") or "",
        keyword_hit=b.get("keyword", "") or "",
        skills=list(b.get("skills") or []) + list(b.get("detail_labels") or []),
        job_labels=list(structured.get("key_points") or []),
        post_description=b.get("post_description", "") or "",
        raw_structured=structured,
    )


# ----------------------------------------------------------------------
# 工具 2：硬过滤（薪资 / 城市 / 学历 / 经验 / 黑名单）
# ----------------------------------------------------------------------
def filter_jobs(
    jobs: list[JobRecord],
    *,
    salary_min: int | None = None,
    cities_include: list[str] | None = None,
    cities_exclude: list[str] | None = None,
    degree_allow: list[str] | None = None,
    experience_allow: list[str] | None = None,
    blacklist_keywords: list[str] | None = None,
) -> tuple[list[JobRecord], dict]:
    """
    返回 (通过过滤的岗位, 每条规则的拦截统计)。

    所有规则**遇到字段为空时放行**，避免误杀。
    """
    counts = {
        "input": len(jobs),
        "by_salary": 0,
        "by_city_include": 0,
        "by_city_exclude": 0,
        "by_degree": 0,
        "by_experience": 0,
        "by_blacklist": 0,
        "kept": 0,
    }

    kept: list[JobRecord] = []
    for j in jobs:
        # 薪资：用 salary_max（"5-10K" 时下限不达但上限达就算）
        if salary_min and j.salary_max and j.salary_max < salary_min:
            counts["by_salary"] += 1
            continue
        # 城市：明确包含的优先
        if cities_include and j.city and j.city not in cities_include:
            counts["by_city_include"] += 1
            continue
        if cities_exclude and j.city and j.city in cities_exclude:
            counts["by_city_exclude"] += 1
            continue
        # 学历：允许的列表（"学历不限"始终通过）
        if degree_allow and j.degree and j.degree not in degree_allow and j.degree != "学历不限":
            counts["by_degree"] += 1
            continue
        # 经验：允许的列表（"经验不限"始终通过）
        if (
            experience_allow
            and j.experience
            and j.experience not in experience_allow
            and j.experience != "经验不限"
        ):
            counts["by_experience"] += 1
            continue
        # 黑名单词：title 或 JD 命中即拒
        if blacklist_keywords:
            blob = f"{j.title} {j.post_description}".lower()
            if any(bw.lower() in blob for bw in blacklist_keywords):
                counts["by_blacklist"] += 1
                continue
        kept.append(j)

    counts["kept"] = len(kept)
    return kept, counts


# ----------------------------------------------------------------------
# 工具 3：技能差距统计
# ----------------------------------------------------------------------
def compute_skill_gap(
    jobs: list[JobRecord],
    profile: dict,
) -> list[tuple[str, int]]:
    """
    在这批岗位里，列出**反复出现但 profile.already_have 里没有**的技能词。

    返回 [(skill, hit_count), ...]，按 hit_count 降序。
    """
    have = {s.lower() for s in (profile.get("already_have") or [])}
    learning = {s.lower() for s in (profile.get("learning") or [])}

    # 简单技能词典（出现在 JD 正文里就算命中一次）
    # 故意不动态分词，求"高准确率 + 简单可解释"
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

    counter: dict[str, int] = {}
    for j in jobs:
        blob = f"{j.title} {j.post_description}".lower()
        for s in skill_dict:
            if s.lower() in blob:
                counter[s] = counter.get(s, 0) + 1

    gap: list[tuple[str, int]] = []
    for skill, n in counter.items():
        if skill.lower() in have:
            continue
        # 把 learning 中的技能加个标记（caller 决定怎么用）
        gap.append((skill, n))

    gap.sort(key=lambda x: x[1], reverse=True)
    return gap


# ----------------------------------------------------------------------
# 工具 4：薪资字符串解析
# ----------------------------------------------------------------------
_SALARY_K = re.compile(r"(\d+(?:\.\d+)?)\s*[-~]\s*(\d+(?:\.\d+)?)\s*K", re.IGNORECASE)
_SALARY_K_SINGLE = re.compile(r"(\d+(?:\.\d+)?)\s*K", re.IGNORECASE)
_SALARY_DAILY = re.compile(r"(\d+)\s*[-~]?\s*(\d+)?\s*元\s*/\s*天")


def _parse_salary(desc: str) -> tuple[int, int]:
    """
    把 "15-25K" / "20K·14薪" / "280-400元/天" 解析成 (月薪下限, 月薪上限)，单位元。

    返回 (0, 0) 表示无法解析。
    """
    if not desc:
        return 0, 0

    m = _SALARY_K.search(desc)
    if m:
        lo = int(float(m.group(1)) * 1000)
        hi = int(float(m.group(2)) * 1000)
        return lo, hi

    m = _SALARY_K_SINGLE.search(desc)
    if m:
        v = int(float(m.group(1)) * 1000)
        return v, v

    m = _SALARY_DAILY.search(desc)
    if m:
        # 按 22 天/月折算
        lo = int(m.group(1)) * 22
        hi = int(m.group(2)) * 22 if m.group(2) else lo
        return lo, hi

    return 0, 0
