# ai_collector_project v3.1 路线图

> **从「单 Agent 闭环」升级为「MCP 生态原生 + 多 Agent 协作」**
> v3.0 证明了 Agent 能自主决策；v3.1 把它**接入 AI 生态**——
> 让 Claude Desktop / Cursor / Cherry Studio 直接调用我的求职 Agent。

**起草日期**：2026-06-25
**预期完成**：2026-07 中 ~ 2026-08 末（4-6 个周末）
**最终目标**：作为 2026-09/10 求职作品集**第二层差异化**——
v3.0 是「单 Agent 实操」，v3.1 是「多 Agent + 协议级工程」。

> 📌 **简历金句升级**
> v3.0：用 LangGraph + RAG + CDP 反爬实现自主求职 Agent
> v3.1：**基于 MCP 协议的多 Agent 协作系统，覆盖求职全链路；
>        Server 同时被 Claude Desktop / Cursor / Hermes Agent 调用**
> → 从「demo 级别」跨到「生态级别」

---

## 零、为什么是 v3.1 而不是 v4.0？

```
v3.0 已经是一个能跑通的 Agent
v3.1 不是推倒重来，是「让 v3.0 长出三根新手脚」：
  ① MCP Server 化   → 让生态调用我
  ② 多 Agent 协作   → 把一个大节点拆成多个小角色
  ③ 商用 LLM 接入   → 不止本地 ollama，能跑大模型
v4.0 留给真正改架构的版本（如：换底座 / 端到端微调）
```

---

## 一、v3.1 的「3 个新能力」

### 能力 1 ── MCP Server 化（核心）★★★

**目标**：把 v3.0 的核心能力暴露成符合 MCP 协议的工具，让任何 MCP 客户端可调。

**对外暴露的 4 个 Tool**：

| Tool 名 | 输入 | 输出 | 来源 |
|---|---|---|---|
| `search_jobs(keyword, city, top_k)` | 自然语言关键词 + 城市 | JSON 岗位列表 | SQLite `final_results` |
| `match_profile(jd_id)` | 岗位 id | overlap/gap/优先级 | v3.0 的 match_score |
| `query_rag(question, top_k)` | 自然语言问题 | RAG 检索结果 | Milvus + bge-m3 |
| `get_skill_gap_summary()` | 无 | 市场技能热度 + 我的缺口 | 192 条 JD 聚合 |

**用 FastMCP + stdio 传输**：

```python
# src/mcp_server/ai_collector_mcp.py
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("ai-collector")

@mcp.tool()
def search_jobs(keyword: str, city: str = "", top_k: int = 5) -> str:
    """搜索已采集的 Boss 岗位..."""
    ...

if __name__ == "__main__":
    mcp.run(transport="stdio")
```

**验证**：装到 Claude Desktop + Hermes 两个客户端，**两边都能查同一份数据**。

---

### 能力 2 ── 多 Agent 协作 ★★

**目标**：把 v3.0 的"一个 LangGraph Agent 干所有事"拆成 **3 个专业 Agent**，用 supervisor 模式协调。

```
┌────────────────────────────────────────────────────┐
│  Supervisor Agent（总调度，决定下一步谁干）          │
└────────────────────────────────────────────────────┘
         ↓ 路由
    ┌────┴────┬──────────┐
    ↓         ↓          ↓
┌────────┐ ┌────────┐ ┌────────┐
│研究 Agent│ │简历 Agent│ │投递 Agent│
│        │ │          │ │        │
│采集+RAG│ │ JD→简历  │ │生成打招呼│
│技能分析│ │ 关键词改写│ │ + 跟踪状态│
└────────┘ └────────┘ └────────┘
```

**为什么拆？**
- 单 Agent 上下文过载（v3.0 已经接近 prompt 上限）
- 不同 Agent 用不同模型（研究用便宜的，简历用强的）
- 简历能写「实现多 Agent 协作架构」——2026 招聘 JD 高频词

**用 LangGraph 的 Multi-Agent Supervisor 模式**（课程里有章节）。

---

### 能力 3 ── 商用 LLM API 接入 ★

**目标**：v3.0 只用本地 ollama，v3.1 接入 **通义千问 / Kimi / 智谱**，做 A/B 对比。

**接入策略**：
- 抽象层：`src/llm/router.py` 统一接口
- 配置：`config.yaml` 选模型（ollama / qwen-max / kimi / glm-4）
- 用途：研究 Agent 用 ollama（省钱）、简历 Agent 用 qwen-max（质量）
- 实验：跑同一份 JD，对比 4 个模型的简历改写质量

**为什么做？**
- HR 一定会问「你用过国产大模型吗？」
- 课程涵盖 Coze/Dify 都依赖国内 API
- 数据：本地模型在简历改写上明显不如商用，得有数据证明

---

## 二、目录结构（v3.1 增量）

