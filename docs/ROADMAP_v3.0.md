# ai_collector_project v3.0 路线图

> **从「RAG 检索器」升级为「求职 Agent」**
> 一个能自主搜索、自主决策、自主反思的端到端 AI Agent。
> 用户说一句自然语言需求，它替我把 5 个城市的 AI 岗位扫一遍、
> 清洗、向量化、匹配我的画像、打技能差距分、给我排序输出。

**起草日期**：2026-06-24
**预期完成**：2026-07 ~ 2026-08（分 2-3 个周末）
**最终目标**：作为 9-10 月求职作品集的核心项目

---

## 一、v3.0 的"3 个核心能力"

### 能力 1 ── 自主采集
- 新增 `BossSource`：移动端 H5 路线（避开 Canvas 列表反爬）
- 与 v2.0 的 `BilibiliSource`、`ArxivSource` 同架构
- 复用所有反爬基建（Playwright + stealth + cookie 注入）

### 能力 2 ── 自主决策（LangGraph 编排）
- 节点 A：理解用户需求（解析"15K+"、"5 城市"等约束）
- 节点 B：决策搜索策略（先搜哪个城市/关键词组合）
- 节点 C：调用工具采集
- 节点 D：反思是否充分（信息不够 → 换关键词重搜）
- 节点 E：综合输出 + 引用每条 JD 来源

### 能力 3 ── 自主匹配（Profile-aware）
- `my_profile.yaml`：学历、年限、技能、目标
- `match_score(jd, profile)`：技能 overlap + gap 分析
- 输出："你已具备 X，需补 Y，建议优先级"

---

## 二、目录结构（v2.1 增量）

```
ai_collector_project/
├── src/
│   ├── sources/
│   │   ├── base.py            ← 已有
│   │   ├── bilibili.py        ← 已有
│   │   ├── arxiv.py           ← 已有
│   │   └── boss_zhipin.py     ★ 新增（移动端 H5）
│   │
│   ├── rag/                   ← 已有 v2.1
│   │   ├── embedder.py
│   │   └── vector_store.py
│   │
│   └── agent/                 ★ 新增 v3.0 核心
│       ├── tools.py           ← 6 个 Tool
│       ├── graph.py           ← LangGraph DAG
│       ├── nodes.py           ← 5 个决策节点
│       ├── prompts.py         ← 系统 Prompt
│       └── my_profile.yaml    ← 我的画像
│
└── scripts/
    └── find_jobs.py           ★ CLI 入口
```

---

## 三、5 阶段推进计划

| 阶段 | 目标 | 产出 | 预估 | 状态 |
|---|---|---|---|---|
| **P1** Boss 侦察 | 摸清移动端 H5 反爬情况 | 技术评估文档 | 1-2h | ✅ 完成（2026-06-24） |
| **P2** 采集打通 | 能从 1 个城市抓 10 条真实 JD | `BossSource` MVP | 3-4h | ✅ 完成（2026-06-24，5 城市 192 条入库） |
| **P3** 数据闭环 | 接入 v2.1 RAG（向量化+检索） | 自然语言查询 JD | 2h | ✅ 完成（2026-06-24，召回 A+） |
| **P4'** 详情富化 | 抓 JD 正文 + 公司 + 学历经验 | `BossJobDetail` + enrich 脚本 | 2-3h | ✅ 完成（2026-06-24，192/192 全成功） |
| **P5** Agent 化 | LangGraph 工具 + 5 节点编排 | 端到端 Agent demo | 4-6h | ✅ 完成（2026-06-24，反思循环验证） |
| **P6** 画像深匹配 | 每条 JD 算技能 overlap/gap 数值分 | match_score 函数 + 排序 | 2h | ⏳ 待办（P5 summarize 已部分覆盖） |
| **合计** | | | **15-20h** | 一天 5 阶段，约 6h |

每个阶段都是独立 commit + 独立可演示，遵循 v2.0 博客确立的"垂直切片"哲学。

---

## 三-A、P1 实战发现（2026-06-24）

**目标**：摸清 Boss 直聘的反爬画像，决定走 PC 站 / 移动端 / API 哪条路。

