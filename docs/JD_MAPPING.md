# JD ↔ 项目能力映射表

> 面试前 5 分钟翻这张表，每条 JD 关键词都有对应的"嘴一开就能讲"的项目证据。
> 标记：✅ 已有现成证据 / 🟡 有但需现编故事 / 🔴 没有 / ⬜ 不必要正面回应

更新日期：2026-06-26

---

## 0. 目标 JD（按主投顺序）

| 主投顺序 | 公司 | 岗位 | 薪资 | 经验要求 | 备注 |
|---|---|---|---|---|---|
| 🟢 主投 | 科锐国际 | AI Agent 应用开发工程师 | 15-30K | **经验不限** | 转型期最优解 |
| 🟢 冲刺 | 中科昊萌 | AI Agent 开发工程师（广告投流） | 18-25K | 3-5 年 | 硬门槛：Claude Code + OpenAI harness |
| 🟡 练手 | 杭州智豪千越 | AI Agent 工程师（财务 SaaS） | 10-15K | 3-5 年 | JD 描述跟 v3.0 重合度最高 |

---

## 1. 公共能力（三家都问）

| JD 关键词 | 项目证据 | 话术模板 | 状态 |
|---|---|---|---|
| **Agent 编排 / LangGraph** | `src/agent/graph.py` 5 节点 DAG + conditional_edge 反思循环 | "v3.0 主框架就是 LangGraph，5 个节点：parse_intent → retrieve → filter → reflect → summarize，reflect 用 conditional_edge 实现 0 结果自动换关键词重搜，最多 3 轮" | ✅ |
| **RAG / 向量检索** | `src/rag/`（bge-m3 + Milvus Lite）+ 192 条 JD 索引 | "Embedding 用本地 ollama 跑 bge-m3（1024 维），向量库选 Milvus Lite（单文件零服务，生产可平滑迁 Cluster）；4 query benchmark 召回 A+，最高相似度 0.901" | ✅ |
| **Function Calling / Tool Use** | `src/agent/tools.py` 4 个工具函数 | "Agent 里的 retrieve / filter / skill_gap / salary 解析都是工具函数，节点本身不做业务决策，决策在 graph 编排层" | ✅ |
| **MCP** | `src/mcp_server/ai_collector_mcp.py` 3 个 Tool | "我自己写了一个 MCP server，把岗位库的能力封装成 3 个 Tool 暴露给 Hermes/Claude/Cursor，全部走 stdio 传输；今天还在 Hermes 里实测过查杭州 MCP 相关岗位" | ✅ |
| **Prompt 工程** | `src/agent/prompts.py` 3 个 LLM prompt | "Prompt 我按节点维护，parse_intent / reflect / summarize 各一份，git 走版本控制；规模大可以做个 SQLite + UI 的 prompt registry" | ✅ |
| **Memory** | `src/agent/bad_case_store.py` agent_runs.db | "Memory 我现在做的是长期记忆——每次 Agent 跑完落库，零结果自动 bad，replay 命令做回归。短期对话 memory 当前用 LangGraph state 透传" | ✅ |
| **Bad Case 闭环** | `scripts/agent_runs.py` CLI | "Bad case 我有完整闭环：跑完自动落库 → mark root_cause → replay 验证修好没；这是我从 2 年军工测评带过来的习惯" | ✅ |
| **Python 后端** | 全项目 + FastAPI/Flask 经验 | "v3.0 全 Python，async / sqlite / pytest / GitHub Actions 都跑过，Web 框架 FastAPI 用过；不是科班但工程素养稳" | ✅ |
| **反爬 / 数据采集** | `src/sources/boss_zhipin.py` CDP 接管 Chrome | "Boss 这边是 CDP 接管真实 Chrome 绕 Canvas 反爬，单独 Chrome profile + 9222 调试端口 + 同源 fetch 自动带 cookie，跳过 code 37 风控" | ✅ |
| **测试 / 评测** | 81 单测 + GitHub Actions CI | "项目 81 个 pytest 全离线 mock，CI 每次 push 自动跑；评测是我的舒适区，之前 2 年做军工/航天级 CNAS+CMA" | ✅ |

---

## 2. #1 科锐国际 · AI Agent 应用开发工程师

### JD 关键能力点 → 项目映射

