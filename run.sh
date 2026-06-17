#!/bin/bash
# ============================================================
# AI Collector v1.1 — daily run wrapper
# ============================================================
# Usage:
#   ./run.sh                    # 跑默认流水线（每天定时点用）
#   ./run.sh --batch 10         # 一次跑 10 条 PENDING（手动追赶用）
#
# Crontab example (macOS / Linux):
#   0 9 * * * /Users/minjie/shangguigu/ai_collector_project/run.sh \
#             >> /Users/minjie/shangguigu/ai_collector_project/logs/cron.log 2>&1
#
# 设计：
# - 切换到项目目录（避免 cron 把 cwd 设成 /）
# - 激活共享 venv（在 ../.venv，不污染项目目录）
# - 失败时返回非零退出码（cron 任务监控可识别）
# ============================================================

set -e  # 任何命令失败都立刻退出

# 项目根（脚本所在目录）
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

# venv 在父目录（多个 shangguigu 子项目共享）
VENV_DIR="$(cd "$PROJECT_DIR/.." && pwd)/.venv"

if [ ! -d "$VENV_DIR" ]; then
    echo "[run.sh] ERROR: venv not found at $VENV_DIR" >&2
    exit 1
fi

# 激活 venv
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

# 时间戳，便于在 cron.log 里区分多次运行
echo ""
echo "============================================================"
echo "[run.sh] $(date '+%Y-%m-%d %H:%M:%S') starting (mode: ${1:-default})"
echo "============================================================"

# 解析参数：默认走 main.py；--batch N 走 run_batch.py
if [ "${1:-}" = "--batch" ]; then
    N="${2:-10}"
    python run_batch.py "$N"
else
    python main.py
fi

echo ""
echo "[run.sh] $(date '+%Y-%m-%d %H:%M:%S') finished"
