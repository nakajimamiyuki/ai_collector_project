# experiments/

每天手敲的练习代码放这里。**不开 Cursor / 不 vibe coding，全手敲。**

## 规则

1. 每天一个子目录：`dayNN_主题/`（NN = 学习天数，01 开始）
2. 子目录里至少 1 个 `.py` 文件 + 1 个 `notes.md`（5 行小结：今天学了啥、卡在哪、怎么过的）
3. `git add experiments/dayNN_*` 当天提交，commit message 格式：`exp: dayNN <一句话主题>`
4. 跑代码前在脚本最上面加：
   ```python
   import os
   os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"  # 防 macOS OpenMP abort
   ```

## 跟 src/ 的区别

- `src/`  → 生产代码（ai_collector 项目本体），可以 vibe coding 但要讲清
- `experiments/` → 学习代码，**纯手敲**，烂没关系，重点是肌肉记忆

## 目录索引

| Day | 日期 | 主题 | 状态 |
|---|---|---|---|
| 01 | 2026-06-28 | LLM 演化速查（跳过纯理论视频，docs/llm_cheatsheet.md 替代） | ✅ 文档 only |
| 02 | 2026-06-29 | LangChain day01 前 5 集 | ⏳ 待写 |

往后每天新加一行。
