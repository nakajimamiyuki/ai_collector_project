"""MCP Server 的单元测试。

测试目标：
- 不碰真实 data/collector.db
- 不依赖真实 ollama / milvus
- 直接 monkeypatch DB_PATH 和向量检索函数到测试替身
- 验证 3 个 Tool（search_jobs / query_rag / get_skill_gap）的行为契约
"""
import json
import sqlite3

import pytest

from src.mcp_server import ai_collector_mcp as mcp_mod

pytestmark = pytest.mark.unit


# ======================================================================
# 共用：构造一份带 3 条 Boss 岗位的临时 SQLite
# ======================================================================
def _write_boss_row(conn, *, url, title, company, city, salary, desc, skills=None):
    payload = {
        "title": title,
        "summary": f"{title} summary",
        "key_points": ["point A", "point B"],
        "tags": ["AI", "Agent"],
        "_boss": {
            "brand_name": company,
            "city": city,
            "salary_desc": salary,
            "experience_name": "1-3年",
            "degree_name": "本科",
            "skills": skills or ["Python"],
            "post_description": desc,
            "boss_name": "张三",
            "boss_title": "HR",
            "address": f"{city}测试地址",
        },
    }
    conn.execute(
        "INSERT INTO final_results (url, source_type, structured_json, processed_at) "
        "VALUES (?, 'boss_zhipin', ?, '2026-06-25')",
        (url, json.dumps(payload, ensure_ascii=False)),
    )


def _make_temp_collector_db(tmp_path):
    db_path = tmp_path / "collector.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE final_results ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "url TEXT, "
        "source_type TEXT, "
        "structured_json TEXT, "
        "processed_at DATETIME)"
    )
    _write_boss_row(
        conn,
        url="https://example.com/job-1",
        title="AI Agent 开发工程师",
        company="杭州智能科技",
        city="杭州",
        salary="15-30K",
        desc="负责 MCP Tool-use Memory 多智能体协作。要求熟悉 LangGraph 与 RAG。",
        skills=["Python", "MCP", "LangGraph"],
    )
    _write_boss_row(
        conn,
        url="https://example.com/job-2",
        title="RAG 工程师",
        company="苏州知识库公司",
        city="苏州",
        salary="12-20K",
        desc="负责向量数据库和 LangChain 检索。熟悉 Milvus / Embedding。",
        skills=["RAG", "Milvus"],
    )
    _write_boss_row(
        conn,
        url="https://example.com/job-3",
        title="AI 后端开发",
        company="杭州后端科技",
        city="杭州",
        salary="10-15K",
        desc="负责 Python API 与 Agent 平台。需要 FastAPI 与 Docker 经验。",
        skills=["Python", "FastAPI"],
    )
    conn.commit()
    conn.close()
    return db_path


def _call_tool(tool, **kwargs):
    """FastMCP 包装后的函数在单测里可能暴露 fn；兼容直接函数和 FunctionTool。"""
    wrapped = getattr(tool, "fn", None)
    if wrapped is not None:
        return wrapped(**kwargs)
    return tool(**kwargs)


# ======================================================================
# Tool 1: search_jobs
# ======================================================================
def test_search_jobs_filters_by_keyword_and_city(tmp_path, monkeypatch):
    db_path = _make_temp_collector_db(tmp_path)
    monkeypatch.setattr(mcp_mod, "DB_PATH", db_path)

    data = json.loads(_call_tool(mcp_mod.search_jobs, keyword="MCP", city="杭州", top_k=5))

    assert data["query"] == {"keyword": "MCP", "city": "杭州", "top_k": 5}
    assert data["total_matched"] == 1
    assert data["returned"] == 1
    assert data["jobs"][0]["title"] == "AI Agent 开发工程师"
    assert data["jobs"][0]["company"] == "杭州智能科技"
    assert data["jobs"][0]["url"] == "https://example.com/job-1"


def test_search_jobs_caps_top_k_to_20_and_counts_all_matches(tmp_path, monkeypatch):
    db_path = _make_temp_collector_db(tmp_path)
    monkeypatch.setattr(mcp_mod, "DB_PATH", db_path)

    data = json.loads(_call_tool(mcp_mod.search_jobs, keyword="AI", city="", top_k=999))

    assert data["query"]["top_k"] == 20
    assert data["total_matched"] == 3
    assert data["returned"] == 3
    assert {job["city"] for job in data["jobs"]} == {"杭州", "苏州"}


def test_search_jobs_empty_keyword_lists_city_jobs(tmp_path, monkeypatch):
    db_path = _make_temp_collector_db(tmp_path)
    monkeypatch.setattr(mcp_mod, "DB_PATH", db_path)

    data = json.loads(_call_tool(mcp_mod.search_jobs, keyword="", city="杭州", top_k=1))

    assert data["total_matched"] == 2
    assert data["returned"] == 1
    # SQL 按 id DESC，所以后插入的杭州岗位先返回
    assert data["jobs"][0]["title"] == "AI 后端开发"


def test_search_jobs_missing_db_raises_clear_error(tmp_path, monkeypatch):
    monkeypatch.setattr(mcp_mod, "DB_PATH", tmp_path / "missing.db")

    with pytest.raises(FileNotFoundError, match="collector.db not found"):
        _call_tool(mcp_mod.search_jobs, keyword="MCP")


