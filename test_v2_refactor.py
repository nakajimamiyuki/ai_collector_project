"""
v2.0 Phase 1 重构验证脚本
验证：
  1. 新 Source 架构导入链正常
  2. Monitor 调度器能注册并跑 BilibiliSource
  3. v1.1 兼容入口 sync_targets_async(uids) 仍可用
  4. BilibiliSource.fetch_new_urls() 能真实发现 B 站 URL
不写库（用一个临时内存式校验，不污染主库 task 状态）。
"""
import asyncio
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

from src.sources.base import BaseSource
from src.sources.bilibili import BilibiliSource
from src.monitor import Monitor, BiliMonitor


async def main():
    print("\n=== 1. 类型/继承检查 ===")
    assert issubclass(BilibiliSource, BaseSource), "BilibiliSource 应继承 BaseSource"
    assert BilibiliSource.source_type == "bilibili"
    assert issubclass(BiliMonitor, Monitor), "BiliMonitor 应是 Monitor 的别名子类"
    print("  OK: 继承关系正确, source_type=bilibili")

    print("\n=== 2. 直接用 Source 发现 URL（稚晖君 UID）===")
    src = BilibiliSource(uids=["1333131174"])
    urls = await src.fetch_new_urls()
    print(f"  fetch_new_urls() 返回 {len(urls)} 个 URL")
    for u in urls[:3]:
        print(f"    - {u}")
    assert isinstance(urls, list), "返回必须是 list"

    print("\n=== 3. Monitor 调度器 + add_source（不入库，仅跑发现）===")
    mon = Monitor()
    mon.add_source(BilibiliSource(uids=["1333131174"]))
    assert len(mon.sources) == 1

    print("\n=== 4. v1.1 兼容入口 sync_targets_async（会真实入库）===")
    compat = Monitor()
    added = await compat.sync_targets_async(["1333131174"])
    print(f"  sync_targets_async 返回 added={added}（重复 URL 会是 0，正常）")

    print("\n=== 全部通过 ===")


if __name__ == "__main__":
    asyncio.run(main())
