"""
信息源插件包 (v2.0)

每个数据源（B 站 / arXiv / 知乎 ...）实现为一个 BaseSource 子类，
统一对外暴露 `fetch_new_urls()` 接口。Monitor 作为调度器持有一组
Source 实例，逐个发现新 URL 并汇总入库。
"""

from src.sources.base import BaseSource
from src.sources.bilibili import BilibiliSource
from src.sources.arxiv import ArxivSource

__all__ = ["BaseSource", "BilibiliSource", "ArxivSource"]
