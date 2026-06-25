"""ai_collector_project 的最小 MCP Server。

v3.1 Phase 1 目标：先把 v3.0 已采集的 Boss 直聘岗位数据，
通过 MCP 暴露给 Claude Desktop / Cursor / Hermes 等客户端。

当前只实现 1 个工具：
- search_jobs(keyword, city="", top_k=5)

运行方式（stdio）：
    python src/mcp_server/ai_collector_mcp.py
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = PROJECT_ROOT / "data" / "collector.db"

mcp = FastMCP("ai-collector")


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


if __name__ == "__main__":
    mcp.run(transport="stdio")
