"""P2 端到端验证：5 城市 × 4 关键词 抓岗位 + 打印汇总报告。"""

import asyncio
import logging
from collections import Counter

from src.sources.boss_zhipin import BossSource

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s | %(message)s",
)


async def main():
    src = BossSource(
        cities=["杭州", "苏州", "济南", "青岛", "郑州"],
        keywords=["AI应用开发", "大模型", "LangChain", "Agent"],
        pages_per_query=1,
        filter_noise=True,
    )

    jobs = await src.fetch_jobs_structured()

    print()
    print("=" * 70)
    print(f"✅ 总共拿到 {len(jobs)} 条去噪后的岗位")
    print("=" * 70)

    # 城市分布
    by_city = Counter(j.city for j in jobs)
    print("\n按城市分布：")
    for city, n in by_city.most_common():
        print(f"  {city:<6} {n:>3} 条")

    # 关键词分布
    by_kw = Counter(j.keyword for j in jobs)
    print("\n按关键词分布：")
    for kw, n in by_kw.most_common():
        print(f"  {kw:<14} {n:>3} 条")

    # 抽样 10 条最有可能匹配画像的
    print("\n=== 抽样 10 条 ===")
    for j in jobs[:10]:
        skills = ",".join(j.skills[:5]) if j.skills else "(无)"
        labels = ",".join(j.job_labels[:3]) if j.job_labels else "(无)"
        print(
            f"[{j.city}] {j.job_name[:25]:<25} | {j.salary_desc:<12} | "
            f"skills={skills:<25} | labels={labels}"
        )


if __name__ == "__main__":
    asyncio.run(main())
