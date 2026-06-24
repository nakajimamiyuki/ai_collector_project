"""
P4'：用 Boss 详情 API 给已入库的岗位补全富数据。

flow
----
1. 从 final_results 找出 source_type='boss_zhipin' 但 postDescription 还没补的条目
2. 从 structured_json._boss 拿 (securityId, lid) → 调 BossSource.fetch_job_details
3. 把 postDescription / experienceName / degreeName / brandName 合并进 structured_json
4. 重新写回 final_results

落库后下游：
- scripts/index_final_results.py  → 重新索引（postDescription 进 embed_text，召回质量↑）
- scripts/search.py               → 同一查询能召回明显更准的岗位

用法：
    python scripts/enrich_boss_details.py            # 默认补全所有未补的
    python scripts/enrich_boss_details.py --limit 20 # 调试：只抓 20 条
    python scripts/enrich_boss_details.py --rerun    # 已补过的也重抓（更新数据）
"""
import os

# macOS OpenMP 双库冲突 escape hatch（必须在 import numpy/faiss/milvus 前设置）
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.sources.boss_zhipin import BossSource

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


SQLITE_PATH = PROJECT_ROOT / "data" / "collector.db"


def load_boss_jobs_needing_enrichment(
    limit: int | None,
    rerun: bool,
) -> list[tuple[int, str, dict]]:
    """返回 [(id, url, structured), ...]。"""
    conn = sqlite3.connect(SQLITE_PATH)
    rows = conn.execute(
        "SELECT id, url, structured_json FROM final_results "
        "WHERE source_type = 'boss_zhipin' "
        "ORDER BY id"
    ).fetchall()
    conn.close()

    out = []
    for rid, url, sj in rows:
        try:
            structured = json.loads(sj) if sj else {}
        except json.JSONDecodeError:
            logger.warning(f"[parse] id={rid} structured_json 损坏，跳过")
            continue

        # 不重跑：已有 post_description 就跳过
        if not rerun and structured.get("_boss", {}).get("post_description"):
            continue
        out.append((rid, url, structured))

    if limit:
        out = out[:limit]
    return out


def update_structured(
    record_id: int,
    structured: dict,
) -> None:
    conn = sqlite3.connect(SQLITE_PATH)
    conn.execute(
        "UPDATE final_results SET structured_json = ? WHERE id = ?",
        (json.dumps(structured, ensure_ascii=False), record_id),
    )
    conn.commit()
    conn.close()


def merge_detail_into_structured(structured: dict, detail) -> dict:
    """
    把 BossJobDetail 合并到 structured_json。

    设计原则：
    - title 不动（已有）
    - summary 补上"公司名 + 学历 + 经验"，让 embedding 拿到这些信号
    - key_points 升级为 [经验, 学历, 公司] + 原 jobLabels
    - tags 补充经验/学历短语
    - _boss 子节点保存原始详情字段（下游 Agent / 报告用）
    """
    job = structured.get("_boss", {})

    # 把 detail 中的字段合并到 _boss（保留搜索阶段已有字段如 keyword）
    job.update({
        "post_description": detail.post_description,
        "experience_name": detail.experience_name,
        "degree_name": detail.degree_name,
        "brand_name": detail.brand_name,
        "address": detail.address,
        # 详情 jobLabels 通常是 skills（如 ["MySQL", "Python"]），更准
        "detail_labels": list(detail.job_labels),
    })
    # 详情若提供更精确的薪资描述就更新
    if detail.salary_desc:
        job["salary_desc"] = detail.salary_desc

    structured["_boss"] = job

    # 升级 summary：加入公司、学历、经验，让 bge-m3 召回更准
    summary_parts = [
        f"{detail.city_name or job.get('city', '')}地区",
        f"公司「{detail.brand_name}」" if detail.brand_name else "",
        f"职位「{detail.job_name}」",
        f"薪资 {detail.salary_desc or job.get('salary_desc', '')}",
        f"要求 {detail.experience_name}经验" if detail.experience_name else "",
        f"{detail.degree_name}学历" if detail.degree_name else "",
    ]
    summary_parts = [s for s in summary_parts if s]

    # 把 JD 正文前 600 字加进 summary——embedding 能看到核心技能词
    if detail.post_description:
        jd_excerpt = detail.post_description[:600].replace("\n", " ")
        summary_parts.append(f"职责：{jd_excerpt}")

    structured["summary"] = "，".join(summary_parts) + "。"

    # key_points：经验 + 学历 + 公司 + 原 labels
    kp: list[str] = []
    if detail.experience_name:
        kp.append(detail.experience_name)
    if detail.degree_name:
        kp.append(detail.degree_name)
    if detail.brand_name:
        kp.append(detail.brand_name)
    kp.extend(structured.get("key_points", []))
    # 去重保序
    seen, deduped = set(), []
    for k in kp:
        if k and k not in seen:
            seen.add(k)
            deduped.append(k)
    structured["key_points"] = deduped

    # tags：加入经验/学历/公司
    tags = structured.get("tags", []) or []
    for t in [detail.experience_name, detail.degree_name, detail.brand_name]:
        if t and t not in tags:
            tags.append(t)
    # 详情 jobLabels（通常是 skills）也合入
    for label in detail.job_labels:
        if label and label not in tags:
            tags.append(label)
    structured["tags"] = tags

    return structured


