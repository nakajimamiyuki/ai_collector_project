"""单独验证 ArxivSource.fetch_new_urls() 能真实发现 arXiv 论文 URL。"""
import asyncio
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

from src.sources.arxiv import ArxivSource
from src.sources.base import BaseSource


async def main():
    assert issubclass(ArxivSource, BaseSource)
    assert ArxivSource.source_type == "arxiv"

    src = ArxivSource(categories=["cs.AI"], max_results=3)
    urls = await src.fetch_new_urls()
    print(f"\n拿到 {len(urls)} 个 URL:")
    for u in urls:
        print(f"  - {u}")
    assert len(urls) > 0, "应至少拿到 1 篇论文"
    assert all(u.startswith("https://arxiv.org/abs/") for u in urls), "URL 格式应规范"
    print("\n=== ArxivSource OK ===")


if __name__ == "__main__":
    asyncio.run(main())
