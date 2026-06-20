"""
v2.0 Phase 2 端到端验证：arXiv 全链路（发现 -> 采集 -> LLM 清洗）
不写主库，单条手动跑通，验证三个模块协同正确。
"""
import asyncio
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

from src.sources.arxiv import ArxivSource
from src.collector import BiliCollector
from src.processor import LLMProcessor


async def main():
    print("\n=== 1. ArxivSource 发现 ===")
    src = ArxivSource(categories=["cs.AI"], max_results=2)
    urls = await src.fetch_new_urls()
    assert urls, "应发现论文"
    url = urls[0]
    print(f"  选取: {url}")

    print("\n=== 2. Collector 采集（应走 arxiv 轻量路径，不开浏览器）===")
    collector = BiliCollector(headless=True)
    md = await collector.collect_content(url)
    assert md and len(md) > 50, "应采集到内容"
    print(f"  采集到 {len(md)} 字符，前 200:")
    print("  " + md[:200].replace("\n", "\n  "))

    print("\n=== 3. Processor LLM 清洗（应走 arxiv prompt，summary 中文）===")
    proc = LLMProcessor()
    result = proc.clean_data(md, url=url)
    assert result, "LLM 应返回结构化 JSON"
    print(result)

    print("\n=== arXiv 全链路 OK ===")


if __name__ == "__main__":
    asyncio.run(main())
