"""
Bilibili monitor (v1.1)

v1.0 -> v1.1 改进：
- 参数 uid= -> mid=（B 站官方推荐，老参数已逐步弃用）
- requests 失败时自动 fallback 到 Playwright（打开 space.bilibili.com 抓 BV 号）
- 完整浏览器 headers + 可选 BILI_COOKIE
- 区分 HTTP 错误 / B 站业务错误码（-799 WBI 签名 / -111 鉴权失败 / -412 风控）
- print() -> logger
"""

import os
import re
import asyncio
import logging
from typing import List, Optional

import requests
from dotenv import load_dotenv

from src.db_manager import DBManager

load_dotenv()
logger = logging.getLogger(__name__)


class BiliMonitor:
    API_URL = "https://api.bilibili.com/x/space/arc/search"

    # B 站要求带这些 headers 才会通过基本反爬
    DEFAULT_HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        ),
        "Referer": "https://space.bilibili.com/",
        "Origin": "https://space.bilibili.com",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }

    # 已知的业务错误码：requests 路径无法解决，必须切 Playwright
    NEED_FALLBACK_CODES = {-799, -412, -403, -509}

    def __init__(self):
        self.db = DBManager()
        self.headers = dict(self.DEFAULT_HEADERS)

        # .env 里可选放一份用户的 BILI_COOKIE，用来提升请求成功率
        cookie = os.getenv("BILI_COOKIE")
        if cookie:
            self.headers["Cookie"] = cookie
            logger.info("[Monitor] BILI_COOKIE loaded from .env")

    # ------------------------------------------------------------------
    # Stage A: 普通 requests
    # ------------------------------------------------------------------
    def _fetch_via_requests(self, uid) -> Optional[List[str]]:
        """
        返回:
          list[str] -> 成功（可能是空列表，代表确实没新视频）
          None      -> 需要 fallback
        """
        params = {"mid": uid, "pn": 1, "ps": 30}
        try:
            resp = requests.get(
                self.API_URL, params=params, headers=self.headers, timeout=15
            )
        except requests.RequestException as e:
            logger.warning(f"[Monitor] requests error for UID {uid}: {e}")
            return None

        if resp.status_code in (412, 403, 429):
            logger.warning(
                f"[Monitor] HTTP {resp.status_code} for UID {uid} "
                f"(rate-limited / blocked) -> will fallback"
            )
            return None
        if resp.status_code >= 400:
            logger.warning(
                f"[Monitor] HTTP {resp.status_code} for UID {uid} -> will fallback"
            )
            return None

        try:
            data = resp.json()
        except ValueError:
            logger.warning(f"[Monitor] Non-JSON response for UID {uid} -> will fallback")
            return None

        code = data.get("code")
        if code in self.NEED_FALLBACK_CODES:
            logger.warning(
                f"[Monitor] Bilibili API code={code} for UID {uid} "
                f"(WBI sign / risk-control) -> will fallback"
            )
            return None
        if code == -111:
            logger.error(f"[Monitor] UID {uid} not found or access denied (code=-111).")
            return []  # 业务上确认无效，无需 fallback
        if code != 0:
            logger.warning(
                f"[Monitor] Bilibili API returned non-zero code={code} for UID {uid}: "
                f"{data.get('message')}"
            )
            return None

        video_list = data.get("data", {}).get("list", {}).get("vlist", [])
        urls = [
            f"https://www.bilibili.com/video/{v['bvid']}"
            for v in video_list
            if v.get("bvid")
        ]
        logger.info(f"[Monitor] [requests] UID {uid}: found {len(urls)} videos.")
        return urls

    # ------------------------------------------------------------------
    # Stage B: Playwright fallback
    # ------------------------------------------------------------------
    async def _fetch_via_playwright_async(self, uid) -> List[str]:
        """打开 UP 主投稿页，从 DOM 里抠 BV 号。"""
        from playwright.async_api import async_playwright
        from playwright_stealth import Stealth

        space_url = f"https://space.bilibili.com/{uid}/video"
        urls: List[str] = []

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            ctx = await browser.new_context(
                user_agent=self.DEFAULT_HEADERS["User-Agent"],
                viewport={"width": 1280, "height": 800},
            )
            page = await ctx.new_page()
            await Stealth().apply_stealth_async(page)

            try:
                # 先访问主页 seed cookie
                await page.goto(
                    "https://www.bilibili.com/", wait_until="domcontentloaded", timeout=30000
                )
                await asyncio.sleep(1.5)

                await page.goto(space_url, wait_until="domcontentloaded", timeout=30000)
                await asyncio.sleep(3)  # 等 SPA 渲染

                # 直接从整页 HTML 里抠 /video/BVxxxx 链接
                html = await page.content()
                bvids = set(re.findall(r"/video/(BV[0-9A-Za-z]{10})", html))
                urls = [f"https://www.bilibili.com/video/{bv}" for bv in bvids]

                logger.info(
                    f"[Monitor] [playwright] UID {uid}: scraped {len(urls)} BV ids "
                    f"from {space_url}"
                )
            except Exception as e:
                logger.error(f"[Monitor] Playwright fallback failed for UID {uid}: {e}")
            finally:
                await browser.close()

        return urls

    def _fetch_via_playwright(self, uid) -> List[str]:
        """同步包装：选择当前是否已有 event loop，避开 'event loop is running' 报错。"""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self._fetch_via_playwright_async(uid))
        # 已经在事件循环里（极少出现），直接调用底层
        return asyncio.get_event_loop().run_until_complete(
            self._fetch_via_playwright_async(uid)
        )

    # ------------------------------------------------------------------
    # 公共入口
    # ------------------------------------------------------------------
    def fetch_bilibili_urls(self, uid) -> List[str]:
        """
        先 requests，失败再 Playwright。
        统一返回 list[str]，永远不抛异常。
        """
        logger.info(f"[Monitor] Scanning UID {uid} ...")

        urls = self._fetch_via_requests(uid)
        if urls is not None:
            return urls

        logger.info(f"[Monitor] requests path failed, trying Playwright fallback ...")
        return self._fetch_via_playwright(uid)

    def sync_targets(self, target_uids):
        total_added = 0
        for uid in target_uids:
            urls = self.fetch_bilibili_urls(uid)
            if urls:
                added = self.db.add_new_urls(urls)
                logger.info(f"[Monitor] UID {uid}: added {added} new tasks to queue.")
                total_added += added
        logger.info(f"[Monitor] Sync completed. Total new tasks added: {total_added}")
        return total_added
