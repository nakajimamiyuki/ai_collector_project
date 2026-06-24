"""
P3：把 BossSource 抓到的岗位入库到 final_results。

为什么不走完整流水线（监控 → 采集 → 清洗）？
- Boss 搜索 API 本身就返回结构化数据（jobName/salaryDesc/skills/jobLabels/boss）
- 不需要再爬一遍 HTML，也不需要 LLM 清洗
- 把数据按 v2.1 的 structured_json 契约 shim 一下，直接落库

落库后：
- scripts/index_final_results.py  → 索引到向量库（零修改）
- scripts/search.py               → 自然语言查询（零修改）

用法：
    python scripts/ingest_boss_jobs.py
    python scripts/ingest_boss_jobs.py --cities 杭州,苏州 --keywords AI应用开发
    python scripts/ingest_boss_jobs.py --pages 2     # 每个查询抓 2 页
"""
import os

# macOS OpenMP 双库冲突 escape hatch（必须在 import numpy/faiss/milvus 前设置）
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.db_manager import DBManager
from src.sources.boss_zhipin import BossSource, BossJob

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


DEFAULT_CITIES = ["杭州", "苏州", "济南", "青岛", "郑州"]
DEFAULT_KEYWORDS = ["AI应用开发", "大模型", "LangChain", "Agent"]


def boss_job_to_structured(job: BossJob) -> dict:
    """
    把 BossJob 转成 v2.1 structured_json 契约的 dict。

    映射规则（让索引脚本 build_embed_text 拼出来的语义最强）：
      title       = jobName                 ← 标题最重要
      summary     = 自然语言一句话总结      ← 让 embedding 抓到薪资+城市+经验
      key_points  = jobLabels（经验/学历）  ← 已经是结构化要点
      tags        = skills + 关键词 + 城市  ← 检索时用得上
    """
    summary_parts = [
        f"{job.city}地区",
        f"职位「{job.job_name}」",
        f"薪资 {job.salary_desc}",
    ]
    if job.job_labels:
        summary_parts.append("要求：" + " / ".join(job.job_labels))
    if job.boss_title:
        summary_parts.append(f"发布人：{job.boss_name}（{job.boss_title}）")

    tags: list[str] = list(job.skills)
    if job.keyword and job.keyword not in tags:
        tags.append(job.keyword)
    if job.city and job.city not in tags:
        tags.append(job.city)

    return {
        "title": job.job_name,
        "summary": "，".join(summary_parts) + "。",
        "key_points": list(job.job_labels),
        "tags": tags,
        # Boss 专属富字段（不影响 v2.1 build_embed_text，下游 Agent 可用）
        "_boss": {
            "salary_desc": job.salary_desc,
            "city": job.city,
            "keyword": job.keyword,
            "skills": list(job.skills),
            "boss_name": job.boss_name,
            "boss_title": job.boss_title,
            "boss_cert": job.boss_cert,
            "encrypt_job_id": job.encrypt_job_id,
            # 详情 API 所需配对参数（P4' enrich 时使用）
            "security_id": job.raw.get("securityId", ""),
            "lid": job.raw.get("lid", ""),
        },
    }


async def ingest(
    cities: list[str],
    keywords: list[str],
    pages_per_query: int,
) -> tuple[int, int, int]:
    """返回 (抓到, 新入库, 已存在跳过)。"""
    db = DBManager()

    src = BossSource(
        cities=cities,
        keywords=keywords,
        pages_per_query=pages_per_query,
        filter_noise=True,
    )

    logger.info(f"开始抓取 {len(cities)} 城市 × {len(keywords)} 关键词 × {pages_per_query} 页 ...")
    jobs = await src.fetch_jobs_structured()
    logger.info(f"BossSource 共返回 {len(jobs)} 条去噪岗位")

    # 同一 url 在本批中可能重复（同一岗位被多个关键词同时召回）—— 先去重
    seen, unique_jobs = set(), []
    for j in jobs:
        if j.url in seen:
            continue
        seen.add(j.url)
        unique_jobs.append(j)
    logger.info(f"批内去重后 {len(unique_jobs)} 条唯一 URL")

    # 1) URL 入 task_queue（v2.1 流水线惯例：先有 task，再有 final_result）
    urls = [j.url for j in unique_jobs]
    added_to_queue = db.add_new_urls(urls, source_type="boss_zhipin")
    logger.info(f"task_queue 新增 {added_to_queue} 条（{len(urls) - added_to_queue} 条已存在）")

    # 2) 直接写 final_results（跳过 collector + processor，因为 Boss API 已结构化）
    saved = 0
    skipped_already_in_results = 0

    # 查一遍 final_results 已有的 url，避免重复写入
    import sqlite3
    conn = sqlite3.connect(db.db_path)
    existing = {row[0] for row in conn.execute(
        "SELECT url FROM final_results WHERE source_type = 'boss_zhipin'"
    ).fetchall()}
    conn.close()

    for job in unique_jobs:
        if job.url in existing:
            skipped_already_in_results += 1
            continue
        structured = boss_job_to_structured(job)
        db.save_final_result(
            url=job.url,
            json_data=json.dumps(structured, ensure_ascii=False),
            source_type="boss_zhipin",
        )
        saved += 1

    return len(unique_jobs), saved, skipped_already_in_results


def main():
    ap = argparse.ArgumentParser(description="抓 Boss 岗位 → final_results")
    ap.add_argument(
        "--cities",
        default=",".join(DEFAULT_CITIES),
        help=f"逗号分隔；默认 {DEFAULT_CITIES}",
    )
    ap.add_argument(
        "--keywords",
        default=",".join(DEFAULT_KEYWORDS),
        help=f"逗号分隔；默认 {DEFAULT_KEYWORDS}",
    )
    ap.add_argument("--pages", type=int, default=1, help="每个查询抓几页（默认 1）")
    args = ap.parse_args()

    cities = [c.strip() for c in args.cities.split(",") if c.strip()]
    keywords = [k.strip() for k in args.keywords.split(",") if k.strip()]

    fetched, saved, skipped = asyncio.run(ingest(cities, keywords, args.pages))

    print()
    print("=" * 70)
    print(f"✅ 抓取去噪 {fetched} 条 / 新入库 {saved} 条 / 已存在跳过 {skipped} 条")
    print("=" * 70)
    print()
    print("下一步：")
    print("  python scripts/index_final_results.py   # 把新岗位喂给 bge-m3 + Milvus")
    print('  python scripts/search.py "薪资 20K+ 要 LangChain 的 AI 应用岗"')


if __name__ == "__main__":
    main()