| JD 原文 | 我的证据 | 话术 | 状态 |
|---|---|---|---|
| "Prompt 动态配置 / Tool-use / Memory / 多智能体协作" | LangGraph 5 节点 + agent_runs.db + my_profile.yaml | "Prompt 我用 git 版本化；Tool-use 走 LangGraph 节点；Memory 用 SQLite 持久化做长期；多 Agent 协作我做了单 Agent 的 PoC，v3.2 规划拆 supervisor + 3 sub-agent" | 🟡 多 Agent 还没拆 |
| "**MCP（Model Computing Platform）管理**" | `src/mcp_server/` 3 个 Tool | ⚠️ **先问对方** "贵司说的 MCP 是 Anthropic 的 Model Context Protocol 还是内部的 Model Computing Platform？" 然后顺杆爬 | ✅ |
| "Agent 安全控制" | filter_node 黑名单 + retry/timeout | "我的 filter 节点做了 want_to_avoid 黑名单（防 AI 概念伪装销售岗），节点级 retry 防 LLM 抽风，单条 90s 超时；安全控制最低层我有" | 🟡 没做内容审查 |
| "教育 / 工业场景落地" | （无，求职场景） | "我的 domain 是求职，原理上跟教育对话陪练同构——意图解析 + 工具调用 + 反思 + 反馈闭环；教育场景的 bad case 表会换成'答错题 / 不耐烦 / 跑题'三类" | 🟡 类比迁移 |
| "LangGraph/AgentScope" | LangGraph ✅ / AgentScope ❌ | "LangGraph 是 v3.0 主框架；AgentScope 我读过文档没在生产用，一周内能补上" | 🟡 |
| "性能分析 / 高可用 / 低延迟" | 节流 + 退避 + 缓存 graph 实例 | "Agent 我做了 graph 编译缓存（避免每次 invoke 重建），节流随机 0.6-1.4s + 指数退避（1.5^attempt），LangGraph 节点级缓存是 v3.1 路线图的下一项" | 🟡 |
| "POC 到生产上线全流程" | 5 版本演进 + 5 篇 CSDN 博客 | "v1.0→v3.1 五个版本，每版都有博客和 git tag，从'能跑'到'稳定'到'插件化'到'RAG'到'Agent'是完整的工程演进，不是堆功能" | ✅ |

### 投递策略
- 简历项目栏第一行：v3.0 + v3.1 主线，**经验不限** 是这个岗的核心红利
- 期望薪资写 **18-22K**（中位偏下，留谈判空间）
- 面试时主动澄清 MCP 口径，能多展示 30% 信息量

---

## 3. #2 中科昊萌 · AI Agent 开发工程师（广告投流）

### 硬门槛（裸投会被秒拒）

| 门槛 | 状态 | 必须做的事 |
|---|---|---|
| 用过 Claude Code 解决实际问题 | 🟡 准备中 | 今晚装 Claude Code 让它重构 v3.0 某个模块，记 2 个真实体感 |
| 读过 OpenAI harness 文章 | 🔴 待补 | 今晚读完，写 200 字读后感放简历附录 |

### JD 关键能力点 → 项目映射

| JD 原文 | 我的证据 | 话术 | 状态 |
|---|---|---|---|
| "基于 LLM 构建智能投手 Agent" | LangGraph Agent + my_profile.yaml 驱动 | "我的 Agent 现在是 profile 驱动的'智能求职者'，把它换成'智能投手'本质同构——profile 换成账户/预算/历史投放，决策节点改投放动作，反思节点看 ROI 跌幅" | 🟡 类比 |
| "巨量引擎 / 腾讯广告 API 封装为 Function Calling / MCP" | `src/sources/boss_zhipin.py` + MCP server | "API 封装我做过——Boss 那套带 securityId/lid 配对的详情 API 我封装成了 LangGraph 工具节点，签名 / 限流 / retry 都在工具层处理；今天我把岗位库的 3 个工具暴露成了 MCP Server" | ✅ |
| "Agent 工作流编排（类 LangGraph / Dify / 自研）" | LangGraph 主框架 | "LangGraph 重度用户，v3.0 反思决策走 conditional_edge；Dify 用过 Demo 级；自研也能上，但优先用 LangGraph 因为生态更成熟" | ✅ |
| "记忆与决策模块（历史投放 / 素材表现 / 人群反馈）" | bge-m3 RAG + bad_case_store | "记忆我有 RAG（bge-m3 + Milvus），决策有反思机制——Agent 每轮 confidence 低于阈值就走 human-in-the-loop；投流场景的素材库直接复用我的向量库结构" | ✅ |
| "DSP / 竞价 / 流量分发" | 🔴 无 | "DSP 我没做过，但 v3.0 的硬过滤 + 向量排序 + 反思修正这套，跟竞价里的'出价生成 → 实时反馈 → 出价调整'是同构的；上手预计 2 周" | 🔴 类比赌一把 |
| "ROI / 跑量稳定性 / 人工接管率 评测体系" | 81 单测 + bad_case_store + replay | "评测闭环是我的舒适区——之前 2 年做军工/航天级 CNAS+CMA 测评，bad case 表 + replay 命令直接对标 ROI 跑量评测" | ✅ |
| "本科 + 计算机相关 + 3 年以上后端/AI 应用开发" | 本科 + 2 年测评 + 几个月 AI 项目 | **不要硬凑**。诚实写 2 年 + 项目时长，让对方自己评估；用 v3.0+v3.1 项目密度反推开发能力 | 🟡 |

### 投递策略
- 投递前 24 小时**必须**完成：装 Claude Code 真用一次 + 读完 OpenAI harness 写 200 字读后感
- 期望薪资 **20-22K**
- 简历附录放一份"我读 OpenAI harness 的笔记"，规避 HR 第一轮硬筛

---

## 4. #4 千越（亿企赢）· AI Agent 工程师（财务 SaaS）

### JD 关键能力点 → 项目映射