**关键发现**：
1. PC 站 `zhipin.com` 列表用 **Canvas 渲染**，DOM 里没有岗位文字 → 常规爬虫直接废
2. 移动端 `m.zhipin.com` 提供 **JSON API**：
   `GET /wapi/zpgeek/search/joblist.json?query=&city=&page=`
   返回结构化岗位列表（jobName / salaryDesc / skills / jobLabels / 发布人）
3. **未登录直接请求**会触发风控：
   `{"code": 37, "message": "您的环境存在异常.", "zpData": {"seed": "...", "name": "..."}}`
4. **真实浏览器登录后**直接在地址栏访问 API URL → 返回 `code: 0` + 完整数据

**技术决策**：放弃 cookie 逆向 / 接口签名逆向，改走 **CDP 接管真实 Chrome** 方案。

**Chrome 启动方式（用户一次性操作）**：
```bash
osascript -e 'quit app "Google Chrome"' && sleep 2 && \
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
  --remote-debugging-port=9222 \
  --user-data-dir="$HOME/.hermes/chrome-debug-profile" \
  https://m.zhipin.com \
  > /tmp/chrome-debug.log 2>&1 &
```

**两个必踩的坑**：
- Chrome 安全策略：**不允许默认 profile 开调试端口**，会在日志里报
  `DevTools remote debugging requires a non-default data directory`
  → 必须用独立 `--user-data-dir`（我们选 `~/.hermes/chrome-debug-profile`）
- 用户日常 Chrome 和调试 Chrome 是**两个独立 profile**，互不干扰；调试 profile 里
  扫一次码就持久保存，下次启动不用重扫

---

## 三-B、P2 实战发现（2026-06-24）

**目标**：封装 `BossSource`，跑通 5 城市 × 4 关键词的端到端采集。

**架构定位**：
- `BossSource(BaseSource)` 继承既有 v2.0 插件式架构
- 不依赖 cookie 文件 / 不依赖 .env：**通过 CDP 端口动态接管 Chrome**
- 暴露两个接口：
  - `fetch_new_urls()`：BaseSource 契约，返回 URL 列表（给 Monitor 走旧流水线）
  - `fetch_jobs_structured()`：v3.0 新接口，返回 `List[BossJob]` 富数据

**关键代码片段**（同源 fetch 让浏览器自动带 cookie）：
```python
result = await page.evaluate(
    """async (url) => {
        const r = await fetch(url, { credentials: "include" });
        return await r.json();
    }""",
    api_url,
)
```

**两轮端到端跑结果对比**（**这就是垂直切片 + 真跑一次胜过空想十次**）：

| | 第 1 次 | 第 2 次（加 retry + 节流） |
|---|---|---|
| 总抓取 | 141 条 | 270 条 |
| 去噪后 | 125 条 | 238 条 |
| 郑州 | **0 条** 🔴 | 51 条 ✅ |
| 5 城市覆盖 | 4 / 5 | **5 / 5** ✅ |

**4 个真实 bug 实战修复**（systematic-debugging 在新项目里再次落地）：

```
Bug 1（🔴）连续高频请求触发 code 37 风控
        → 解：每个请求间随机 0.6-1.4s 延迟（节流）
        → 解：失败请求 1.5^attempt 指数退避，最多 2 次重试

Bug 2（🟡）Playwright 偶现 fetch_error
        "Page.evaluate: Execution context was destroyed,
         most likely because of a navigation"
        → 解：纳入同一套 retry 路径，下一次 evaluate 重新拿到上下文

Bug 3（🟢）日志格式串里把 Page 对象当 page 号打印了
        → 解：参数改名 page_num（避开和 Playwright Page 对象同名）
        → 教训：变量影子很容易导致日志噪音 → CI 看到这种乱字符串要修

Bug 4（🟢）pyright 报"参数已声明"
        → 解：同上 page 改 page_num，关键字参数也跟着改
```

**重要洞察 1：Boss 风控是"临时性"的，不是"持续性"**
- 同一查询失败一次，1-2 秒后重试 80%+ 会成功
- 不需要换 IP、不需要逆向签名、不需要刷新 cookie
- **这是个工程问题，不是逆向问题**

**重要洞察 2：列表 API 字段太少，必须再抓详情**
- `skills` 字段 90%+ 为空（只有"数据标注"类岗位才填）
- 学历、经验、JD 正文都不在搜索 API 里
- v3.0 P3 阶段必须新增 `fetch_job_detail(encrypt_job_id)` 抓详情页

