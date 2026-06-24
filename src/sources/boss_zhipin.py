"""
BossSource —— Boss 直聘招聘源 (v3.0)

设计思路
--------
Boss 直聘 PC 站列表用 Canvas 渲染，常规爬虫拿不到岗位文字；但**移动端 H5
站 m.zhipin.com 提供了 JSON API**（/wapi/zpgeek/search/joblist.json），
直接返回结构化岗位列表（jobName / salaryDesc / skills / jobLabels / 发布人）。

为了优雅、长期可持续地绕过 Boss 风控（code 37 "您的环境存在异常"），
我们采用 **CDP 接管真实 Chrome** 方案：

1. 用户用 ~/.hermes/chrome-debug-profile 这个独立 profile 启动 Chrome：
       --remote-debugging-port=9222
       --user-data-dir="$HOME/.hermes/chrome-debug-profile"
2. 用户在那个 Chrome 里手动扫码登 Boss（一次性，cookie 持久保存）
3. BossSource 通过 Playwright 的 connect_over_cdp 接管这个浏览器
4. 在已登录的 m.zhipin.com 页面里直接 fetch API（同源、cookie 自动带）

这样：
- 完全绕开 code 37 风控（请求来自真实浏览器、真实用户 cookie）
- cookie 失效时浏览器会自然提示，用户重新扫码即可
- 不需要逆向 __zp_stoken__ 签名

实战经验（v3.0 P2 阶段发现）
----------------------------
- 连续高频请求依然会被 Boss 临时风控为 code 37 → 每次请求间加随机延迟
- 单次失败大多是临时的，简单重试 1-2 次即可恢复
- 日志中要打印 page_num（数字），不要打印 page 对象，否则刷一串 <Page url=...>

与 BaseSource 契约
------------------
fetch_new_urls() 返回岗位详情页 URL 列表，符合既有 Monitor 调度模式。
另外暴露 fetch_jobs_structured()，直接返回完整结构化岗位（v3.0 Agent 用）。
"""

from __future__ import annotations

import asyncio
import logging
import random
from dataclasses import dataclass, field
from typing import List

from .base import BaseSource

logger = logging.getLogger(__name__)

# Boss 直聘城市编码（与 m.zhipin.com 的 city 参数一致）
CITY_CODES = {
    "北京": "101010100",
    "上海": "101020100",
    "广州": "101280100",
    "深圳": "101280600",
    "杭州": "101210100",
    "苏州": "101190400",
    "郑州": "101180100",
    "济南": "101120100",
    "青岛": "101120200",
    "南京": "101190100",
    "成都": "101270100",
    "武汉": "101200100",
    "西安": "101110100",
}

# Boss 搜索 API（移动端 H5）
SEARCH_API_PATH = "/wapi/zpgeek/search/joblist.json"

# Boss 岗位详情卡片 API（移动端 H5）—— 用搜索返回的 securityId + lid 调用
DETAIL_API_PATH = "/wapi/zpgeek/job/card.json"

# CDP 端点（用户启动 Chrome 时指定的 --remote-debugging-port）
DEFAULT_CDP_URL = "http://127.0.0.1:9222"


@dataclass
class BossJobDetail:
    """Boss 岗位详情（来自 /wapi/zpgeek/job/card.json）。"""

    encrypt_job_id: str
    job_name: str
    post_description: str       # JD 正文
    city_name: str
    experience_name: str        # "1-3 年" / "经验不限" 等
    degree_name: str            # "本科" / "大专" 等
    job_labels: List[str] = field(default_factory=list)
    salary_desc: str = ""
    brand_name: str = ""        # 公司名（搜索 API 里没有）
    address: str = ""
    boss_name: str = ""
    boss_title: str = ""
    raw: dict = field(default_factory=dict)


