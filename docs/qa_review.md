# Q&A Review · 错题本 · 面试自测库

> **用法**：每次学完做自测题，把题目 + 我答的 + 标准答案 + 易错点都记这里。
> **面试前 1-2 周**：按主题筛选标签，5 分钟扫一遍错过的题。
> **判分**：✅ 答对  🟡 方向对/不完整  ❌ 答错

## 标签索引

- `#langchain` `#langgraph` `#rag` `#mcp` `#llm-基础` `#agent` `#prompt` `#面试常见`

---

## 2026-06-29 周一 · LangChain day01 入门

### Q1: LangChain 是什么？ `#langchain` `#面试常见`

**我答（✅）**：
> "LangChain 是一个用于开发由大语言模型驱动的开发框架，类似于 Java 有 Spring，Python 有 Django。"

**标准答案 / 完整版**：
> LangChain 是 2022 年由 Harrison Chase 发起的开源框架，用于开发由 LLM 驱动的应用程序。
> 它把 LLM 调用、Prompt、Memory、RAG、Tool 调用这些零散环节**串成链**——"Chain" 的命名就是这意思。
> 类比：**LangChain 之于 LLM，就像 Spring 之于 Java，Django 之于 Python**。

**加分点**：
- 比 ChatGPT 早 1 个月发布（2022 年 10 月，ChatGPT 是 11 月）——创始人有眼光，先机优势
- 同生态还有 LangGraph（编排）/ LangSmith（观测）/ Deep Agents

---

### Q2: 为什么有 LLM 还要 LangChain？ `#langchain` `#面试常见`

**我答（🟡）**：
> "因为 LangChain 可以更快地自定义开发。"

**为什么扣分**：方向对，但太笼统，面试官追问"具体哪里更快"就卡住。

**标准答案（3 条，记忆口诀：省事 + 通用 + 现成）**：
1. **简化开发难度**：专注业务逻辑，不用手写底层（重试、解析、错误处理）
2. **学习成本低 / 模型可移植**：换模型不用换代码——OpenAI / Claude / DeepSeek / GLM 调用方式统一
3. **现成的链式组装**：RAG / Agent / Memory 都有现成轮子，不用从 0 写

**加分点**：能讲出自己项目里的真实感受。
> "我在 ai_collector_project 里用 LangChain 切换 GLM-4 和本地 ollama 时，只改了配置，没改业务代码——这就是第 2 条的实际收益。"

---

### Q3: LangChain 架构里哪个包是入口？ `#langchain` `#包结构`

**我答（❌）**：
> "langchain-core"

**为什么错**：被名字 "core" 误导了。

**标准答案**：**`langchain`**（就这一个词，没后缀）

**完整对比**：

| 包 | 角色 | 类比 |
|---|---|---|
| **langchain** | **主入口，包含构建 LLM 应用所需的所有实现** | Django 主包（开箱即用） |
| langchain-core | 只定义**接口和抽象**，没有具体实现，给开发者写自定义组件用 | Python `abc` 模块 |
| langchain-text-splitters | 文档处理（分块） | — |
| langchain-mcp-adapters | MCP 工具适配 | — |
| langchain-tests | 集成包测试套件 | — |
| langchain-classic | 遗留实现 | — |

**为什么这是常见坑**：很多框架里 "core" 就是主入口（`spring-core` / `aspnetcore`），但 LangChain v0.1 大重构后**故意把 core 留给抽象层**，这是设计选择。

---

### Q4 (Step 1 心里画): LangChain 4 大核心模块？ `#langchain` `#面试常见`

**标准答案**：**Model I/O / Chains / Retrieval / Agents**

**翻译成人话**：
- **Model I/O** = 怎么调用大模型（输入→模型→输出）
- **Chains** = 把多个步骤"串起来"（LangChain 名字"Chain"的由来）
- **Retrieval** = RAG 用的检索能力（向量化、向量库、查找）
- **Agents** = 让 LLM 自己决定下一步干啥（Function Calling / Tool 调用）

**项目对应**（你 ai_collector_project v3.0 里）：
- Model I/O ✓ 调 chat 模型
- Retrieval ✓ bge-m3 + Milvus 做 RAG
- Agents ✓ LangGraph 反思决策
- Chains ✗ LangGraph 出来后大多场景被 graph 替代，少显式用

---