**重要洞察 3：垃圾岗位筛选是真实需求，不是 over-engineering**
- 141 条里 16 条是噪音（11.3%）：日结/外包/兼职/校招实习/保险代理人发布
- 简单启发式（"元/天"/"校招"/"实习"/"收展"）就能过滤一半
- v3.0 P4 阶段 Agent 还要加 LLM 二次过滤（语义识别"挂羊头卖狗肉"）

**首批数据画像（238 条，4 关键词 × 1 页）**：
```
按城市：郑州 51 / 苏州 50 / 青岛 47 / 杭州 45 / 济南 45
按关键词：大模型 66 / Agent 65 / AI应用开发 62 / LangChain 45
```

**意外发现**：郑州 AI 岗位数量 ≥ 杭州（51 vs 45）
- 推翻了"郑州 AI 岗位稀缺"的预判
- 但需要**抓详情看薪资分布 + 公司质量**才能下定论（P3 之后做）

---

## 三-C、P3 实战发现（2026-06-24）

**目标**：把 192 条 Boss 岗位入 SQLite final_results，并接入 v2.1 RAG 层实现自然语言查询。

**架构选择**：
- Boss 搜索 API 已返回结构化数据 → **跳过 v2.0 流水线的 collector + processor 两步**
- 直接把 BossJob 按 v2.1 `structured_json` 契约 shim → final_results
- 索引脚本 `scripts/index_final_results.py` **零修改**自动支持新 source_type
- 搜索脚本 `scripts/search.py` 只加了 1 个 `--source boss_zhipin` 选项

**新增脚本**：
```
scripts/ingest_boss_jobs.py    156 行  抓 + 落库（任务队列 + final_results）
scripts/search.py              +1 行   choices 加 boss_zhipin
```

**字段映射设计**（让 bge-m3 召回最准）：
```python
{
  "title":      job.jobName,
  "summary":    "{city}地区，职位「{title}」，薪资 {salary}，要求：{labels}",
  "key_points": jobLabels,
  "tags":       skills + [keyword, city],
  "_boss":      {salary_desc, city, keyword, skills, encrypt_job_id, ...}
}
```

**召回质量验证**（4 个真实查询，full benchmark）：

| 查询 | 召回质量 | 备注 |
|---|---|---|
| "薪资 20K 以上 AI 应用开发" | A+ | 5/5 都是 AI 应用开发 |
| "要求 LangChain 或 LangGraph 经验" | A+ | 5/5 全 LangChain 工程师，最高 0.780 |
| "AI 测试或大模型评估岗位" | A+ | 5/5 全 AI 评测/测试岗 |
| "杭州 Agent 开发工程师" | A++ | 5/5 全杭州 + AI Agent，相似度 0.901-0.883 |

**重要洞察 1：跨源 RAG 一抽象就通**
- v2.0 抽象出 `BaseSource`、v2.1 抽象出 `VectorStore`
- 加 Boss 这一全新源时 RAG 层零修改可复用
- 这就是 v2.0 博客金句"架构复利"的现实印证

**重要洞察 2：搜索 API 字段太少 → 召回准但解释力弱**
- 召回相似度高，但用户看到的还是"标题+薪资"
- skills 字段 90%+ 为空，没法给出"为什么推荐"的具体理由
- → 触发 P4'：必须再抓详情才能让 Agent 解释推荐

---

## 三-D、P4' 实战发现（2026-06-24）

**目标**：用 Boss 详情 API 给 192 条岗位补全 JD 正文 + 公司 + 学历经验，让 RAG embedding 看到完整技能词。

**关键发现：详情 API 也是同源 JSON**
```
GET m.zhipin.com/wapi/zpgeek/job/card.json?securityId=...&lid=...
```
- 复用 P1 那条 CDP 接管 Chrome 路径，零额外鉴权
- `securityId` 和 `lid` 必须配对（来自搜索 API 同一条 jobList[*]），分开调会被风控

**新增代码**：
```
src/sources/boss_zhipin.py         +145 行  BossJobDetail + fetch_job_details
scripts/enrich_boss_details.py     230 行   读 DB → 调详情 API → 回写 + 索引更新
scripts/ingest_boss_jobs.py        +3 行    保存 securityId + lid 进 _boss
```