@dataclass
class BossJob:
    """Boss 一条岗位的结构化表示。"""

    job_name: str
    salary_desc: str
    city: str
    keyword: str
    encrypt_job_id: str
    skills: List[str] = field(default_factory=list)
    job_labels: List[str] = field(default_factory=list)
    boss_name: str = ""
    boss_title: str = ""
    boss_cert: int = 0  # 3 = 已认证企业 boss
    raw: dict = field(default_factory=dict)

    @property
    def url(self) -> str:
        """构造 PC 站详情页 URL（统一对外暴露的"内容 URL"）。"""
        return f"https://www.zhipin.com/job_detail/{self.encrypt_job_id}.html"

    @property
    def is_likely_noise(self) -> bool:
        """快速垃圾岗启发式：日结/项目外包/校招实习等。"""
        s = self.salary_desc
        if "元/天" in s or "元/小时" in s:
            return True
        labels = "".join(self.job_labels)
        if "校招" in self.job_name or "校招" in labels:
            return True
        if "实习" in self.job_name and "转正" not in self.job_name:
            return True
        # 发布人头衔包含明显非技术的关键词（"收展员" = 保险代理人 等）
        if self.boss_title and any(
            x in self.boss_title for x in ["收展", "保险", "代理", "招聘专员"]
        ):
            # 注意：HR / 招聘专员也算正常发布岗位的人，这里只把"收展/保险/代理"列噪音
            if any(x in self.boss_title for x in ["收展", "保险", "代理"]):
                return True
        return False