```
ai_collector_project/
├── src/
│   ├── agent/                      ← v3.0 已有
│   │   ├── graph.py                ← 现 supervisor 节点入口
│   │   ├── agents/                 ★ 新增（多 Agent 拆分）
│   │   │   ├── research_agent.py
│   │   │   ├── resume_agent.py
│   │   │   └── apply_agent.py
│   │   └── my_profile.yaml
│   │
│   ├── llm/                        ★ 新增（LLM 路由抽象层）
│   │   ├── router.py
│   │   ├── ollama_provider.py
│   │   ├── qwen_provider.py
│   │   └── kimi_provider.py
│   │
│   └── mcp_server/                 ★ 新增（MCP 服务化）
│       ├── ai_collector_mcp.py     ← 主入口
│       └── tools.py                ← 4 个对外 Tool 实现
│
├── scripts/
│   ├── find_jobs.py                ← v3.0 已有
│   ├── start_mcp_server.sh         ★ 新增
│   └── compare_llm_quality.py      ★ 新增（模型对比脚本）
│
└── docs/
    ├── ROADMAP_v3.0.md             ← 已有
    ├── ROADMAP_v3.1.md             ← 本文档
    └── blog/
        └── v3.1_把单Agent升级成MCP生态原生的多Agent.md  ★ 待写
```

---

## 三、分阶段执行计划

### Phase 1 ── MCP Server 最小可跑（1 个周末，~6 小时）

**周末 1**（2026-07-04/05 或 07-11/12）

- [ ] P1.1 装 mcp SDK + fastmcp（venv 内，aliyun 镜像）
- [ ] P1.2 写 `ai_collector_mcp.py` 骨架（只包 `search_jobs` 一个 Tool）
- [ ] P1.3 stdio 模式启动，用 `mcp inspector` 调试
- [ ] P1.4 配进 Hermes `~/.hermes/config.yaml` 的 `mcp_servers`
- [ ] P1.5 配进 Claude Desktop（如有账号）
- [ ] P1.6 完整跑一遍：用 Hermes 自然语言查\"杭州 LangChain 岗位\"，验证返回真实数据

**完成标志**：
```
✅ Hermes 里执行任何自然语言问句，能看到 mcp_ai_collector_search_jobs 被调用
✅ 返回的数据跟直接 SQL 查 collector.db 一致
```

---

### Phase 2 ── 把 v3.0 全部能力暴露 + 商用 LLM 接入（1-2 个周末，~10 小时）

**周末 2-3**（2026-07 中下旬）

- [ ] P2.1 实现 `match_profile / query_rag / get_skill_gap_summary` 3 个 Tool
- [ ] P2.2 抽 `src/llm/router.py` 统一接口（OpenAI 兼容协议）
- [ ] P2.3 接 qwen-max（阿里云灵积，需要 API key）
- [ ] P2.4 接 kimi（月之暗面）
- [ ] P2.5 写 `compare_llm_quality.py`：固定 5 条 JD，跑 4 个模型，人工打分
- [ ] P2.6 把对比结果写进 README 当数据卖点

**完成标志**：
```
✅ MCP Server 4 个 Tool 全部跑通
✅ LLM 路由层支持至少 3 个 provider 切换
✅ README 里有一张「4 模型简历改写质量对比表」
```

---

### Phase 3 ── 多 Agent 拆分 + Supervisor（2 个周末，~12 小时）

**周末 4-5**（2026-07 末 ~ 2026-08 初）

- [ ] P3.1 把 v3.0 的 `graph.py` 拆成 3 个 sub-agent
- [ ] P3.2 写 Supervisor Agent（LangGraph 的 multi-agent supervisor）
- [ ] P3.3 验证端到端：自然语言 → Supervisor 路由 → 多 Agent 协作 → 输出
- [ ] P3.4 给每个 sub-agent 单独配模型（研究 ollama / 简历 qwen-max）
- [ ] P3.5 测试套件 +5 个测试（覆盖 supervisor 路由 + 单 agent 独立性）

**完成标志**：
```
✅ python find_jobs.py "杭州 AI Agent 开发岗 + 帮我改简历"
   能跑完整路径：研究 Agent 出岗位 → 简历 Agent 改简历 → 输出
✅ 不同 Agent 调用了不同 LLM provider（日志能看到）
```

---

### Phase 4 ── 博客 + 发布（1 个周末，~6 小时）

**周末 6**（2026-08 中）

- [ ] P4.1 写 v3.1 博客：《把单 Agent 升级成 MCP 生态原生的多 Agent》
- [ ] P4.2 截图：Claude Desktop 调用我的 MCP Server 的实况
- [ ] P4.3 发 CSDN（账号 peaceworld_，署名 minjie / @nakajimamiyuki）
- [ ] P4.4 GitHub README 升级（v3.1 章节 + MCP 接入指南）
- [ ] P4.5 git tag v3.1

**完成标志**：
```
✅ 博客 CSDN 上线，是系列第 6 篇
✅ GitHub 仓库 README 顶部有 \"v3.1: MCP-native multi-agent\" 徽章
✅ 简历金句可以替换：「实现符合 MCP 协议的多 Agent 求职系统，
   支持 Claude Desktop / Cursor / Hermes 三个主流客户端直接调用」
```

