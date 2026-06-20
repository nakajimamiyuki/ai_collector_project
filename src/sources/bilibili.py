"""
BilibiliSource —— B 站信息源 (v2.0)

由 v1.1 的 BiliMonitor 重构而来：核心抓取逻辑（requests 主路径 +
Playwright fallback + BILI_COOKIE 注入 + 业务错误码识别）原样保留，
只是包装成 BaseSource 接口。

一个 BilibiliSource 实例持有一组 UP 主 UID；fetch_new_urls() 会
扫描所有 UID 并汇总返回 URL 列表。
"""

import os
import re
import asyncio
import logging
from typing import List, Optional

import requests
from dotenv import load_dotenv

from src.sources.base import BaseSource

load_dotenv()
logger = logging.getLogger(__name__)


class BilibiliSource(BaseSource):
    source_type = "bilibili"

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

    def __init__(self, uids: List[str]):
        """
        Args:
            uids: 要监控的 UP 主 UID 列表。
        """
        self.uids = [str(u) for u in uids]
        self.headers = dict(self.DEFAULT_HEADERS)

        # .env 里可选放一份用户的 BILI_COOKIE，用来提升请求成功率
        cookie = os.getenv("BILI_COOKIE")
        if cookie:
            self.headers["Cookie"] = cookie
            logger.info("[BilibiliSource] BILI_COOKIE loaded from .env")

    # ------------------------------------------------------------------
    # BaseSource 接口实现
    # ------------------------------------------------------------------
    async def fetch_new_urls(self) -> List[str]:
        """扫描所有 UID，汇总返回视频 URL（已跨 UID 去重）。"""
        all_urls: List[str] = []
        for uid in self.uids:
            urls = await self._fetch_urls_for_uid(uid)
            all_urls.extend(urls)
        # 跨 UID 去重，保持顺序
        seen = set()
        deduped = []
        for u in all_urls:
            if u not in seen:
                seen.add(u)
                deduped.append(u)
        logger.info(
            f"[BilibiliSource] scanned {len(self.uids)} UID(s), "
            f"found {len(deduped)} unique video URL(s)."
        )
        return deduped

    async def _fetch_urls_for_uid(self, uid) -> List[str]:
        """单个 UID：先 requests，失败再 Playwright。统一返回 list[str]。"""
        logger.info(f"[BilibiliSource] Scanning UID {uid} ...")
        urls = self._fetch_via_requests(uid)
        if urls is not None:
            return urls
        logger.info(
            "[BilibiliSource] requests path failed, trying Playwright fallback ..."
        )
        return await self._fetch_via_playwright_async(uid)

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
            logger.warning(f"[BilibiliSource] requests error for UID {uid}: {e}")
            return None

        if resp.status_code in (412, 403, 429):
            logger.warning(
                f"[BilibiliSource] HTTP {resp.status_code} for UID {uid} "
                f"(rate-limited / blocked) -> will fallback"
            )
            return None
        if resp.status_code >= 400:
            logger.warning(
                f"[BilibiliSource] HTTP {resp.status_code} for UID {uid} -> will fallback"
            )
            return None

        try:
            data = resp.json()
        except ValueError:
            logger.warning(
                f"[BilibiliSource] Non-JSON response for UID {uid} -> will fallback"
            )
            return None

        code = data.get("code")
        if code in self.NEED_FALLBACK_CODES:
            logger.warning(
                f"[BilibiliSource] Bilibili API code={code} for UID {uid} "
                f"(WBI sign / risk-control) -> will fallback"
            )
            return None
        if code == -111:
            logger.error(
                f"[BilibiliSource] UID {uid} not found or access denied (code=-111)."
            )
            return []  # 业务上确认无效，无需 fallback
        if code != 0:
            logger.warning(
                f"[BilibiliSource] Bilibili API returned non-zero code={code} "
                f"for UID {uid}: {data.get('message')}"
            )
            return None

        video_list = data.get("data", {}).get("list", {}).get("vlist", [])
        urls = [
            f"https://www.bilibili.com/video/{v['bvid']}"
            for v in video_list
            if v.get("bvid")
        ]
        logger.info(f"[BilibiliSource] [requests] UID {uid}: found {len(urls)} videos.")
        return urls

    # ------------------------------------------------------------------
    # Stage B: Playwright fallback
    # ------------------------------------------------------------------
    @staticmethod
    def _parse_cookie_string(cookie_str):
        """
        把 'k1=v1; k2=v2' 格式的 cookie 字符串解析为
        Playwright 的 add_cookies 需要的 dict 列表。
        domain 设成 .bilibili.com，覆盖所有子域名。
        """
        cookies = []
        for chunk in cookie_str.split(";"):
            chunk = chunk.strip()
            if not chunk or "=" not in chunk:
                continue
            name, value = chunk.split("=", 1)
            name = name.strip()
            value = value.strip()
            if not name:
                continue
            cookies.append({
                "name": name,
                "value": value,
                "domain": ".bilibili.com",
                "path": "/",
            })
        return cookies

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

            # 关键：把 .env 里的 BILI_COOKIE 注入到 Playwright context，
            # 这样 fallback 路径也能享受登录态，绕过风控。
            cookie_str = os.getenv("BILI_COOKIE")
            if cookie_str:
                try:
                    pw_cookies = self._parse_cookie_string(cookie_str)
                    if pw_cookies:
                        await ctx.add_cookies(pw_cookies)
                        logger.info(
                            f"[BilibiliSource] [playwright] injected {len(pw_cookies)} "
                            f"cookies from BILI_COOKIE"
                        )
                except Exception as e:
                    logger.warning(
                        f"[BilibiliSource] [playwright] cookie inject failed: {e}"
                    )

            page = await ctx.new_page()
            await Stealth().apply_stealth_async(page)

            try:
                await page.goto(space_url, wait_until="domcontentloaded", timeout=30000)
                # 等 SPA 渲染列表，最多重试 3 次
                bvids: set = set()
                for delay in (2, 3, 4):
                    await asyncio.sleep(delay)
                    html = await page.content()
                    bvids = set(re.findall(r"/video/(BV[0-9A-Za-z]{10})", html))
                    if bvids:
                        break

                urls = [f"https://www.bilibili.com/video/{bv}" for bv in bvids]

                logger.info(
                    f"[BilibiliSource] [playwright] UID {uid}: scraped {len(urls)} "
                    f"BV ids from {space_url}"
                )
            except Exception as e:
                logger.error(
                    f"[BilibiliSource] Playwright fallback failed for UID {uid}: {e}"
                )
            finally:
                await browser.close()

        return urls
