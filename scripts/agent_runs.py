"""Agent 运行记录 + Bad Case 管理 CLI。

子命令：
    list    [--status good|bad|unreviewed] [--limit 50]   列出运行记录
    show    <id>                                          看一条详情
    mark    <id> [--status ...] [--root-cause ...] [--fix-commit ...] [--fix-notes ...]
                                                          人工 review 后打标
    replay  [--status bad] [--limit 5]                    选定一批记录 replay
    stats                                                 统计 unreviewed/good/bad

用法示例：
    python scripts/agent_runs.py list
    python scripts/agent_runs.py list --status bad
    python scripts/agent_runs.py show 3
    python scripts/agent_runs.py mark 3 --status bad --root-cause filter_too_strict
    python scripts/agent_runs.py replay --status bad --limit 3
    python scripts/agent_runs.py stats
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# 见 find_jobs.py：必须在 import 任何依赖 OpenMP 的库前设置
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env")

from src.agent.bad_case_store import VALID_STATUSES, BadCaseStore


# ----------------------------------------------------------------------
# 命令实现
# ----------------------------------------------------------------------
def cmd_list(args, store: BadCaseStore) -> int:
    runs = store.list(status=args.status, limit=args.limit)
    if not runs:
        print("（无记录）")
        return 0

    # 表头
    print(f"{'ID':>4} | {'when':<19} | {'cnt':>3} | {'sec':>5} | "
          f"{'refl':>4} | {'status':<11} | {'cause':<22} | query")
    print("-" * 110)
    for r in runs:
        q = r.query if len(r.query) <= 40 else r.query[:37] + "..."
        cause = r.root_cause if len(r.root_cause) <= 22 else r.root_cause[:19] + "..."
        # status 着色
        st = r.status
        status_disp = {
            "bad": f"\033[31m{st:<11}\033[0m",
            "good": f"\033[32m{st:<11}\033[0m",
            "unreviewed": f"\033[33m{st:<11}\033[0m",
        }.get(st, f"{st:<11}")
        print(
            f"{r.id:>4} | {r.run_at[:19]:<19} | {r.result_count:>3} | "
            f"{r.elapsed_seconds:>5.1f} | {r.reflect_rounds:>4} | "
            f"{status_disp} | {cause:<22} | {q}"
        )
    return 0


def cmd_show(args, store: BadCaseStore) -> int:
    run = store.get(args.id)
    if not run:
        print(f"❌ 没有 id={args.id} 的记录")
        return 1

    print(f"# Run #{run.id}")
    print()
    print(f"- when:        {run.run_at}")
    print(f"- query:       {run.query}")
    print(f"- result_count {run.result_count}")
    print(f"- elapsed:     {run.elapsed_seconds:.1f}s")
    print(f"- reflect:     {run.reflect_rounds}")
    print(f"- status:      {run.status}")
    print(f"- root_cause:  {run.root_cause or '-'}")
    print(f"- fix_commit:  {run.fix_commit or '-'}")
    print(f"- fix_notes:   {run.fix_notes or '-'}")
    print()
    print("## Trace")
    import json
    try:
        trace = json.loads(run.trace_json or "[]")
        for line in trace:
            print(f"  · {line}")
    except json.JSONDecodeError:
        print(f"  (无法解析 trace_json: {run.trace_json[:200]})")
    print()
    print("## Final Report")
    print(run.final_report or "(空)")
    return 0


def cmd_mark(args, store: BadCaseStore) -> int:
    ok = store.mark(
        args.id,
        status=args.status,
        root_cause=args.root_cause,
        fix_commit=args.fix_commit,
        fix_notes=args.fix_notes,
    )
    if not ok:
        print(f"❌ 未更新（id={args.id} 不存在，或没有传任何字段）")
        return 1
    run = store.get(args.id)
    if run:
        print(f"✅ Run #{run.id} 已更新")
        print(f"   status={run.status}")
        print(f"   root_cause={run.root_cause or '-'}")
        print(f"   fix_commit={run.fix_commit or '-'}")
    return 0


def cmd_replay(args, store: BadCaseStore) -> int:
    """选定一批记录，用同一个 query 重新跑一遍 Agent，对比新结果。

    新结果会作为一条新记录写入 agent_runs.db，老记录原样保留。
    """
    runs = store.list(status=args.status, limit=args.limit)
    if not runs:
        print(f"（没有 status={args.status} 的记录可 replay）")
        return 0

    # 延迟 import，省启动时间 + 让 list 命令也能在无 ollama/milvus 环境下跑
    from src.agent import find_jobs

    print(f"🔁 准备 replay {len(runs)} 条记录\n")
    summary: list[tuple[int | None, str, int, int]] = []
    for old in runs:
        print(f"=== Replay Run #{old.id} ===")
        print(f"    query: {old.query}")
        print(f"    旧结果: result_count={old.result_count} status={old.status}")
        try:
            result = find_jobs(old.query)
        except Exception as e:
            print(f"    ❌ replay 失败: {e}\n")
            summary.append((old.id, "ERROR", old.result_count, -1))
            continue

        reflect_rounds = len([t for t in result.trace if "reflect" in t])
        new_count = len(result.filtered_jobs)
        new_id = store.record_run(
            query=old.query,
            result_count=new_count,
            elapsed_seconds=result.elapsed_seconds,
            reflect_rounds=reflect_rounds,
            trace=result.trace,
            final_report=result.final_report,
        )
        new_run = store.get(new_id)
        new_status = new_run.status if new_run else "?"
        delta = new_count - old.result_count
        arrow = "↑" if delta > 0 else ("↓" if delta < 0 else "=")
        print(
            f"    新结果: id={new_id} result_count={new_count} ({arrow}{abs(delta)}) "
            f"status={new_status}\n"
        )
        summary.append((old.id, new_status, old.result_count, new_count))

    # 汇总
    print("─" * 60)
    print(f"{'old_id':>6} | {'new_status':<11} | {'old_cnt':>7} | {'new_cnt':>7}")
    print("-" * 60)
    for old_id, st, old_cnt, new_cnt in summary:
        new_cnt_disp = str(new_cnt) if new_cnt >= 0 else "ERR"
        print(f"{old_id:>6} | {st:<11} | {old_cnt:>7} | {new_cnt_disp:>7}")
    fixed = sum(
        1
        for _, st, oc, nc in summary
        if st == "good" and oc == 0 and nc > 0
    )
    if fixed:
        print(f"\n✅ {fixed} 条之前零结果的 query 这次有命中了。")
    return 0


def cmd_stats(args, store: BadCaseStore) -> int:
    stats = store.stats()
    total = stats["total"]
    print(f"# Agent Runs Stats (total={total})")
    print()
    if not total:
        print("（暂无记录，跑一遍 scripts/find_jobs.py 试试）")
        return 0
    for st in ("unreviewed", "good", "bad"):
        n = stats[st]
        pct = (n / total * 100) if total else 0
        bar = "█" * int(pct / 5)
        print(f"  {st:<11} {n:>4}  {pct:>5.1f}%  {bar}")
    return 0


# ----------------------------------------------------------------------
# main
# ----------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="Agent 运行记录 + Bad Case CLI")
    sub = ap.add_subparsers(dest="cmd", required=True)

    # list
    p = sub.add_parser("list", help="列出运行记录")
    p.add_argument("--status", choices=sorted(VALID_STATUSES))
    p.add_argument("--limit", type=int, default=50)
    p.set_defaults(func=cmd_list)

    # show
    p = sub.add_parser("show", help="看一条详情")
    p.add_argument("id", type=int)
    p.set_defaults(func=cmd_show)

    # mark
    p = sub.add_parser("mark", help="人工 review 后打标")
    p.add_argument("id", type=int)
    p.add_argument("--status", choices=sorted(VALID_STATUSES))
    p.add_argument("--root-cause", dest="root_cause")
    p.add_argument("--fix-commit", dest="fix_commit")
    p.add_argument("--fix-notes", dest="fix_notes")
    p.set_defaults(func=cmd_mark)

    # replay
    p = sub.add_parser("replay", help="选定一批记录 replay")
    p.add_argument(
        "--status",
        choices=sorted(VALID_STATUSES),
        default="bad",
        help="默认 replay 所有 status='bad' 的记录",
    )
    p.add_argument("--limit", type=int, default=5)
    p.set_defaults(func=cmd_replay)

    # stats
    p = sub.add_parser("stats", help="统计 unreviewed/good/bad")
    p.set_defaults(func=cmd_stats)

    args = ap.parse_args()
    store = BadCaseStore()
    sys.exit(args.func(args, store) or 0)


if __name__ == "__main__":
    main()
