"""MCP Server 的单元测试。

测试目标：
- 不碰真实 data/collector.db
- 直接 monkeypatch DB_PATH 到临时 SQLite
- 验证 search_jobs 的过滤、top_k 限制和 JSON 结构
"""
import json
import sqlite3

import pytest

from src.mcp_server import ai_collector_mcp as mcp_mod

pytestmark = pytest.mark.unit


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
        desc="负责 MCP Tool-use Memory 多智能体协作。",
        skills=["Python", "MCP", "LangGraph"],
    )
    _write_boss_row(
        conn,
        url="https://example.com/job-2",
        title="RAG 工程师",
        company="苏州知识库公司",
        city="苏州",
        salary="12-20K",
        desc="负责向量数据库和 LangChain 检索。",
        skills=["RAG", "Milvus"],
    )
    _write_boss_row(
        conn,
        url="https://example.com/job-3",
        title="AI 后端开发",
        company="杭州后端科技",
        city="杭州",
        salary="10-15K",
        desc="负责 Python API 与 Agent 平台。",
        skills=["Python", "FastAPI"],
    )
    conn.commit()
    conn.close()
    return db_path


def _call_search_jobs(**kwargs):
    """FastMCP 包装后的函数在单测里可能暴露 fn；兼容直接函数和 FunctionTool。"""
    tool = mcp_mod.search_jobs
    wrapped = getattr(tool, "fn", None)
    if wrapped is not None:
        return wrapped(**kwargs)
    return tool(**kwargs)


def test_search_jobs_filters_by_keyword_and_city(tmp_path, monkeypatch):
    db_path = _make_temp_collector_db(tmp_path)
    monkeypatch.setattr(mcp_mod, "DB_PATH", db_path)

    data = json.loads(_call_search_jobs(keyword="MCP", city="杭州", top_k=5))

    assert data["query"] == {"keyword": "MCP", "city": "杭州", "top_k": 5}
    assert data["total_matched"] == 1
    assert data["returned"] == 1
    assert data["jobs"][0]["title"] == "AI Agent 开发工程师"
    assert data["jobs"][0]["company"] == "杭州智能科技"
    assert data["jobs"][0]["url"] == "https://example.com/job-1"


def test_search_jobs_caps_top_k_to_20_and_counts_all_matches(tmp_path, monkeypatch):
    db_path = _make_temp_collector_db(tmp_path)
    monkeypatch.setattr(mcp_mod, "DB_PATH", db_path)

    data = json.loads(_call_search_jobs(keyword="AI", city="", top_k=999))

    assert data["query"]["top_k"] == 20
    assert data["total_matched"] == 3
    assert data["returned"] == 3
    assert {job["city"] for job in data["jobs"]} == {"杭州", "苏州"}


def test_search_jobs_empty_keyword_lists_city_jobs(tmp_path, monkeypatch):
    db_path = _make_temp_collector_db(tmp_path)
    monkeypatch.setattr(mcp_mod, "DB_PATH", db_path)

    data = json.loads(_call_search_jobs(keyword="", city="杭州", top_k=1))

    assert data["total_matched"] == 2
    assert data["returned"] == 1
    # SQL 按 id DESC，所以后插入的杭州岗位先返回
    assert data["jobs"][0]["title"] == "AI 后端开发"


def test_search_jobs_missing_db_raises_clear_error(tmp_path, monkeypatch):
    monkeypatch.setattr(mcp_mod, "DB_PATH", tmp_path / "missing.db")

    with pytest.raises(FileNotFoundError, match="collector.db not found"):
        _call_search_jobs(keyword="MCP")