async def enrich(limit: int | None, rerun: bool):
    records = load_boss_jobs_needing_enrichment(limit, rerun)
    if not records:
        logger.info("没有需要富化的 Boss 岗位，退出（如想重抓加 --rerun）")
        return

    logger.info(f"待富化 {len(records)} 条 Boss 岗位")

    # 收集 (security_id, lid) 配对
    pairs = []
    rec_by_pair: dict[tuple[str, str], tuple[int, str, dict]] = {}
    skipped_missing_ids = 0
    for rid, url, structured in records:
        job = structured.get("_boss", {})
        # 注意：搜索阶段我们没把 securityId/lid 单独存——它们在 _boss 之外的 raw
        # 这里需要从已知字段或 url 倒推。先看看是否已经保留：
        sid = job.get("security_id") or job.get("_security_id")
        lid = job.get("lid") or job.get("_lid")
        if not sid or not lid:
            skipped_missing_ids += 1
            continue
        pairs.append((sid, lid))
        rec_by_pair[(sid, lid)] = (rid, url, structured)

    if skipped_missing_ids:
        logger.warning(
            f"⚠️ {skipped_missing_ids} 条岗位缺 securityId/lid（旧数据没保存），"
            "这些条目此次无法富化"
        )

    if not pairs:
        logger.error(
            "所有岗位都缺 securityId/lid。"
            "→ 解决：重新跑 scripts/ingest_boss_jobs.py（新版会保存这两个字段）"
        )
        return

    logger.info(f"准备调详情 API {len(pairs)} 次...")
    src = BossSource(
        cities=["杭州"],  # 不实际用
        keywords=["AI"],  # 不实际用
        pages_per_query=1,
    )
    details = await src.fetch_job_details(pairs)

    logger.info(f"详情抓取完成：{len(details)} / {len(pairs)} 条成功")

    # 回写
    updated = 0
    for detail in details:
        # 用 encryptJobId 反查 record（更可靠）
        match = None
        for (sid, lid), (rid, url, structured) in rec_by_pair.items():
            if structured.get("_boss", {}).get("encrypt_job_id") == detail.encrypt_job_id:
                match = (rid, url, structured)
                break
        if match is None:
            logger.warning(f"无法匹配详情回写：{detail.encrypt_job_id}")
            continue
        rid, url, structured = match
        merged = merge_detail_into_structured(structured, detail)
        update_structured(rid, merged)
        updated += 1

    print()
    print("=" * 70)
    print(f"✅ 富化完成：{updated} 条 Boss 岗位补上了 JD 正文 + 公司 + 学历经验")
    print("=" * 70)
    print()
    print("下一步：")
    print("  python scripts/index_final_results.py --rebuild   # 重建向量库（embed 进了更丰富的内容）")
    print('  python scripts/search.py "薪资 20K+ 要 LangChain 的本科 1-3 年" --source boss_zhipin')


def main():
    ap = argparse.ArgumentParser(description="给 final_results 里的 Boss 岗位补全 JD 详情")
    ap.add_argument("--limit", type=int, default=None, help="只补前 N 条（调试用）")
    ap.add_argument("--rerun", action="store_true", help="已补过的也重抓一遍")
    args = ap.parse_args()

    asyncio.run(enrich(args.limit, args.rerun))


if __name__ == "__main__":
    main()