| JD 原文 | 我的证据 | 话术 | 状态 |
|---|---|---|---|
| "**基于 MCP 将业务 API 封装为标准化工具供智能体调用**" | 我自己写了一个 MCP server！3 个 Tool 全跑通 | 这是这个岗位**最纯正的 MCP 用法**，直接给 GitHub demo 链接：`github.com/nakajimamiyuki/ai_collector_project`，让 HR 当场看代码 | ✅ **杀手锏** |
| "Prompt 模板中心 + 按领域版本化" | `src/agent/prompts.py` git 版本化 | "我现在按节点分文件管 Prompt，git 走版本控制；财税这种多领域场景可以做 SQLite + UI 的 prompt registry，按 domain/version/ab_group 三维索引" | 🟡 没做中心化但讲得出来 |
| "落地 RAG：法规库 / 企业知识库" | bge-m3 + Milvus 已落 192 条 JD | "财税法规结构强，embedding 选 bge-m3 中文 SOTA + 1024 维；分块用层级化——条款级精确召回 + 篇章级上下文兜底；我现在 ai_collector 就是这套结构，召回 A+" | ✅ |
| "AI 使用能力：Prompt 设计 / 评测 / Bad Case" | bad_case_store + replay CLI | "Bad case 闭环：SQLite 单表 + status/root_cause/fix_commit 字段，replay 命令批量回放；这习惯从军工测评带过来" | ✅ |
| "AI 辅助开发：Cursor" | 🟡 装了但用得不多 | "Cursor + Claude Code 都用，Cursor 做单点编辑，Claude Code 做长链路重构" | 🟡 投前真用几次 |
| "Function Calling / Tool Use / RAG 至少 2 项" | Function Calling ✅ / Tool Use ✅ / RAG ✅ | "三项都掌握，最熟 RAG——本地 bge-m3 + Milvus + 4 query benchmark 召回 A+" | ✅ |
| "对话链路质量监控" | bad_case_store | "我对每次跑都埋点：result_count / elapsed / reflect_rounds / status / root_cause，零结果自动标 bad；这就是最简单的对话链路质量监控" | ✅ |

### 投递策略
- 薪资偏低（10-15K 杭州中下水位）→ **当练手 + 沟通话术校准**，不是主战场
- 期望薪资 **13-15K**
- 财税领域加一句"我父辈做小生意，家庭背景对开票/记账有直觉"（如果是真的）
- **先投这家**：HR 追问什么 → 调整话术 → 再去打 #1 #2

---

## 5. 自查清单（投简历前 5 分钟）

- [ ] 三家 JD 的"MCP"口径都查清楚了？（#1 可能是内部缩写，#2/#4 是 Anthropic 的）
- [ ] GitHub 仓库公开可访问？仓库顶部 README 30 秒能扫完？
- [ ] qlmanage 导的架构图 PNG 准备好放简历附录？
- [ ] Claude Code + OpenAI harness 投 #2 前的硬门槛？
- [ ] 简历项目栏第一行是"v3.0/v3.1 求职 Agent"，不是 2 年软测？
- [ ] 期望薪资按 #1(18-22K) / #2(20-22K) / #4(13-15K) 分别报？
- [ ] 学历："本科" 不是大厂核心算法岗，AI 应用 / Agent 开发岗 OK？

---

## 6. 真问真答 · 高频追问预演

> **Q1**: "你这个 conditional_edge 的 state 是怎么序列化的？"
> A: LangGraph 默认走 TypedDict，状态在节点间传值不序列化磁盘；持久化我用 SQLite，agent_runs.db 存 trace 是 JSON dumps 的字符串。

> **Q2**: "bge-m3 跟 m3e、bge-large 你怎么选的？"
> A: bge-m3 1024 维中英混合 SOTA，对 AI 技术术语好；m3e 早一代，bge-large 不支持中文细粒度；本地 ollama 跑无成本是关键。

> **Q3**: "chunk size 怎么定的？为什么不用 parent-child retriever？"
> A: 当前数据量 192 条，单条 JD 1-3KB，整段 embed 召回 A+，**故意 YAGNI 没分 chunk**；上千条 + 单条长文档时再上 parent-child。

> **Q4**: "你的 Agent 反思机制为什么不无限循环？"
> A: 反思节点有 `max_retry=3` 硬上限，conditional_edge 根据 state 里的 `retry_count` 决定路由到 retrieve 还是 summarize；这是 LangGraph 推荐的 escape hatch 模式。

> **Q5**: "MCP server 跟普通 HTTP API 有什么本质区别？"
> A: MCP 是协议层标准，规定了 initialize / list_tools / call_tool 三件套和 stdio/SSE 传输；HTTP API 是端点设计，每家不一样；MCP 让客户端**零配置**集成任意 server，类似 LSP 之于 IDE。

> **Q6**: "为什么不用 LangChain Agent，要自己拼 LangGraph？"
> A: LangChain Agent 是 ReAct 范式黑盒，不好控制反思边界；LangGraph 是 explicit DAG，每个节点是什么、什么时候反思、何时退出都肉眼可见；调试和单测都方便。