---

## 四、技术决策记录

### 为什么 stdio 而不是 HTTP？
- 个人项目，单机用，stdio 零配置零运维
- HTTP 需要部署 + HTTPS + 鉴权，对作品集来说没必要
- 简历写「实现 MCP Server 支持 stdio 传输」已经够稀缺

### 为什么 LangGraph supervisor 而不是 AutoGen / CrewAI？
- v3.0 已用 LangGraph，避免再学一套
- supervisor 模式跟课程章节对应
- LangGraph 招聘 JD 出现频率 > AutoGen

### 为什么 qwen + kimi 而不是 GPT-4 / Claude？
- 国内 HR 关心：「你能用国产模型吗？」
- 国产模型 API key 便宜（qwen-max 几块钱够跑完 v3.1 全流程）
- 翻墙不稳，本地开发体验差

### 为什么不接 Coze / Dify？
- Coze/Dify 是 **无代码平台**，跟 v3.1 工程化目标冲突
- 等 v3.1 完成后，再做一个 Coze 版的对比 demo 作为额外材料
- 简历可以写「在 v3.1 工程版之外，用 Coze 复现同样功能 1 小时搞定」

---

## 五、风险与备选

| 风险 | 应对 |
|---|---|
| MCP SDK 版本不稳定（API 频繁变化） | 锁版本 `mcp==1.26.x`，写明 |
| Claude Desktop 国内用不了 | Hermes + Cursor 两端验证即可（Cursor 走代理稳） |
| 商用 LLM API key 没注册 | qwen 阿里云送 100 万 token 免费额度，kimi 也送 |
| Supervisor 拆分后比单 Agent 还慢 | 加并发节点 / 减少 Agent 间通信轮次 |
| 多 Agent 上下文管理复杂 | 先用「共享 state」最简方案，需要再升 |

---

## 六、与 v3.0 / 求职策略的对齐

```
v3.0 简历定位：能独立做端到端 Agent 工程
   ↓
v3.1 简历定位：懂 AI 应用生态（MCP）+ 懂多 Agent 协作

主投方向（开发主投 + 测评保底）：
  ✓ AI 应用开发工程师          ← v3.0+v3.1 直接命中
  ✓ AI Agent 开发              ← v3.1 多 Agent 是核心卖点
  ✓ RAG 工程师                 ← RAG 是 v3.1 暴露的 Tool 之一
  ✓ LLM 应用工程师             ← LLM 路由层是直接证据
  保底：AI 测试 / 大模型评估    ← compare_llm_quality.py 是\"评测\"实证
```

**关键转化**：
- 「会写 LangChain」→ **稀缺度 30%**（人人都说自己会）
- 「实现 MCP Server」→ **稀缺度 90%**（2026-06 实测 14/192 JD 提到）
- 「多 Agent 协作架构」→ **稀缺度 80%**（绝大多数项目是单 Agent）

---

## 七、完成定义（DoD）

v3.1 视为完成的标志（**必须全部满足**）：

- [ ] MCP Server 至少 4 个 Tool 跑通（stdio 传输）
- [ ] 至少 2 个 MCP 客户端验证（Hermes + Cursor 或 Claude）
- [ ] LLM 路由层支持 ≥3 个 provider（ollama / qwen / kimi）
- [ ] Supervisor + 3 sub-agent 端到端跑通
- [ ] 测试套件保持全绿（v3.0 基础上 +10）
- [ ] 4 模型简历改写对比表（README 里有数据）
- [ ] 写一篇 v3.1 博客
- [ ] CSDN 发布（系列第 6 篇）
- [ ] GitHub tag v3.1

---

## 八、与作品集叙事的衔接

```
v1.0   能跑          基础采集 + LLM 清洗
v1.1   稳定          反爬 + 重试 + 调度
v2.0   可扩展        插件式多源（B站 + arXiv）
v2.1   能查询        + RAG 语义检索（Milvus + bge-m3）
v3.0   真 Agent      + LangGraph 编排 + 自主决策 + 技能匹配
v3.1   ★生态原生     + MCP Server + 多 Agent 协作 + LLM 路由
       ↑↑↑
       这一步项目从\"工程闭环\"升级为\"AI 生态原生公民\"
```

**v3.1 完成后的求职话术替换**：

> 自研基于 **MCP 协议 + LangGraph 多 Agent + 多 LLM 路由**的求职系统：
> 一个 MCP Server 同时被 Claude Desktop、Cursor、Hermes Agent 三个客户端调用；
> 内部由 Supervisor 调度 3 个 sub-agent（研究 / 简历 / 投递），
> 每个 Agent 按性价比选用不同 LLM（本地 ollama + 阿里 qwen + 月之暗面 kimi）。
> **用自己造的 Agent 找到了这份工作。**

═══════════════════════════════════════════
**承接 v3.0 的偶然，开启 v3.1 的必然**。
═══════════════════════════════════════════

---

*Last updated: 2026-06-25*