# ======================================================================
# Tool 2: query_rag
# ======================================================================
def _fake_records():
    """构造 2 条假 JobRecord 用于测试 query_rag。"""
    from src.agent.tools import JobRecord

    return [
        JobRecord(
            url="https://example.com/job-1",
            title="AI Agent 开发工程师",
            score=0.92,
            salary_desc="15-30K",
            salary_min=15000,
            salary_max=30000,
            city="杭州",
            experience="1-3年",
            degree="本科",
            brand="杭州智能科技",
            keyword_hit="MCP",
            skills=["Python", "MCP", "LangGraph"],
            job_labels=["Agent", "AI"],
            post_description="负责 MCP Tool-use 多智能体协作。",
            raw_structured={},
        ),
        JobRecord(
            url="https://example.com/job-2",
            title="RAG 工程师",
            score=0.81,
            salary_desc="12-20K",
            salary_min=12000,
            salary_max=20000,
            city="苏州",
            experience="1-3年",
            degree="本科",
            brand="苏州知识库公司",
            keyword_hit="RAG",
            skills=["RAG", "Milvus"],
            job_labels=["Embedding"],
            post_description="向量库 + LangChain 检索。",
            raw_structured={},
        ),
    ]


def test_query_rag_returns_hits_with_score(monkeypatch):
    fake = _fake_records()
    monkeypatch.setattr(
        "src.agent.tools.vector_search_jobs",
        lambda question, top_k=20: fake[:top_k],
    )

    data = json.loads(_call_tool(mcp_mod.query_rag, question="找 MCP 相关岗位", top_k=5))

    assert data["query"]["question"] == "找 MCP 相关岗位"
    assert data["query"]["top_k"] == 5
    assert data["returned"] == 2
    first = data["hits"][0]
    assert first["title"] == "AI Agent 开发工程师"
    assert first["score"] == 0.92
    assert first["company"] == "杭州智能科技"
    assert "short_desc" in first


def test_query_rag_caps_top_k(monkeypatch):
    fake = _fake_records()
    received_top_k = {}

    def spy(question, top_k=20):
        received_top_k["v"] = top_k
        return fake

    monkeypatch.setattr("src.agent.tools.vector_search_jobs", spy)

    data = json.loads(_call_tool(mcp_mod.query_rag, question="x", top_k=999))

    assert data["query"]["top_k"] == 20
    assert received_top_k["v"] == 20


def test_query_rag_empty_question_returns_error(monkeypatch):
    """不应该真的去调用向量检索，应该直接返回错误。"""
    called = {"v": False}

    def spy(question, top_k=20):
        called["v"] = True
        return []

    monkeypatch.setattr("src.agent.tools.vector_search_jobs", spy)

    data = json.loads(_call_tool(mcp_mod.query_rag, question="   ", top_k=5))

    assert "error" in data
    assert data["hits"] == []
    assert called["v"] is False


def test_query_rag_backend_failure_is_translated_to_json(monkeypatch):
    """ollama 没起 / milvus 没建库 → 不抛异常，返回带 hint 的错误 JSON。"""
    def boom(question, top_k=20):
        raise RuntimeError("ollama unreachable")

    monkeypatch.setattr("src.agent.tools.vector_search_jobs", boom)

    data = json.loads(_call_tool(mcp_mod.query_rag, question="测试", top_k=5))

    assert "error" in data
    assert "ollama unreachable" in data["error"]
    assert "hint" in data
    assert data["hits"] == []


# ======================================================================
# Tool 3: get_skill_gap
# ======================================================================
def test_get_skill_gap_basic_shape(tmp_path, monkeypatch):
    db_path = _make_temp_collector_db(tmp_path)
    monkeypatch.setattr(mcp_mod, "DB_PATH", db_path)

    # 替换 profile：已掌握 Python + LangChain，正在学 MCP
    monkeypatch.setattr(
        "src.agent.tools.load_profile",
        lambda: {
            "already_have": ["Python", "LangChain"],
            "learning": ["MCP", "LangGraph"],
        },
    )

    data = json.loads(_call_tool(mcp_mod.get_skill_gap, top_n=10))

    # 3 条岗位分析完
    assert data["total_jobs_analyzed"] == 3

    # market_top 至少要有 Python（3 条都提到）
    market_skills = {item["skill"] for item in data["market_top_skills"]}
    assert "Python" in market_skills

    # already_have_hits 应含 Python（市场要 + 我有）
    have_skills = {item["skill"] for item in data["already_have_hits"]}
    assert "Python" in have_skills

    # learning_hits 应含 MCP（market 上有，且我正在学）
    learning_skills = {item["skill"] for item in data["learning_hits"]}
    assert "MCP" in learning_skills

    # skill_gap 不能包含我已有的
    gap_skills = {item["skill"] for item in data["skill_gap"]}
    assert "Python" not in gap_skills
    assert "LangChain" not in gap_skills


def test_get_skill_gap_top_n_caps_at_30(tmp_path, monkeypatch):
    db_path = _make_temp_collector_db(tmp_path)
    monkeypatch.setattr(mcp_mod, "DB_PATH", db_path)
    monkeypatch.setattr(
        "src.agent.tools.load_profile",
        lambda: {"already_have": [], "learning": []},
    )

    data = json.loads(_call_tool(mcp_mod.get_skill_gap, top_n=999))

    # market_top_skills 受 top_n=30 控制，但实际命中可能不到 30
    assert len(data["market_top_skills"]) <= 30


def test_get_skill_gap_marks_learning_in_gap(tmp_path, monkeypatch):
    """正在学的技能也会进 skill_gap（因为还没掌握），但要带 is_learning 标记。"""
    db_path = _make_temp_collector_db(tmp_path)
    monkeypatch.setattr(mcp_mod, "DB_PATH", db_path)
    monkeypatch.setattr(
        "src.agent.tools.load_profile",
        lambda: {"already_have": [], "learning": ["MCP"]},
    )

    data = json.loads(_call_tool(mcp_mod.get_skill_gap, top_n=20))

    mcp_entries = [s for s in data["skill_gap"] if s["skill"] == "MCP"]
    assert len(mcp_entries) == 1
    assert mcp_entries[0]["is_learning"] is True
