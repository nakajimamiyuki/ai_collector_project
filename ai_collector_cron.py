#!/usr/bin/env python3
"""
ai_collector_cron.py — Hermes cron entrypoint for ai_collector_project.

跑完一次完整流水线后，输出一份**精简摘要**（不超过 20 行）。
Hermes 的 no_agent cron 会把这份 stdout 直接发到 origin。

详细日志仍然落在 logs/pipeline.log，需要时可以去看。

寂静策略：如果这次运行没有任何新数据（new=0, collected=0, processed=0, FAILED 没变化），
打印 "[SILENT]"，让 Hermes 抑制推送。
"""
import os
import sys
import io
import logging
import asyncio
from contextlib import redirect_stdout, redirect_stderr

# 切到项目目录（cron 默认 cwd 不一定是这里）
PROJECT_DIR = "/Users/minjie/shangguigu/ai_collector_project"
os.chdir(PROJECT_DIR)
sys.path.insert(0, PROJECT_DIR)


def main():
    # 把所有 stdout/stderr 吞掉，避免详细日志爆终端
    silenced = io.StringIO()
    with redirect_stdout(silenced), redirect_stderr(silenced):
        # 这里再 import，避免一启动就刷到 stdout
        from main import AIPipeline
        from src.db_manager import DBManager

        # 跑前的状态，用来对比
        db = DBManager()
        before = db.get_run_summary()

        pipeline = AIPipeline(headless=True)
        try:
            asyncio.run(pipeline.run())
        except Exception as e:
            # 执行失败不要静默：直接打印错误让 Hermes 看到
            print(f"⚠️ AI Collector cron failed: {e}", flush=True)
            sys.exit(1)

        after = db.get_run_summary()

    # 计算增量
    before_completed = before["by_status"].get("COMPLETED", 0)
    after_completed = after["by_status"].get("COMPLETED", 0)
    delta_completed = after_completed - before_completed

    before_pending = before["by_status"].get("PENDING", 0)
    after_pending = after["by_status"].get("PENDING", 0)
    delta_pending = after_pending - before_pending  # >0 = 新发现

    after_failed = after["by_status"].get("FAILED", 0)
    after_collected = after["by_status"].get("COLLECTED", 0)

    # 寂静：什么都没发生
    if delta_completed == 0 and delta_pending == 0 and after_failed == 0 and after_collected == 0:
        print("[SILENT]")
        return

    # 拿最近完成的 3 条标题，做"今日要点"
    import sqlite3, json
    conn = sqlite3.connect(db.db_path)
    cur = conn.cursor()
    cur.execute(
        "SELECT structured_json FROM final_results ORDER BY id DESC LIMIT 3"
    )
    recent_titles = []
    for (sj,) in cur.fetchall():
        try:
            t = json.loads(sj).get("title") or ""
            recent_titles.append(t[:55])
        except Exception:
            pass
    conn.close()

    # 输出（≤ 20 行）
    print("📡 AI Collector 每日报告")
    print("")
    if delta_pending > 0:
        print(f"🆕 新发现：{delta_pending} 个视频")
    if delta_completed > 0:
        print(f"✅ 本次处理：{delta_completed} 条")
    if after_failed > 0:
        print(f"⚠️ 失败累计：{after_failed} 条（下次自动重试）")
    print(
        f"📊 数据库：COMPLETED {after_completed} / "
        f"PENDING {after_pending} / FAILED {after_failed}"
    )
    if recent_titles:
        print("")
        print("📰 最近入库：")
        for t in recent_titles:
            print(f"  • {t}")
    print("")
    print(f"📁 详情见 logs/pipeline.log")


if __name__ == "__main__":
    main()
