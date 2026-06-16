import asyncio
from playwright.async_api import async_playwright
from playwright_stealth import Stealth
from markdownify import markdownify as md
from bs4 import BeautifulSoup
import random
import time

class BiliCollector:
    def __init__(self, headless=True):
        self.headless = headless

    async def collect_content(self, url):
        """
        使用 Playwright 采集 B 站视频页面的正文内容并转换为 Markdown
        """
        print(f"Collecting content from: {url}...")
        
        async with async_playwright() as p:
            # 启动浏览器
            browser = await p.chromium.launch(headless=self.headless)
            
            # 创建上下文，设置常见的 User-Agent
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                viewport={'width': 1280, 'height': 800}
            )
            
            page = await context.new_page()
            
            # 应用 stealth 插件，隐藏自动化特征
            await Stealth().apply_stealth_async(page)
            
            try:
                # 禁用图片加载以提升速度
                await page.route("**/*.{jpg,jpeg,png,gif,webp,svg}", lambda route: route.abort())
                
                # 访问页面
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                
                # 模拟人类行为：随机等待 2-5 秒
                await asyncio.sleep(random.uniform(2, 5))
                
                # 针对 B 站视频页面的正文提取逻辑
                # B 站的视频描述通常在 .video-desc 或类似类名中
                # 我们先尝试等待描述区域加载
                try:
                    await page.wait_for_selector(".video-desc, .desc-content", timeout=10000)
                except:
                    print(f"Warning: Could not find description area for {url}, grabbing general body.")

                # 获取页面 HTML
                content = await page.content()
                
                # 使用 BeautifulSoup 进行初步清洗，只保留正文区域
                soup = BeautifulSoup(content, 'html.parser')
                
                # 尝试定位 B 站视频描述区域
                desc_element = soup.select_one(".video-desc") or soup.select_one(".desc-content")
                
                if desc_element:
                    # 仅对描述区域进行 Markdown 转换
                    clean_html = str(desc_element)
                else:
                    # 如果没找到描述区，则提取 body 中所有文本
                    clean_html = str(soup.body if soup.body else soup)

                # 转换为 Markdown
                markdown_text = md(clean_html, heading_style="ATX").strip()
                
                # 如果结果太短，说明可能被拦截或没抓到，尝试抓取标题作为补充
                if len(markdown_text) < 10:
                    title = await page.title()
                    markdown_text = f"# {title}\n(Content could not be extracted, possible bot detection or empty description)"

                print(f"Successfully extracted content for {url}. Length: {len(markdown_text)} chars.")
                return markdown_text

            except Exception as e:
                print(f"Error collecting {url}: {e}")
                return None
            finally:
                await browser.close()
