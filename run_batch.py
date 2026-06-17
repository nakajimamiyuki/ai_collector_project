"""
临时批跑脚本：把 stage2/stage3 的 max_count 调高，一次处理更多条。
不修改 main.py 默认行为（main.py 还是 3/3，适合每日定时运行）。

用法：
    python run_batch.py 10        # 跑 10 条
    python run_batch.py           # 默认 5 条
"""
import asyncio
import sys

# main.py 里有 AIPipeline 类，直接复用
from main import AIPipeline, logger


async def run_batch(n: int):
    p = AIPipeline()
    logger.info(f"\n>>> BATCH RUN, max_count = {n} <<<\n")

    # 阶段 1: 监控（保留每天的扫描，但不影响 batch 含义；如果只想跑队列里的旧任务可以注释掉）
    new_urls = await p.stage1_monitor()

    # 阶段 2: 采集（提高上限）
    collected = await p.stage2_collect(max_count=n)

    # 阶段 3: LLM（提高上限）
    processed = p.stage3_process(max_count=n)

    logger.info(f"\n=== BATCH SUMMARY ===")
    logger.info(f"  monitor new urls: {new_urls}")
    logger.info(f"  collected:        {collected}")
    logger.info(f"  processed:        {processed}")


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    asyncio.run(run_batch(n))
