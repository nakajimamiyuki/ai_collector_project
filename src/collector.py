"""
Content collector (v2.0)

v1.1 -> v2.0 改进：
- 按 URL 类型分派采集策略（插件式信息源的下游配套）：
  · bilibili.com  -> Playwright + stealth（动态 SPA，需浏览器）
  · arxiv.org     -> 轻量 requests + BeautifulSoup（静态页，无需浏览器）
- collect_content(url) 仍是统一入口，main.py 无需感知类型差异
- 类名保留 BiliCollector 以兼容旧调用（实为通用 Collector）

v1.0 -> v1.1（B 站部分，原样保留）：
- 选择器全面更新（基于 2026-06-17 的真实 B 站 DOM 探测）
- 标题、UP主、标签独立抓取，拼到 markdown 顶部给 LLM 明确 anchor
- 任何单个字段失败都不影响整体（容错降级）
"""

import asyncio
import logging
import random

import requests
from playwright.async_api import async_playwright
from playwright_stealth import Stealth
from markdownify import markdownify as md
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


# 选择器优先级表：从最新最准 -> 最老最兜底
SELECTORS = {
    "title": [
        "h1.video-title",
        "h1[title]",
        ".video-title",
    ],
    "up_name": [
        ".up-name",
        ".up-info--right .up-name",
        ".staff-info .up-name",
    ],
    "desc": [
        ".video-desc-container",
        "#v_desc",
        ".basic-desc-info",
        ".video-desc",         # 旧选择器留作最后兜底
        ".desc-content",
    ],
    "tags": [
        ".tag-link",
        ".tag-area .tag",
    ],
}


