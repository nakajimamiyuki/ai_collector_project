"""
Monitor —— 信息源调度器 (v2.0)

v1.1 -> v2.0 重构
-----------------
v1.1 时 Monitor（BiliMonitor）自己写死了 B 站抓取逻辑。v2.0 把"如何
抓某个源"下沉到 src/sources/ 下的 BaseSource 子类，Monitor 退化为
一个纯调度器：持有一组 Source，逐个调 fetch_new_urls()，汇总入库。

新增数据源 = 写一个 BaseSource 子类并注册，Monitor / Pipeline 不改。

向后兼容
--------
保留 v1.1 的公共入口签名，main.py 无需改动：
  - await monitor.sync_targets_async(target_uids)
  - monitor.sync_targets(target_uids)
这两个方法仍接受 B 站 UID 列表，内部转交给 BilibiliSource。
"""

import asyncio
import logging
from typing import List, Optional

from src.db_manager import DBManager
from src.sources.base import BaseSource
from src.sources.bilibili import BilibiliSource

logger = logging.getLogger(__name__)


class Monitor:
    """信息源调度器：管理一组 BaseSource，统一发现新 URL 并入库。"""

    def __init__(self, sources: Optional[List[BaseSource]] = None):
        """
        Args:
            sources: BaseSource 实例列表。为 None 时为空，可后续 add_source()。
        """
        self.db = DBManager()
        self.sources: List[BaseSource] = list(sources) if sources else []

    def add_source(self, source: BaseSource) -> None:
        """注册一个信息源。"""
        self.sources.append(source)
        logger.info(f"[Monitor] registered source: {source!r}")

    # ------------------------------------------------------------------
    # 核心调度
    # ------------------------------------------------------------------
    async def run_all_async(self) -> int:
        """
        扫描所有已注册的源，发现的新 URL 入库。
        返回本次新增到队列的任务数。
        """
        if not self.sources:
            logger.warning("[Monitor] no sources registered, nothing to scan.")
            return 0

        total_added = 0
        for source in self.sources:
            try:
                urls = await source.fetch_new_urls()
            except Exception as e:
                logger.error(
                    f"[Monitor] source {source!r} raised unexpectedly: {e}"
                )
                continue
            if urls:
                added = self.db.add_new_urls(urls)
                logger.info(
                    f"[Monitor] {source.source_type}: "
                    f"{len(urls)} urls -> {added} new tasks added."
                )
                total_added += added
        logger.info(f"[Monitor] Sync completed. Total new tasks added: {total_added}")
        return total_added

    # ------------------------------------------------------------------
    # 向后兼容入口（v1.1 签名）—— main.py 仍调这两个
    # ------------------------------------------------------------------
    async def sync_targets_async(self, target_uids) -> int:
        """
        [兼容 v1.1] 接受 B 站 UID 列表，内部用 BilibiliSource 抓取。

        若 Monitor 还没注册任何源，则根据传入的 uids 即时创建一个
        BilibiliSource；若已有源，则忽略 uids 直接跑 run_all_async()。
        """
        if not self.sources and target_uids:
            self.add_source(BilibiliSource(uids=target_uids))
        return await self.run_all_async()

    def sync_targets(self, target_uids) -> int:
        """[兼容 v1.1] 同步版：脚本式调用。"""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.sync_targets_async(target_uids))
        raise RuntimeError(
            "Monitor.sync_targets() called from inside a running event loop. "
            "Use `await monitor.sync_targets_async(uids)` instead."
        )


# ----------------------------------------------------------------------
# 向后兼容别名：旧代码 `from src.monitor import BiliMonitor` 仍可用
# ----------------------------------------------------------------------
class BiliMonitor(Monitor):
    """
    [DEPRECATED] v1.1 的类名，保留为 Monitor 的薄别名以兼容旧调用。
    新代码请直接用 Monitor + BilibiliSource。
    """
    pass
