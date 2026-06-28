# Study Log · AI 转型 11+1 周

每天 3 行：学了啥 / 新点 / 没懂点。

格式：`YYYY-MM-DD 周X · 主题 · <3 行>`

---

## 2026-06-28 周日 · 启动日 · LLM 演化

- 学了啥：跳过阶段13/day_01 13 集纯理论视频，用 `docs/llm_cheatsheet.md` 5 分钟扫完替代
- 新点：GPT-3 的 in-context learning 就是我写 prompt 塞示例那套——之前不知道有正式名字
- 没懂点：今天没写代码，无技术卡点；唯一的"没懂"是工程通用约定（什么是脚手架），已记到 user profile

明天 (6/29) 进 LangChain day01 前 5 集 + docx 精读 3 节。

---

## 2026-06-29 周一 · LangChain day01 入门 · 总 1h

- 学了啥：LangChain 4 大核心模块（Model I/O / Chains / Retrieval / Agents），
  类比 Spring 之于 Java——把 LLM 应用开发的零散环节串成链。
- 新点：langchain（主入口，有实现） vs langchain-core（只定义抽象接口）
  这俩别搞混；换模型不重写代码就是 LangChain 第 2 大价值。
- 没懂点：今天还没动代码，明天 6/30 看 6-11 集会讲消息构造和异步调用，
  到时候真上手肯定会卡。

**自测 3 题成绩 1.5/3**：
- ✅ LangChain 是什么 + 类比 Spring/Django
- 🟡 为什么需要 LangChain（说出方向但忘了 3 条标准答案：省事/通用/现成）
- ❌ 主入口包是 `langchain` 不是 `langchain-core`（core 是抽象层）

---
