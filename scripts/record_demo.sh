#!/usr/bin/env bash
# 录一段 v3.0 求职 Agent 的 30-60 秒 demo（asciinema 形式）
# 用法：bash scripts/record_demo.sh "杭州 AI Agent 开发 1-3 年"
#
# 依赖：
#   - asciinema（macOS: brew install asciinema）
#   - 已跑过 scripts/ingest_boss_jobs.py + index_final_results.py（向量库要在）
#   - .env 已配 LLM 凭证（火山引擎 Coding Plan）
#
# 录完后：
#   1. 文件输出在 docs/assets/demo.cast
#   2. 上传到 asciinema.org 拿在线链接（asciinema upload docs/assets/demo.cast）
#   3. 或本地转 GIF：asciicast2gif docs/assets/demo.cast docs/assets/demo.gif
#   4. README 里嵌入 [![asciicast](url)](url)
set -euo pipefail

QUERY="${1:-杭州 AI Agent 开发 1-3 年 15K+}"
OUT="docs/assets/demo.cast"

if ! command -v asciinema &>/dev/null; then
    echo "❌ 需要 asciinema：brew install asciinema"
    exit 1
fi

mkdir -p docs/assets

echo "📹 准备录 demo，query: $QUERY"
echo "    输出: $OUT"
echo "    录制开始后会自动跑 find_jobs.py，结束后按 Ctrl+D 退出 shell"
echo ""

# asciinema 3.x 参数：
#   --idle-time-limit 2   长等待压到 2 秒（旧版叫 --max-wait）
#   -t                    asciinema.org 上显示的标题
#   -c                    要录的命令（旧版叫 --command，3.x 仍支持长写法）
#   --overwrite           已有同名文件直接覆盖（重录方便）
asciinema rec \
    --overwrite \
    --idle-time-limit 2 \
    -t "v3.0 求职 Agent demo: $QUERY" \
    -c "/Users/minjie/shangguigu/.venv/bin/python scripts/find_jobs.py '$QUERY'" \
    "$OUT"

echo ""
echo "✅ 录制完成: $OUT"
echo ""
echo "下一步选其一："
echo "  上传:        asciinema upload $OUT"
echo "  转 GIF:      brew install agg && agg $OUT docs/assets/demo.gif"
echo "  本地回放:    asciinema play $OUT"