class BiliCollector:
    def __init__(self, headless=True):
        self.headless = headless

    @staticmethod
    async def _try_text(page, selectors):
        """按优先级尝试一组选择器，返回第一个有文本的结果。"""
        for sel in selectors:
            try:
                loc = page.locator(sel).first
                if await loc.count() > 0:
                    txt = (await loc.text_content()) or ""
                    txt = txt.strip()
                    if txt:
                        return txt, sel
            except Exception:
                continue
        return None, None

    @staticmethod
    async def _try_all_texts(page, selectors):
        """按优先级尝试一组选择器，返回第一个有匹配的全部文本列表。"""
        for sel in selectors:
            try:
                loc = page.locator(sel)
                n = await loc.count()
                if n > 0:
                    texts = []
                    for i in range(n):
                        t = (await loc.nth(i).text_content()) or ""
                        t = t.strip()
                        if t:
                            texts.append(t)
                    if texts:
                        return texts, sel
            except Exception:
                continue
        return [], None

    async def collect_content(self, url, source_type=None):
        """
        统一采集入口：按来源类型分派到对应采集策略。
        失败返回 None；成功返回带结构化头部的 Markdown 字符串。

        Args:
            url: 内容 URL。
            source_type: 显式来源类型（bilibili / arxiv）。为 None 时从 URL 推断（兜底）。
        """
        if source_type is None:
            source_type = "arxiv" if "arxiv.org" in url else "bilibili"

        if source_type == "arxiv":
            return self._collect_arxiv(url)
        # 默认按 B 站处理（向后兼容）
        return await self._collect_bilibili(url)

    # ------------------------------------------------------------------
    # arXiv：轻量 requests，无需浏览器
    # ------------------------------------------------------------------
    def _collect_arxiv(self, url):
        """
        采集 arXiv abstract 页（静态 HTML），转成带结构化头部的 Markdown。
        arXiv 页面是服务端渲染的静态页，requests 即可，省去 Playwright 开销。
        """
        logger.info(f"[Collector] Collecting (arxiv) from: {url}")
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            )
        }
        try:
            resp = requests.get(url, headers=headers, timeout=30)
            if resp.status_code != 200:
                logger.error(f"[Collector] arxiv HTTP {resp.status_code} for {url}")
                return None

            soup = BeautifulSoup(resp.content, "html.parser")

            def _clean(node, prefix):
                """取文本并去掉 arxiv 页面的 'Title:' / 'Abstract:' 等前缀。"""
                if not node:
                    return None
                txt = node.get_text(strip=True)
                if prefix and txt.startswith(prefix):
                    txt = txt[len(prefix):].strip()
                return txt or None

            title = _clean(soup.select_one("h1.title"), "Title:")
            authors = _clean(soup.select_one("div.authors"), "Authors:")
            abstract = _clean(soup.select_one("blockquote.abstract"), "Abstract:")
            # 学科分类标签
            subjects = _clean(soup.select_one("td.subjects"), None)

            header_lines = []
            if title:
                header_lines.append(f"# {title}")
            if authors:
                header_lines.append(f"作者：{authors}")
            if subjects:
                header_lines.append(f"分类：{subjects}")

            body = abstract or ""
            if header_lines:
                markdown_text = "\n\n".join(header_lines) + "\n\n---\n\n" + body
            else:
                markdown_text = body

            if len(markdown_text) < 20:
                logger.warning(f"[Collector] arxiv content too short for {url}")
                return None

            logger.info(
                f"[Collector] OK (arxiv) {url} | len={len(markdown_text)} "
                f"title={'Y' if title else 'N'} abstract={'Y' if abstract else 'N'}"
            )
            return markdown_text

        except Exception as e:
            logger.error(f"[Collector] arxiv error on {url}: {e}")
            return None

    # ------------------------------------------------------------------
    # Bilibili：Playwright + stealth（v1.1 逻辑原样保留）
    # ------------------------------------------------------------------
    async def _collect_bilibili(self, url):
        """
        采集 B 站视频页主体内容并转 Markdown。
        失败返回 None；成功返回带结构化头部的 Markdown 字符串。
        """
        logger.info(f"[Collector] Collecting (bilibili) from: {url}")

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self.headless)
            context = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1280, "height": 800},
            )
            page = await context.new_page()
            await Stealth().apply_stealth_async(page)

            try:
                # 屏蔽图片，提速
                await page.route(
                    "**/*.{jpg,jpeg,png,gif,webp,svg}",
                    lambda route: route.abort(),
                )

                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                await asyncio.sleep(random.uniform(2, 4))

                # 尝试等待描述区域加载（即使失败也继续）
                try:
                    await page.wait_for_selector(
                        ", ".join(SELECTORS["desc"]), timeout=8000
                    )
                except Exception:
                    logger.warning(
                        f"[Collector] desc selector timeout for {url}, "
                        f"falling back to whole-body extraction."
                    )

                # === 结构化字段抓取 ===
                title, title_sel = await self._try_text(page, SELECTORS["title"])
                up_name, up_sel = await self._try_text(page, SELECTORS["up_name"])
                desc_text, desc_sel = await self._try_text(page, SELECTORS["desc"])
                tags, tags_sel = await self._try_all_texts(page, SELECTORS["tags"])

                logger.info(
                    f"[Collector] Selectors hit: "
                    f"title={title_sel}, up={up_sel}, desc={desc_sel}, tags={tags_sel}"
                )

                # === HTML 兜底（保留旧逻辑作为 markdown 主体的 fallback） ===
                html = await page.content()
                soup = BeautifulSoup(html, "html.parser")

                desc_html_node = None
                for sel in SELECTORS["desc"]:
                    desc_html_node = soup.select_one(sel)
                    if desc_html_node:
                        break

                if desc_html_node:
                    body_md = md(str(desc_html_node), heading_style="ATX").strip()
                else:
                    # 抓不到描述区时退回到 body，但限制长度避免 Markdown 巨大
                    body_md = md(
                        str(soup.body if soup.body else soup), heading_style="ATX"
                    ).strip()

                # === 把结构化字段拼到 markdown 顶部，给 LLM 明确锚点 ===
                header_lines = []
                if title:
                    header_lines.append(f"# {title}")
                if up_name:
                    header_lines.append(f"UP主：{up_name}")
                if tags:
                    # 去重保序
                    seen, dedup = set(), []
                    for t in tags:
                        if t not in seen:
                            seen.add(t)
                            dedup.append(t)
                    header_lines.append(f"标签：{', '.join(dedup)}")
                if desc_text:
                    header_lines.append(f"描述：{desc_text}")

                if header_lines:
                    markdown_text = "\n\n".join(header_lines) + "\n\n---\n\n" + body_md
                else:
                    markdown_text = body_md

                # 兜底：内容太短说明被拦了
                if len(markdown_text) < 20:
                    page_title = await page.title()
                    markdown_text = (
                        f"# {page_title}\n"
                        f"(Content could not be extracted, "
                        f"possible bot detection or empty description)"
                    )

                logger.info(
                    f"[Collector] OK {url} | "
                    f"len={len(markdown_text)} title={'Y' if title else 'N'} "
                    f"up={'Y' if up_name else 'N'} desc={'Y' if desc_text else 'N'} "
                    f"tags={len(tags)}"
                )
                return markdown_text

            except Exception as e:
                logger.error(f"[Collector] Error on {url}: {e}")
                return None
            finally:
                await browser.close()
