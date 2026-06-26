"""
v3.0 求职 Agent CLI 入口。

用法：
    python scripts/find_jobs.py "找北京以外薪资 15K+ 要 LangChain 的 1-3 年 AI 岗"
    python scripts/find_jobs.py "AI 测试 大模型评估岗 适合 2 年传统测试转型"
    python scripts/find_jobs.py "杭州 Agent 开发"  --verbose
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

# macOS 上 milvus-lite 的 faiss 和 numpy/torch 都可能各自链一份 libomp.dylib，
# 同一进程加载多份会触发 OMP Error #15 然后 abort。
# 这个开关让 OpenMP 运行时容忍多份副本（官方 escape hatch）。
# 必须在 import 任何依赖 OpenMP 的库之前设置，所以放在文件最顶部。
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

# 必须在导入 src.agent.* 之前加载 .env（节点构造 LLM 时会读环境变量）
load_dotenv(PROJECT_ROOT / ".env")

from src.agent import find_jobs
from src.agent.bad_case_store import BadCaseStore


def main():
    ap = argparse.ArgumentParser(description="v3.0 求职 Agent")
    ap.add_argument("query", help="自然语言需求")
    ap.add_argument("--verbose", "-v", action="store_true", help="打印 Agent trace")
    ap.add_argument(
        "--no-record",
        action="store_true",
        help="不把这次跑写进 agent_runs.db（默认会写）",
    )
    args = ap.parse_args()

    log_level = logging.INFO if args.verbose else logging.WARNING
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )

    print(f"\n🤖 求职 Agent 启动")
    print(f"📝 你的需求：{args.query}\n")

    result = find_jobs(args.query)

    # 主报告（LLM 生成的 markdown）
    print(result.final_report)

    # 简短统计
    reflect_rounds = len([t for t in result.trace if "reflect" in t])
    result_count = len(result.filtered_jobs)
    print()
    print("─" * 60)
    print(
        f"⏱  Agent 用时 {result.elapsed_seconds:.1f}s · "
        f"反思 {reflect_rounds} 次 · "
        f"过滤剩 {result_count} / {result.filter_stats.get('input', 0)}"
    )

    # F2: 把这次跑落进 agent_runs.db，零结果会自动标 bad
    if not args.no_record:
        try:
            store = BadCaseStore()
            run_id = store.record_run(
                query=args.query,
                result_count=result_count,
                elapsed_seconds=result.elapsed_seconds,
                reflect_rounds=reflect_rounds,
                trace=result.trace,
                final_report=result.final_report,
            )
            run = store.get(run_id)
            status_tag = run.status if run else "?"
            tip = ""
            if status_tag == "bad":
                tip = "  ← 已自动标记 bad，跑 `python scripts/agent_runs.py list --status bad` 复盘"
            print(f"📦 已记录到 agent_runs.db (id={run_id}, status={status_tag}){tip}")
        except Exception as e:
            # 记录失败不应该让 Agent 本身的输出受影响
            print(f"⚠️  记录到 agent_runs.db 失败: {e}")

    # verbose 模式下打印 trace
    if args.verbose:
        print()
        print("Agent Trace:")
        for line in result.trace:
            print(f"  · {line}")


if __name__ == "__main__":
    main()