**真实跑出来的数据**：
```
小批 10/10 ✅ 全成功，JD 长度 282-1949 字
全量 182/182 ✅ 全成功，零失败
平均每条 JD 668 字（中位数 ~600 字）
总耗时 ~6 分钟（含 5 次 fetch_error 被 retry 救活）
```

**1 个真实 bug 实战修复**（再次系统化 debug）：
```
Bug: ingest 没保存 securityId/lid 进 _boss
     → enrich 第一次跑发现 196 条全部缺字段
     → 立刻修 ingest + 清空 Boss 数据 + 重跑（192 条带 ID 入库）
     → enrich 100% 成功
教训: 「下游需要的所有字段都要在上游就存好」，
      P2 应该一并把 raw 中所有 ID 类字段全部落库，不要选择性保存
```

**召回质量对比**（同一查询「LangChain + 20K + 本科 1-3 年」）：

| | 富化前（仅标题+薪资） | 富化后（含 JD 正文） |
|---|---|---|
| 召回准确度 | 字面关键词匹配 | 跨城市精准命中 |
| Top 5 命中实际技能 | "LangChain 工程师"靠标题 | 哈尔滨"Agent构造师 20K"靠 JD |
| 跨源能力 | 杭州相关岗位集中 | 哈尔滨/广州/北京/武汉/北京 |
| 简历级技能词 | skills 字段 90% 空 | 「LlamaIndex / RAG / Dify / Coze」直接可见 |

**重要洞察：JD 正文里有大量金矿**
- 招聘列表只有标题，看不出"这个岗位真用什么"
- JD 正文几乎每条都列出 5-15 个具体技术词
- bge-m3 embedding 把这些技术词全部"看见"了，召回质量直接翻倍

**意外副作用：发现郑州也有 25K+ 岗位**
- 富化前以为郑州都是低薪标注岗
- 富化后看到郑州「AI 大模型 12-18K」「AI Agent 兼职可议」等真实岗位
- 但**LangGraph 这类前沿要求在郑州仍稀缺** —— 这是真实地理梯度

---

## 三-E、P5 实战发现（2026-06-24）

**目标**：用 LangGraph 把数据 + RAG + 画像，编排成能"听话办事"的真 Agent。

**DAG 结构**：
```
START → parse_intent → retrieve → filter → reflect
                          ↑                   │
                          └─── retry ─────────┘
                                              ↓ done
                                          summarize → END
```

**5 个节点分工**（决策类调 LLM，确定性逻辑零延迟）：

| 节点 | 类型 | 用 LLM 吗 | 输出 |
|---|---|---|---|
| parse_intent | 意图解析 | ✅ | `{keywords, cities, salary_min, exp, degree, direction}` |
| retrieve | RAG 检索 | ❌ | top 30 候选 |
| filter | 硬过滤 | ❌ | 按薪资/城市/学历/经验/黑名单 |
| reflect | 反思决策 | ✅ | "done" 或 "retry 换关键词" |
| summarize | 报告生成 | ✅ | markdown 推荐报告 + 技能差距 |

**新增代码**：
```
src/agent/
├── __init__.py          13 行
├── tools.py             273 行  RAG / filter / skill_gap / salary 解析
├── prompts.py           72 行   parse_intent / reflect / summarize 三个 prompt
├── nodes.py             312 行  5 节点 + AgentState + LLM 客户端
├── graph.py             100 行  LangGraph DAG + find_jobs() 入口
└── my_profile.yaml      80 行   你的画像（学历/年限/技能/want_to_avoid）

scripts/find_jobs.py     62 行   CLI 入口
```

**新增依赖**：`langgraph 1.2 / langchain 1.3 / langchain-openai 1.3 / langchain-community 0.4`

**两轮真实端到端跑结果**：

**Run 1**：`"找薪资 15K+ 要 LangChain 或 RAG 经验的 1-3 年 AI 应用开发岗"`
- 路径：parse → retrieve → filter (30→6) → reflect (done) → summarize
- 用时 213.7s（summarize LLM 调用 90s+，火山 coding 模型对长 prompt 较慢）
- 输出：6 条岗位 + Top 3 强推荐 + 3 项技能差距 + 一句话总结
- ⭐ 报告里准确引用了 ai_collector v2.1 的 RAG 经验和 JD 中对应的"知识库构建职责"

