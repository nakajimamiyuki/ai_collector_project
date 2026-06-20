"""
ArxivSource —— arXiv 论文信息源 (v2.0 Phase 2)

通过 arXiv 官方 Atom API 发现指定分类下的最新论文。
默认监控 cs.AI / cs.CL / cs.LG（AI / NLP / 机器学习）三大分类。

设计要点
--------
- 用官方 export API（稳定、无需反爬），HTTPS。
- 只在 fetch_new_urls() 里"发现"论文的 abstract 页 URL，去重 / 增量
  判断交给 DBManager。
- arXiv 的 abstract 页是静态 HTML，collector 用轻量 requests 即可抓取，
  无需 Playwright（见 collector 的 URL 分派逻辑）。
"""

import logging
import xml.etree.ElementTree as ET
from typing import List

import requests

from src.sources.base import BaseSource

logger = logging.getLogger(__name__)


class ArxivSource(BaseSource):
    source_type = "arxiv"

    API_URL = "https://export.arxiv.org/api/query"

    # Atom XML 命名空间
    _NS = {"atom": "http://www.w3.org/2005/Atom"}

    # 默认监控的 arXiv 分类
    DEFAULT_CATEGORIES = ["cs.AI", "cs.CL", "cs.LG"]

    HEADERS = {
        "User-Agent": (
            "ai_collector_project/2.0 (https://github.com/nakajimamiyuki/"
            "ai_collector_project; research aggregator)"
        )
    }

    def __init__(self, categories: List[str] = None, max_results: int = 10):
        """
        Args:
            categories: 要监控的 arXiv 分类列表（如 ["cs.AI", "cs.CL"]）。
            max_results: 每个分类拉取的最新论文数。
        """
        self.categories = categories or list(self.DEFAULT_CATEGORIES)
        self.max_results = max_results

    async def fetch_new_urls(self) -> List[str]:
        """
        拉取所有监控分类下的最新论文 abstract URL（已跨分类去重）。
        失败时记日志并返回已拿到的部分（不抛业务异常）。
        """
        all_urls: List[str] = []
        for cat in self.categories:
            urls = self._fetch_category(cat)
            all_urls.extend(urls)

        # 跨分类去重，保持顺序
        seen = set()
        deduped = []
        for u in all_urls:
            if u not in seen:
                seen.add(u)
                deduped.append(u)

        logger.info(
            f"[ArxivSource] scanned {len(self.categories)} category(ies), "
            f"found {len(deduped)} unique paper URL(s)."
        )
        return deduped

    def _fetch_category(self, category: str) -> List[str]:
        """拉取单个分类的最新论文 URL 列表。"""
        params = {
            "search_query": f"cat:{category}",
            "sortBy": "submittedDate",
            "sortOrder": "descending",
            "max_results": self.max_results,
        }
        try:
            resp = requests.get(
                self.API_URL, params=params, headers=self.HEADERS, timeout=30
            )
        except requests.RequestException as e:
            logger.warning(f"[ArxivSource] requests error for cat={category}: {e}")
            return []

        if resp.status_code != 200:
            logger.warning(
                f"[ArxivSource] HTTP {resp.status_code} for cat={category}"
            )
            return []

        try:
            root = ET.fromstring(resp.content)
        except ET.ParseError as e:
            logger.warning(f"[ArxivSource] XML parse error for cat={category}: {e}")
            return []

        urls: List[str] = []
        for entry in root.findall("atom:entry", self._NS):
            id_node = entry.find("atom:id", self._NS)
            if id_node is None or not id_node.text:
                continue
            # id 形如 http://arxiv.org/abs/2606.20560v1 -> 规范化为 https + 去版本号
            abs_url = id_node.text.strip()
            abs_url = abs_url.replace("http://arxiv.org/", "https://arxiv.org/")
            # 去掉版本号 v1/v2，避免同一篇论文不同版本被当作不同 URL
            if "/abs/" in abs_url:
                base = abs_url.split("/abs/", 1)[1]
                base = base.split("v")[0] if "v" in base.split("/")[-1] else base
                abs_url = f"https://arxiv.org/abs/{base}"
            urls.append(abs_url)

        logger.info(
            f"[ArxivSource] cat={category}: found {len(urls)} papers."
        )
        return urls
