"""
Bilibili collector (v1.1)

v1.0 -> v1.1 改进：
- 选择器全面更新（基于 2026-06-17 的真实 B 站 DOM 探测）
  · .video-desc / .desc-content  ❌ 已下线
  · .video-desc-container / #v_desc  ✅ 当前正确
- 标题、UP主、标签独立抓取，不再让 LLM 从 markdown 里"猜"
- 抓到的结构化字段拼到 markdown 顶部，给 LLM 更明确的 anchor
- print() -> logger
- 任何单个字段失败都不影响整体（容错降级）
"""

import asyncio
import logging
import random

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

    async def collect_content(self, url):
        """
        采集 B 站视频页主体内容并转 Markdown。
        失败返回 None；成功返回带结构化头部的 Markdown 字符串。
        """
        logger.info(f"[Collector] Collecting from: {url}")

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