**Run 2**：`"找郑州本科 1-3 年薪资 25K+ 要 LangGraph 的 AI Agent 开发岗"`（故意造的稀有需求）
- 路径：parse → retrieve → filter (0) → **reflect retry × 3** → summarize
- 用时 224.1s
- LLM 自主换关键词 3 次：
  - 轮 1: `[LangGraph, AI Agent, 开发]` → 0 条
  - 轮 2: `[智能体, 应用开发]` → 0 条  ← LLM 自己想出同义词
  - 轮 3: `[Agent, LLM, 开发工程师]` → 0 条  ← 再换近义词
  - 达 MAX_RETRY=3 强制 done
- 输出："郑州 25K+ 硬卡 LangGraph 与你画像三重错配；立刻转杭州/苏州 18-22K 的 RAG 应用岗，用 LangChain+Milvus 先入行，再内部转 Agent"
- ⭐ **Agent 输出和数据现实一致，没有幻觉**

**LangGraph 1.x StateGraph 用法要点**：
```python
g = StateGraph(AgentState)                  # TypedDict total=False
g.add_node("name", fn)                      # fn: state -> partial state
g.add_edge(START, "parse_intent")
g.add_conditional_edges("reflect", router, # router: state -> next_node_name
                        {"retrieve": ..., "summarize": ...})
g.add_edge("summarize", END)
compiled = g.compile()
state = compiled.invoke({"query": ...})
```

**反思决策路径覆盖率**：
- ✅ "kept ≥ 5 → done"（Run 1 覆盖）
- ✅ "kept < 5 → retry 换关键词"（Run 2 覆盖）
- ✅ "重试 ≥ 3 轮 → 强制 done"（Run 2 触发兜底）
- ✅ "LLM 给空 next_keywords → done"（防死循环兜底，未触发但已实现）

**已知优化点**（不影响功能，留给 v3.1）：
1. summarize prompt 减肥（去掉 profile 全量 JSON dump，只传必要字段）
2. 节点级缓存（同一 query 在反思循环里不要重复调 retrieve）
3. parse_intent / reflect 换更快的小模型（不需要 coding 模型）
4. 把 Agent trace 输出成 mermaid 图，博客里展示决策路径

**重要洞察 1：节点拆 LLM / 非 LLM 极有效**
- 5 节点里只有 3 个调 LLM，retrieve + filter 走纯函数
- 整个 Agent 跑下来 LLM 调用 5 次（parse 1 + reflect 3 + summarize 1）
- 同样的功能用单一 ReAct prompt 跑下来可能要 20+ LLM 调用 + 大量幻觉

**重要洞察 2：反思节点是真 Agent 的"灵魂"**
- 没有 reflect → 0 条结果就直接给空报告（Pipeline 行为）
- 有 reflect → 自动换近义词重试，最终给出"为什么失败 + 替代方案"（Agent 行为）
- 这就是简历能写"自研 LangGraph Agent"的依据

**重要洞察 3：v3.0 终于配得上 "AI Agent" 项目名**
- v1.x：采集 + LLM 清洗 = **AI Pipeline**
- v2.x：插件式多源 + RAG = **可扩展的 AI Pipeline**
- v3.0：意图理解 + 自主决策 + 反思循环 + 报告生成 = **真 AI Agent**

---

## 四、核心工具清单（agent/tools.py）

```python
@tool
def search_jobs(city: str, keyword: str, salary_min: int = 0) -> list[Job]:
    """触发 BossSource 抓取该城市该关键词的最新岗位。"""

@tool
def get_jd_detail(url: str) -> JDStructured:
    """抓取并 LLM 结构化单条 JD。"""

@tool
def vector_search(query: str, top_k: int = 5) -> list[Hit]:
    """在已采集的 JD 库里语义检索。"""

@tool
def match_my_profile(jd: JDStructured) -> MatchReport:
    """比对 my_profile.yaml，输出技能 overlap/gap 分析。"""

@tool
def list_recent_jobs(days: int = 7) -> list[Job]:
    """看最近几天采集到的所有岗位。"""

@tool
def filter_jobs(**criteria) -> list[Job]:
    """按薪资/城市/技能等条件过滤。"""
```

---

## 五、用户故事