class BossSource(BaseSource):
    """
    Boss 直聘招聘源，通过 CDP 接管真实 Chrome 抓取 m.zhipin.com 搜索 API。

    用法
    ----
    >>> src = BossSource(
    ...     cities=["杭州", "苏州", "济南", "青岛", "郑州"],
    ...     keywords=["AI应用开发", "大模型", "LangChain", "Agent"],
    ... )
    >>> urls = await src.fetch_new_urls()           # 走 BaseSource 契约
    >>> jobs = await src.fetch_jobs_structured()    # v3.0 Agent 用
    """

    source_type: str = "boss_zhipin"

    def __init__(
        self,
        cities: List[str],
        keywords: List[str],
        pages_per_query: int = 1,
        cdp_url: str = DEFAULT_CDP_URL,
        filter_noise: bool = True,
        min_delay: float = 0.6,
        max_delay: float = 1.4,
        max_retries: int = 2,
    ):
        if not cities:
            raise ValueError("BossSource: cities 不能为空")
        if not keywords:
            raise ValueError("BossSource: keywords 不能为空")

        unknown_cities = [c for c in cities if c not in CITY_CODES]
        if unknown_cities:
            raise ValueError(
                f"BossSource: 未知城市 {unknown_cities}；"
                f"已支持: {list(CITY_CODES.keys())}"
            )

        self.cities = cities
        self.keywords = keywords
        self.pages_per_query = pages_per_query
        self.cdp_url = cdp_url
        self.filter_noise = filter_noise
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.max_retries = max_retries

        # 抓取后缓存一份完整结构化数据，BaseSource 契约只返回 URL，
        # 但 v3.0 Agent / scripts 可以直接读这个属性拿到富数据。
        self._last_jobs: List[BossJob] = []

    @property
    def last_jobs(self) -> List[BossJob]:
        return list(self._last_jobs)

    # ------------------------------------------------------------------
    # BaseSource 契约
    # ------------------------------------------------------------------
    async def fetch_new_urls(self) -> List[str]:
        jobs = await self.fetch_jobs_structured()
        # 去重保序
        seen, urls = set(), []
        for j in jobs:
            if j.url in seen:
                continue
            seen.add(j.url)
            urls.append(j.url)
        return urls

    # ------------------------------------------------------------------
    # v3.0 富接口：结构化岗位
    # ------------------------------------------------------------------
    async def fetch_jobs_structured(self) -> List[BossJob]:
        """
        抓取 cities × keywords 笛卡尔积下所有岗位。

        返回去噪后的 BossJob 列表（如果 filter_noise=True）。
        """
        from playwright.async_api import async_playwright

        all_jobs: List[BossJob] = []

        async with async_playwright() as p:
            try:
                browser = await p.chromium.connect_over_cdp(self.cdp_url)
            except Exception as e:
                logger.error(
                    f"BossSource: 无法连接 CDP 端口 {self.cdp_url}。"
                    f"请确认 Chrome 已用 --remote-debugging-port=9222 启动。错误: {e}"
                )
                return []

            target_page = await self._get_or_create_zhipin_page(browser)

            for city in self.cities:
                for keyword in self.keywords:
                    for page_num in range(1, self.pages_per_query + 1):
                        jobs = await self._fetch_with_retry(
                            target_page,
                            city=city,
                            keyword=keyword,
                            page_num=page_num,
                        )
                        all_jobs.extend(jobs)
                        # 节流：每次请求间随机延迟，缓解 code 37
                        await asyncio.sleep(
                            random.uniform(self.min_delay, self.max_delay)
                        )

            # 断开 CDP（不关用户的 Chrome 窗口）
            try:
                await browser.close()
            except Exception:
                pass

        # 去噪
        if self.filter_noise:
            kept = [j for j in all_jobs if not j.is_likely_noise]
            noisy = len(all_jobs) - len(kept)
            logger.info(
                f"BossSource: 抓到 {len(all_jobs)} 条，过滤噪音 {noisy} 条，保留 {len(kept)} 条"
            )
        else:
            kept = all_jobs

        self._last_jobs = kept
        return kept

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------
    @staticmethod
    async def _get_or_create_zhipin_page(browser):
        """找一个 zhipin.com 已打开的页面，没有就新建。"""
        for ctx in browser.contexts:
            for pg in ctx.pages:
                if "zhipin.com" in pg.url:
                    return pg
        ctx = browser.contexts[0] if browser.contexts else await browser.new_context()
        pg = await ctx.new_page()
        await pg.goto("https://m.zhipin.com", wait_until="domcontentloaded")
        return pg

    async def _fetch_with_retry(
        self,
        page,
        *,
        city: str,
        keyword: str,
        page_num: int,
    ) -> List[BossJob]:
        """带重试 + 退避的查询封装。code 37 视为可重试。"""
        last_status = "unknown"
        for attempt in range(self.max_retries + 1):
            jobs, status = await self._fetch_one_query(
                page, city=city, keyword=keyword, page_num=page_num
            )
            if status == "ok":
                return jobs
            last_status = status
            if attempt < self.max_retries:
                backoff = (1.5 ** attempt) + random.uniform(0.3, 0.9)
                logger.info(
                    f"BossSource: {city}/{keyword}/p{page_num} {status} → "
                    f"{backoff:.1f}s 后重试 ({attempt + 1}/{self.max_retries})"
                )
                await asyncio.sleep(backoff)
        logger.warning(
            f"BossSource: {city}/{keyword}/p{page_num} 重试 {self.max_retries} 次后仍失败 ({last_status})"
        )
        return []

    async def _fetch_one_query(
        self,
        page,
        *,
        city: str,
        keyword: str,
        page_num: int = 1,
    ) -> tuple[List[BossJob], str]:
        """
        单次查询：1 个城市 + 1 个关键词 + 1 页。

        返回 (jobs, status)；status 取值：
          - "ok"        正常拿到数据（即使空列表）
          - "code_37"   触发 Boss 风控，可重试
          - "code_other"  其他业务错误
          - "fetch_error" 网络 / JS 异常
        """
        import urllib.parse

        city_code = CITY_CODES[city]
        api_url = (
            f"{SEARCH_API_PATH}?query={urllib.parse.quote(keyword)}"
            f"&city={city_code}&page={page_num}"
        )

        try:
            result = await page.evaluate(
                """async (url) => {
                    const r = await fetch(url, { credentials: "include" });
                    return await r.json();
                }""",
                api_url,
            )
        except Exception as e:
            logger.error(
                f"BossSource: {city}/{keyword}/p{page_num} fetch 失败: {e}"
            )
            return [], "fetch_error"

        code = result.get("code")
        if code != 0:
            msg = result.get("message")
            logger.warning(
                f"BossSource: {city}/{keyword}/p{page_num} 业务码非 0: "
                f"code={code} message={msg}"
            )
            return [], "code_37" if code == 37 else "code_other"

        job_list = result.get("zpData", {}).get("jobList", []) or []
        jobs: List[BossJob] = []
        for raw in job_list:
            try:
                jobs.append(
                    BossJob(
                        job_name=raw.get("jobName", "").strip(),
                        salary_desc=raw.get("salaryDesc", "").strip(),
                        city=city,
                        keyword=keyword,
                        encrypt_job_id=raw.get("encryptJobId", ""),
                        skills=list(raw.get("skills", []) or []),
                        job_labels=list(raw.get("jobLabels", []) or []),
                        boss_name=raw.get("bossName", ""),
                        boss_title=raw.get("bossTitle", ""),
                        boss_cert=int(raw.get("bossCert", 0) or 0),
                        raw=raw,
                    )
                )
            except Exception as e:
                logger.warning(f"BossSource: 跳过一条解析失败的岗位: {e}")

        logger.info(
            f"BossSource: {city}/{keyword}/p{page_num} → {len(jobs)} 条"
        )
        return jobs, "ok"

    # ------------------------------------------------------------------
    # 详情 API（P4'：富数据补全）
    # ------------------------------------------------------------------
    async def fetch_job_details(
        self,
        security_id_lid_pairs: List[tuple],
    ) -> List[BossJobDetail]:
        """
        批量抓岗位详情。

        Args:
            security_id_lid_pairs: [(security_id, lid), ...] 序列。
                security_id 和 lid 都来自搜索 API 返回的 jobList[*]，
                调详情接口必须配对，否则会被风控。

        返回去重后的 BossJobDetail 列表（按抓取顺序）。失败的条目跳过。
        """
        from playwright.async_api import async_playwright

        details: List[BossJobDetail] = []

        async with async_playwright() as p:
            try:
                browser = await p.chromium.connect_over_cdp(self.cdp_url)
            except Exception as e:
                logger.error(
                    f"BossSource: 无法连接 CDP 端口 {self.cdp_url}。错误: {e}"
                )
                return []

            page = await self._get_or_create_zhipin_page(browser)

            for i, (security_id, lid) in enumerate(security_id_lid_pairs, 1):
                detail = await self._fetch_one_detail_with_retry(
                    page, security_id=security_id, lid=lid, idx=i,
                    total=len(security_id_lid_pairs),
                )
                if detail is not None:
                    details.append(detail)
                await asyncio.sleep(random.uniform(self.min_delay, self.max_delay))

            try:
                await browser.close()
            except Exception:
                pass

        return details

    async def _fetch_one_detail_with_retry(
        self,
        page,
        *,
        security_id: str,
        lid: str,
        idx: int,
        total: int,
    ) -> "BossJobDetail | None":
        last_status = "unknown"
        for attempt in range(self.max_retries + 1):
            detail, status = await self._fetch_one_detail(
                page, security_id=security_id, lid=lid, idx=idx, total=total
            )
            if status == "ok":
                return detail
            last_status = status
            if attempt < self.max_retries:
                backoff = (1.5 ** attempt) + random.uniform(0.3, 0.9)
                logger.info(
                    f"BossSource detail [{idx}/{total}] {status} → "
                    f"{backoff:.1f}s 后重试 ({attempt + 1}/{self.max_retries})"
                )
                await asyncio.sleep(backoff)
        logger.warning(
            f"BossSource detail [{idx}/{total}] 重试 {self.max_retries} 次后仍失败 ({last_status})"
        )
        return None

    async def _fetch_one_detail(
        self,
        page,
        *,
        security_id: str,
        lid: str,
        idx: int,
        total: int,
    ) -> tuple["BossJobDetail | None", str]:
        """调一次详情 API。返回 (BossJobDetail, status)。"""
        import urllib.parse

        api_url = (
            f"{DETAIL_API_PATH}?securityId={urllib.parse.quote(security_id)}"
            f"&lid={urllib.parse.quote(lid)}"
        )

        try:
            result = await page.evaluate(
                """async (url) => {
                    const r = await fetch(url, { credentials: "include" });
                    return await r.json();
                }""",
                api_url,
            )
        except Exception as e:
            logger.error(f"BossSource detail [{idx}/{total}] fetch 失败: {e}")
            return None, "fetch_error"

        code = result.get("code")
        if code != 0:
            msg = result.get("message")
            logger.warning(
                f"BossSource detail [{idx}/{total}] 业务码非 0: "
                f"code={code} message={msg}"
            )
            return None, "code_37" if code == 37 else "code_other"

        card = result.get("zpData", {}).get("jobCard", {}) or {}
        if not card:
            logger.warning(f"BossSource detail [{idx}/{total}] jobCard 为空")
            return None, "empty"

        detail = BossJobDetail(
            encrypt_job_id=card.get("encryptJobId", ""),
            job_name=(card.get("jobName") or "").strip(),
            post_description=(card.get("postDescription") or "").strip(),
            city_name=card.get("cityName", ""),
            experience_name=card.get("experienceName", ""),
            degree_name=card.get("degreeName", ""),
            job_labels=list(card.get("jobLabels", []) or []),
            salary_desc=card.get("salaryDesc", ""),
            brand_name=card.get("brandName", ""),
            address=card.get("address", ""),
            boss_name=card.get("bossName", ""),
            boss_title=card.get("bossTitle", ""),
            raw=card,
        )

        # 紧凑日志：JD 长度 + 公司，让批量跑时能看到进度
        jd_len = len(detail.post_description)
        brand = (detail.brand_name or "?")[:14]
        logger.info(
            f"BossSource detail [{idx}/{total}] ✅ {brand} | "
            f"{detail.job_name[:25]} | JD {jd_len} 字"
        )
        return detail, "ok"