**Story 1**：日常扫岗
```
$ python find_jobs.py
> 找 5 个城市 AI 应用 / Agent / LLM 相关岗位，15K+ 优先

Agent: 我先查 BOSS 移动端 5 个城市...
       [search_jobs × 5]
       共抓到 73 条，去重后 58 条
       [向量化 + 入库]
       [match_my_profile × 58]

       Top 5 匹配：
       1. [杭州 22-32K] XX科技 · LLM应用工程师
          ✅ 你具备：LangChain, RAG, Playwright, Python
          ⚠️ 需补：LangGraph (核心要求), Docker
          匹配度 78%

       ... (前 5)

       【技能差距 Top 3】
       1. LangGraph：13/58 岗位提到（你课程里有，立即补）
       2. Docker 部署：21/58（你项目可直接加）
       3. 通义/文心 API：9/58（接入 1 个，1 小时）
```

**Story 2**：定向调研
```
> 杭州大厂 AI 测试岗有哪些？

Agent: 关键词：大模型评估/AI测试/LLM benchmark...
       [vector_search]
       命中 4 条相关，但偏少
       [search_jobs(杭州, "大模型评估")]
       再补充 8 条新岗位
       [反思]：你 2 年第三方测评经验 + AI 知识
              这是最容易拿 offer 的方向，我重点排序
       ...
```

---

## 六、技术决策记录

### 为什么不爬 Boss PC 端列表？
- PC 端列表用 Canvas 渲染，DOM 里没有文字
- 破解成本高（OCR or 接口逆向）
- 移动端 H5（m.zhipin.com）依然是 DOM，复用现有 Playwright 基建即可

### 为什么用 LangGraph 而不是 ReAct / AutoGen？
- LangGraph 是显式 DAG，**可视化、可调试、可控**
- 求职这个场景需要"反思 → 重搜"的循环，LangGraph 的 conditional edge 天然支持
- 简历加分项：LangGraph 在 2026 招聘 JD 出现频率高
- 课程 `/RAG与项目实战` 里有完整 LangGraph 章节，正好落地

### 为什么不直接对接招聘 API？
- BOSS / 拉勾 / 智联**没有公开 API**
- 即使有也要企业资质 + 付费
- 爬虫 + 反爬本身就是你简历的差异化卖点

---

## 七、风险与备选

| 风险 | 应对 |
|---|---|
| Boss 移动端也加 Canvas | 切到拉勾 / 智联 / 猎聘移动端 |
| 风控触发滑块 | 加大随机延迟 + cookie 池 |
| LLM 清洗成本高 | 本地 ollama（gemma/mistral-nemo）兜底 |
| LangGraph 学习曲线 | 先用 LangChain AgentExecutor 跑通，再升 LangGraph |

---

## 八、完成定义（DoD）

v3.0 视为完成的标志（**必须全部满足**）：

- [ ] 能用 `python find_jobs.py "<自然语言需求>"` 端到端跑通
- [ ] 5 个城市每个至少抓到 10 条真实 JD
- [ ] LangGraph 至少 5 个节点 + 1 个反思循环
- [ ] `my_profile` 匹配输出包含 overlap、gap、优先级
- [ ] 测试套件保持全绿（在 v2.1 基础上 +10 个新测试）
- [ ] 写一篇 v3.0 博客（延续 v1.0/v1.1/v2.0/v2.1 风格）
- [ ] CSDN 发布

---

## 九、与作品集叙事的衔接

```
v1.0   能跑          基础采集 + LLM 清洗
v1.1   稳定          反爬 + 重试 + 调度
v2.0   可扩展        插件式多源（B站 + arXiv）
v2.1   能查询        + RAG 语义检索（Milvus + bge-m3）
v3.0   ★真 Agent    + LangGraph 编排 + 自主决策 + 技能匹配
       ↑↑↑
       这一步项目从"AI Pipeline"升级为真正的"AI Agent"
```

**简历金句（v3.0 完成后）**：

> 自研基于 LangGraph + Milvus + Playwright 的求职 Agent，每日自动扫描 5 城市
> AI 岗位并按个人画像打分；3 个月内辅助完成转型求职。**用自己造的 Agent 找到了
> 现在这份工作。**

这一句话就是 offer 制造机。

---

*Last updated: 2026-06-24*
