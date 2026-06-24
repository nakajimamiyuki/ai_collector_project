# 🤖 AI Collector Project — 求职 Agent v3.0

[![tests](https://github.com/nakajimamiyuki/ai_collector_project/actions/workflows/tests.yml/badge.svg)](https://github.com/nakajimamiyuki/ai_collector_project/actions/workflows/tests.yml)
[![python](https://img.shields.io/badge/python-3.11-blue.svg)](https://www.python.org/)
[![license](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

> 一个从「采集 + LLM 清洗」一路演进到「**LangGraph 求职 Agent**」的端到端项目。
> 用真实 Chrome（CDP 接管）绕过 Boss 直聘 Canvas 反爬，从 5 城市采集 192+ AI 岗位真实 JD，
> 用 Milvus + bge-m3 语义检索，用 LangGraph 5 节点 DAG 做意图解析 → RAG 检索 → 反思决策 → 报告生成。
> **现在它能听你一句自然语言需求，自己跑完整条求职链路。**

> 🆕 **v3.0** (2026-06-24)：LangGraph Agent + Boss 直聘多源（CDP 反爬）+ 详情 API 富化 + 反思循环
> 🔹 **v2.1** (2026-06-23)：RAG 检索层（Milvus Lite + bge-m3 + Ollama，47 条数据 4 query 召回 A+）
> 🔹 **v2.0** (2026-06-20)：插件式多源架构（B 站 + arXiv）/ source_type 持久化 / 36 pytest 单测
> 🔹 **v1.1** (2026-06-17)：B 站反爬升级 / LLM 健壮性 / 失败自动重试 / 定时运行
> [👉 完整 Changelog](#-changelog)

---

## 📚 配套博客系列

五篇 CSDN 文章配合项目代码一起阅读，效果最佳。每篇文章在仓库内也保留了 Markdown 源稿。

| 版本 | 主题 | CSDN 在线版 | 仓库源稿 |
|---|---|---|---|
| **v1.0** | 从 0 到 1：AI 采集 Agent 从想法到能跑 | [📖 在 CSDN 阅读](https://blog.csdn.net/peaceworld_/article/details/162107888) | [`docs/blog/v1.0_*.md`](docs/blog/v1.0_AI采集Agent从0到1.md) |
| **v1.1** | 从能跑到稳定：5 个工程化升级（反爬 / 重试 / 调度 / 健壮性） | [📖 在 CSDN 阅读](https://blog.csdn.net/peaceworld_/article/details/162130079) | [`docs/blog/v1.1_*.md`](docs/blog/v1.1_从能跑到稳定.md) |
| **v2.0** | 为什么我把"加一个数据源"拆成了三个 Phase（重构思考） | [📖 在 CSDN 阅读](https://blog.csdn.net/peaceworld_/article/details/162179687) | [`docs/blog/v2.0_*.md`](docs/blog/v2.0_为什么我把加一个数据源拆成了三个Phase.md) |
| **v2.1** | 把采集器升级成 RAG 系统的一个夜晚（Milvus Lite + bge-m3 实战与踩坑） | [📖 在 CSDN 阅读](https://blog.csdn.net/peaceworld_/article/details/162248336) | [`docs/blog/v2.1_*.md`](docs/blog/v2.1_把采集器升级成RAG系统的一个夜晚.md) |
| **v3.0** | 用自己造的 Agent 给自己找工作（LangGraph + CDP 接管 Chrome + Boss 反爬 + 反思循环） | [📖 在 CSDN 阅读](https://blog.csdn.net/peaceworld_/article/details/162279268) | [`docs/blog/v3.0_*.md`](docs/blog/v3.0_用自己造的Agent给自己找工作.md) |

---

## ✨ 项目亮点（v3.0）

- 🤖 **真正的 Agent**：LangGraph 5 节点 DAG（意图解析 → RAG 检索 → 硬过滤 → 反思 → 报告生成），反思节点能 0 结果时自主换关键词重搜
- 🛡️ **CDP 接管真实 Chrome 绕反爬**：用调试模式启动独立 Chrome profile，扫码登一次后 Playwright 长期接管 — 绕开 Boss 直聘的 Canvas 列表反爬 + code 37 风控
- 🔌 **插件式多源架构**：`BaseSource` 抽象统一 B 站 / arXiv / Boss 直聘三源接入，加新源只写一个子类
- 🧠 **RAG 语义检索**：Milvus Lite + bge-m3（本地 Ollama，1024 维），242 条数据自然语言查询召回质量 A+
- 📦 **JD 详情富化**：详情 API + 安全 ID 配对自动抓取 192 条 JD 正文 / 公司名 / 学历经验，召回质量翻倍
- 💼 **画像匹配**：`my_profile.yaml` 描述你的学历 / 年限 / 已有技能 / 想避开的关键词，Agent 自动算 skill gap
- 🛠️ **生产级工程**：55 个 pytest 单测 / GitHub Actions CI / 失败自动重试 / 节流 + 退避

---

## 📐 系统架构（v3.0）

```
┌────────────────────────────────────────────────────────────┐
│                     ① 数据采集层（v2.0 插件式）              │
│   ┌─────────────────┐ ┌─────────────────┐ ┌──────────────┐ │
│   │ BilibiliSource  │ │  ArxivSource    │ │ BossSource   │ │
│   │ Playwright+UID │ │  Atom XML API   │ │ CDP→m.zhipin │ │
│   └─────────────────┘ └─────────────────┘ └──────────────┘ │
│                              ↓                              │
│            ┌────────────────────────────────────┐           │
│            │  ② Pipeline（v1.x）                │           │
│            │  Monitor → Collector → Processor   │           │
│            │  （Boss 跳过，因 API 已结构化）     │           │
│            └────────────────────────────────────┘           │
│                              ↓                              │
│            ┌────────────────────────────────────┐           │
│            │  ③ DBManager (SQLite)              │           │
│            │  task_queue / raw / final_results  │           │
│            │  + source_type 多源标识            │           │
│            └────────────────────────────────────┘           │
└────────────────────────────────────────────────────────────┘
                              ↓
┌────────────────────────────────────────────────────────────┐
│                  ④ RAG 检索层（v2.1）                       │
│   OllamaEmbedder (bge-m3) → VectorStore (Milvus Lite)      │
└────────────────────────────────────────────────────────────┘
                              ↓
┌────────────────────────────────────────────────────────────┐
│              ⑤ LangGraph 求职 Agent（v3.0）★               │
│                                                            │
│   START → parse_intent → retrieve → filter → reflect       │
│                                ↑           │               │
│                                └─ retry ───┘               │
│                                            ↓ done          │
│                                       summarize → END      │
│                                                            │
│   3 个 LLM 节点（parse / reflect / summarize）              │
│   2 个纯函数节点（retrieve / filter）                       │
└────────────────────────────────────────────────────────────┘
```

---

## 🚀 5 分钟跑通

### 1. 环境准备

```bash
git clone https://github.com/nakajimamiyuki/ai_collector_project.git
cd ai_collector_project

# 推荐 pyenv 3.11.9（不强制 venv）
pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/

# Playwright 浏览器内核（国内淘宝镜像加速）
PLAYWRIGHT_DOWNLOAD_HOST=https://npmmirror.com/mirrors/playwright \
    python -m playwright install chromium

# 本地 Ollama 拉 bge-m3 embedding 模型（仅 v2.1+ RAG 需要）
ollama pull bge-m3
```

### 2. 配置 LLM 凭证

```bash
cp .env.example .env
```

编辑 `.env`：

```ini
LLM_API_KEY=ark-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
LLM_API_BASE=https://ark.cn-beijing.volces.com/api/coding/v3
LLM_MODEL=kimi-k2.6
DB_PATH=data/collector.db
```

> 💡 火山引擎 Coding Plan 走套餐而非按量付费，`/coding/` 路径必须保留。

### 3. 三类典型用法

**A. 跑原始 v1/v2 采集流水线（B 站 + arXiv）**：

```bash
python main.py
```

**B. v2.1 RAG 检索（语义搜已采集的内容）**：

```bash
# 把 final_results 索引到向量库
python scripts/index_final_results.py

# 自然语言查询
python scripts/search.py "最近 Anthropic 的动态"
python scripts/search.py "diffusion 模型论文" --source arxiv
```

**C. v3.0 求职 Agent（核心新能力）**：

```bash
# Step 1: 用独立调试 profile 启动 Chrome（一次性，扫码登 Boss）
osascript -e 'quit app "Google Chrome"' && sleep 2 && \
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
  --remote-debugging-port=9222 \
  --user-data-dir="$HOME/.hermes/chrome-debug-profile" \
  https://m.zhipin.com \
  > /tmp/chrome-debug.log 2>&1 &

# Step 2: 抓 Boss 5 城市 × 4 关键词 → SQLite
python scripts/ingest_boss_jobs.py

# Step 3: 抓详情页 → 补 JD 正文 / 公司 / 学历经验
python scripts/enrich_boss_details.py

# Step 4: 重建向量库
python scripts/index_final_results.py --rebuild

# Step 5: 跑求职 Agent ⭐
python scripts/find_jobs.py "找北京以外薪资 15K+ 要 LangChain 的 1-3 年 AI 应用开发岗"
python scripts/find_jobs.py "AI 测试或大模型评估岗 适合 2 年传统测试转型" --verbose
```

### 4. 定时运行（可选）

```bash
# 系统 crontab
crontab -e
30 9 * * * /path/to/ai_collector_project/run.sh \
           >> /path/to/ai_collector_project/logs/cron.log 2>&1

# 或用 Hermes Agent 调度（推荐，带摘要推送）
# 参考 ai_collector_cron.py
```

---

## 📂 项目结构（v3.0）

```
ai_collector_project/
├── main.py                       # v1/v2 流水线总调度
├── ai_collector_cron.py          # 简版 cron 入口（摘要推送）
├── run.sh / run_batch.py         # crontab wrapper / 批量补跑
├── requirements.txt
├── .env.example
│
├── src/                          # 核心模块
│   ├── db_manager.py             # SQLite 状态机 + source_type 持久化
│   ├── monitor.py                # 多源调度器（v2.0 重构后）
│   ├── collector.py              # Playwright 采集器（按 source_type 分派）
│   ├── processor.py              # LLM 清洗器（按 source_type 选 prompt）
│   │
│   ├── sources/                  # v2.0 插件式数据源
│   │   ├── base.py               # BaseSource 抽象基类
│   │   ├── bilibili.py           # B 站源（API + Playwright fallback）
│   │   ├── arxiv.py              # arXiv 源（Atom XML）
│   │   └── boss_zhipin.py        # ★ v3.0 Boss 源（CDP + 详情 API）
│   │
│   ├── rag/                      # v2.1 RAG 检索层
│   │   ├── embedder.py           # OllamaEmbedder (bge-m3, 1024d)
│   │   └── vector_store.py       # VectorStore (Milvus Lite + COSINE)
│   │
│   └── agent/                    # ★ v3.0 LangGraph Agent
│       ├── tools.py              # RAG / filter / skill_gap / salary 解析
│       ├── prompts.py            # 3 个 LLM prompt（parse/reflect/summarize）
│       ├── nodes.py              # 5 个 LangGraph 节点 + AgentState
│       ├── graph.py              # DAG 编排 + find_jobs() 入口
│       └── my_profile.yaml       # 用户画像（学历/年限/技能/avoid）
│
├── scripts/                      # CLI 工具集
│   ├── index_final_results.py    # v2.1 批量索引到向量库
│   ├── search.py                 # v2.1 自然语言查询
│   ├── ingest_boss_jobs.py       # ★ v3.0 抓 Boss 岗位 → SQLite
│   ├── enrich_boss_details.py    # ★ v3.0 补全 JD 正文
│   └── find_jobs.py              # ★ v3.0 Agent CLI 入口
│
├── tests/                        # pytest 单测（55 个，全离线 mock）
│   ├── conftest.py
│   ├── test_db_manager.py
│   ├── test_processor.py
│   ├── test_collector_dispatch.py
│   ├── test_sources_arxiv.py
│   ├── test_rag_embedder.py
│   └── test_rag_vector_store.py
│
├── data/                         # 运行时生成
│   ├── collector.db              # SQLite 主库
│   └── vector.db/                # Milvus Lite 目录
│
├── logs/                         # 运行时日志
│
└── docs/
    ├── ROADMAP_v3.0.md           # v3.0 蓝图 + 实战发现
    └── blog/                     # v1.0~v3.0 博客源稿
```

---

## 🎯 当前能做什么

### ✅ 多源采集（v2.0 + v3.0）

- B 站：API 监控 + Playwright fallback + WBI / 风控错误识别
- arXiv：Atom XML 拉取最新论文（cs.AI / cs.CL / cs.LG ...）
- **Boss 直聘**：CDP 接管真实 Chrome → 同源 fetch JSON API → 5 城市 × 任意关键词

### ✅ RAG 语义检索（v2.1）

- bge-m3 中英混合 embedding（本地 Ollama，零网络依赖）
- Milvus Lite 单文件向量库（pip 即装，生产可平滑迁到 Milvus Cluster）
- 4 query benchmark 召回质量 A+（跨语言 / 跨源 / 跨城市命中）

### ✅ 求职 Agent（v3.0）

- 自然语言意图解析（"15K+"、"北京以外"、"1-3 年" 全部识别）
- 硬过滤（薪资 / 城市 / 学历 / 经验 / 黑名单）+ 软排序（向量相似度）
- **反思循环**：0 结果时 LLM 自主换近义词重搜，最多 3 轮
- 报告生成：Top N 推荐 + 每条"为什么推荐" + 技能差距 Top 3 + 一句话总结
- 真实跑过两轮：Run 1 命中 6 条全 actionable，Run 2 故意找不到时给出错配诊断 + 替代方案

### ✅ 工程化（贯穿全版本）

- 状态机 + 失败自动重试（v1.1）
- 插件式架构（v2.0）
- 55 个 pytest 单测，全部离线 mock，CI 自动跑（v2.0）
- 节流 + 指数退避（v3.0，code 37 风控临时性，重试可救活 100%）

---

## 📜 Changelog

### v3.0 (2026-06-24) — 从 RAG 检索器到真 Agent

一天 5 阶段完整跑通，项目正式从「带 LLM 的 Pipeline」升级为「真 AI Agent」。

🛡️ **Boss 反爬侦察 + CDP 接管 Chrome**（P1）
- 移动端 `m.zhipin.com/wapi/zpgeek/search/joblist.json` JSON API 路径确认
- 用独立 Chrome profile（`~/.hermes/chrome-debug-profile`）+ `--remote-debugging-port=9222` 长期接管
- 同源 fetch 让浏览器自动带 cookie，**完全跳过 code 37 风控**
- 踩坑：Chrome 安全策略不允许默认 profile 开调试端口，必须独立 profile

🔌 **BossSource 插件式接入**（P2）
- `src/sources/boss_zhipin.py` — `BossJob` + `BossSource(BaseSource)`
- 节流（每请求间随机 0.6-1.4s）+ 指数退避（1.5^attempt）+ 最多 2 次重试
- 5 城市（杭州/苏州/济南/青岛/郑州）× 4 关键词 → **192 条入库**
- 启发式去噪：自动过滤"元/天"、校招、实习、保险代理人发布的噪音岗

🔄 **接入 v2.1 RAG，零修改可复用**（P3）
- `scripts/ingest_boss_jobs.py` — 跳过 collector/processor，直接 shim 进 `final_results`
- 索引脚本 + 搜索脚本零修改自动支持新 source_type
- 4 query benchmark 召回质量全部 A+（最高 0.901 相似度）

📦 **详情 API 富化**（P4'）
- `BossJobDetail` + `fetch_job_details` — 用 `securityId` + `lid` 配对调详情 API
- `scripts/enrich_boss_details.py` — 192/192 条全部补全 JD 正文 + 公司 + 学历经验
- **召回质量翻倍**：富化后跨城市精准命中（如「LangChain + 20K + 1-3 年」召回到哈尔滨/广州/北京等）
- Bug: ingest 漏存 securityId/lid → 立刻修 + 清库重跑（教训：下游需要的字段都要在上游存好）

🧠 **LangGraph Agent**（P5，v3.0 灵魂）
- `src/agent/` — tools / prompts / nodes / graph / my_profile.yaml
- **5 节点 DAG**：parse_intent (LLM) → retrieve (纯函数) → filter (纯函数) → reflect (LLM) → summarize (LLM)
- 反思循环：0 结果时 LLM 自主换关键词重搜，MAX 3 轮
- Run 1：「LangChain RAG 15K+ 1-3 年」→ 6 条命中 + Top 3 推荐 + 3 项技能差距
- Run 2：「郑州 25K+ LangGraph」（故意稀有）→ 3 轮 retry 后给出"画像三重错配"诊断 + 替代方案
- 端到端 ~3.5 分钟（火山 coding 模型 summarize 较慢）

📚 **依赖新增**
- `langgraph 1.2 / langchain 1.3 / langchain-openai 1.3 / langchain-community 0.4`
- `pyyaml 6.0+`（加载 my_profile.yaml）

📖 **简历金句升级**
> 自研基于 LangGraph + Milvus + Playwright + bge-m3 的**求职 Agent**，通过 CDP 接管真实浏览器绕过 Boss 直聘 Canvas 反爬，从 5 城市采集 192 条 AI 岗位真实 JD，端到端实现意图解析 → RAG 检索 → 反思决策 → 报告生成。**用自己造的 Agent 找到了现在这份工作。**

---

### v2.1 (2026-06-23) — RAG 检索层

把"采集 + LLM 清洗"升级成"采集 + LLM 清洗 + 语义检索"。

🔍 **RAG 端到端**
- `src/rag/embedder.py` — OllamaEmbedder（bge-m3:latest，1024 维，本地零网络）
- `src/rag/vector_store.py` — VectorStore（Milvus Lite + COSINE，单文件零服务）
- `scripts/index_final_results.py` — 批量索引脚本（47/47 条 8 秒索引完）
- `scripts/search.py` — 自然语言 CLI 检索

🐛 **4 个真实 bug 实战修复**（systematic-debugging skill 实战）
- pymilvus 3.x optional extra 不自动装 milvus-lite
- COSINE 返回的是 distance 不是 similarity（手动 `1 - d/2` 转换）
- 跨进程 collection 默认 released，必须 `load_collection()`
- Milvus Lite 3.x 把 `db_path` 当目录用（不是文件），重建要用 `shutil.rmtree`

📈 **测试 36 → 55，全绿**

---

### v2.0 (2026-06-20) — 插件式重构

把"加一个数据源 = 复制粘贴 BiliMonitor"的旧坑废掉。

🏗️ **三段式重构**
- **Phase 1：抽象** — `BaseSource` 基类 + `Monitor` 退化为调度器（零行为变化，零新功能）
- **Phase 2：接源** — `ArxivSource` 真实新源接入验证抽象正确
- **Phase 3：字段化** — `source_type` 进 DB（task_queue + final_results）+ 幂等迁移 + 老数据回填

📦 **异质源挑战**
- arXiv 用 requests（0.5s）vs B 站用 Playwright（10s+）→ collector 按 source_type 分派
- arXiv 论文字段 vs B 站视频字段不同 → processor 按 source_type 选 prompt

🧪 **首次加 pytest 单测**：36 个测试，0.3 秒跑完，全部 mock 外部依赖（DB / 网络 / LLM）

---

### v1.1 (2026-06-17) — Stability Release

修复 v1.0 在真实环境下暴露的 4 个核心问题，加入定时运行支持。

🛡️ **B 站反爬升级**
- `uid=` → `mid=`（B 站官方推荐）
- 完整浏览器 headers + `.env` 注入 `BILI_COOKIE`
- 识别业务错误码（-799 / -412 / -111）→ 自动 fallback 到 Playwright

🔍 **Collector 选择器更新**（2026-06 实地探测）
- `.video-desc-container` / `#v_desc` 替代已下线的 `.video-desc` / `.desc-content`
- 4 个核心字段独立提取，多套备选选择器降级

🧠 **LLM 健壮性**
- `max_tokens` 2000 → 4000
- 输入上下文 6000 → 8000
- `_safe_json_parse()` 二段解析 + 失败原始输出落盘到 `logs/llm_failures/`
- 单次请求 90s 超时

🔁 **失败自动重试**
- `mark_failed(url, reason)` + `requeue_failed(max_retry=3)`
- main.py 启动时自动调用，FAILED 任务自动复活

⏰ **定时运行**
- `run.sh` POSIX wrapper + `ai_collector_cron.py` 摘要推送

---

### v1.0 (2026-06-16) — 从 0 到 1

最初版本：4 层架构（Monitor / Collector / Processor / DBManager）+ 状态机 + Playwright 反爬 + LLM JSON 抽取。

---

## 🔧 Roadmap (v3.1+)

### 🟡 中优先级

- [ ] **v3.1 Agent 优化**：summarize prompt 减肥 / 节点级缓存 / parse + reflect 换更快的小模型
- [ ] **P6 画像深匹配**：每条 JD 算数值化 `match_score(jd, profile)`，按分数排序
- [ ] **更多招聘源**：拉勾 / 智联 / 猎聘 / Stack Overflow Jobs
- [ ] **Boss 详情字段扩展**：公司规模 / 融资阶段 / 福利 / 团队规模
- [ ] **简历自动适配**：根据 Top 5 推荐岗位反向优化简历关键词
- [ ] **每日岗位 cron**：自动跑 Agent + 把 Top 推荐推送到飞书/Telegram

### 🟢 长期规划

- [ ] **MCP Server 化**：让 Claude Desktop / Cherry Studio / Hermes Agent 直接调用本项目
- [ ] **多 Agent 协作**：研究 Agent + 简历 Agent + 投递 Agent 分工合作
- [ ] **图谱化**：Neo4j 存岗位 → 公司 → 技能 → 行业知识图谱
- [ ] **本地 LLM 路由**：parse_intent 用本地小模型（Qwen 7B），summarize 才用云上大模型

### ✅ 已在 v2/v3 解决（v1 时代的旧愿景）

- [x] ~~Embedding + 向量库~~ → v2.1 Milvus Lite + bge-m3
- [x] ~~Agent 化 LangGraph~~ → v3.0 5 节点 DAG + 反思循环
- [x] ~~支持更多平台~~ → v2.0 arXiv + v3.0 Boss 直聘
- [x] ~~并发采集~~ → asyncio 全异步流水线
- [x] ~~Web UI~~ → 改用 CLI（更轻量、易脚本化）
- [x] ~~LLM Provider 抽象~~ → langchain_openai 统一封装

---

## 🧪 测试

```bash
# 全部单元测试（55 个，全离线 mock，0.5 秒跑完）
pytest tests/ -v

# 只跑某个模块
pytest tests/test_rag_vector_store.py -v

# CI 自动跑（每次 push）
# 见 .github/workflows/tests.yml
```

---

## 📊 数据库 Schema

### `task_queue` (任务队列)
| 字段 | 类型 | 说明 |
| :--- | :--- | :--- |
| id | INTEGER | 主键自增 |
| url | TEXT UNIQUE | 内容 URL |
| status | TEXT | PENDING/PROCESSING/COLLECTED/COMPLETED/FAILED |
| **source_type** | TEXT | **v2.0** — bilibili / arxiv / boss_zhipin |
| retry_count | INTEGER | 重试次数（v1.1） |
| error_message | TEXT | v1.1 — 最近一次失败原因 |
| last_attempt_at | DATETIME | v1.1 — 最近一次执行时间 |
| created_at | DATETIME | 入队时间 |

### `final_results` (LLM 清洗结果 / 结构化数据)
| 字段 | 类型 | 说明 |
| :--- | :--- | :--- |
| id | INTEGER | 主键自增 |
| url | TEXT | 内容 URL |
| **source_type** | TEXT | **v2.0** — bilibili / arxiv / boss_zhipin |
| structured_json | TEXT | JSON 结构化数据（含 `_boss` / `_arxiv` 等子节点） |
| processed_at | DATETIME | 处理完成时间 |

### `raw_contents` (Playwright 原始抓取，仅 v1/v2 用)
| 字段 | 类型 | 说明 |
| :--- | :--- | :--- |
| url | TEXT PK | URL |
| markdown_text | TEXT | Playwright 抓的 markdown |
| collected_at | DATETIME | 抓取完成时间 |

> 💡 Boss 直聘走搜索 API 已结构化，跳过 `raw_contents`，直接落 `final_results`。

---

## 📝 数据示例

### v1/v2 B 站视频示例
```json
{
  "title": "【官方 MV】Never Gonna Give You Up - Rick Astley",
  "up_name": "索尼音乐中国",
  "play_count": "9977.2万",
  "tags": ["Never Gonna Give You Up", "Rick Astley", "欧美MV"],
  "summary": "Rick Astley 经典代表作《Never Gonna Give You Up》的官方 MV...",
  "key_points": ["经典 80 年代流行金曲官方 MV", "Rickroll 网络梗文化现象"]
}
```

### v3.0 Boss 岗位示例
```json
{
  "title": "AI Agent应用开发工程师",
  "summary": "杭州地区，公司「斑头雁智能科技」，职位「Agent开发（全栈）」，薪资 12-18K·13薪，要求 1-3年经验，本科学历，职责：根据客户需求独立完成 AI 应用方案设计...",
  "key_points": ["1-3年", "本科", "杭州斑头雁智能科技"],
  "tags": ["LangChain", "RAG", "Agent", "杭州", "本科", "1-3年"],
  "_boss": {
    "salary_desc": "12-18K·13薪",
    "city": "杭州",
    "brand_name": "杭州斑头雁智能科技",
    "experience_name": "1-3年",
    "degree_name": "本科",
    "post_description": "岗位职责：1. 根据客户需求，能独立完成 AI 应用的方案设计与应用开发...",
    "encrypt_job_id": "80c09728ecb88e840nZ429u0EltT",
    "security_id": "...",
    "lid": "..."
  }
}
```

---

## 🤝 贡献

这是一个学习项目，欢迎 Issue 和 PR。

## 📄 License

MIT License

## 🙏 致谢

- [Playwright](https://playwright.dev/) — 浏览器自动化
- [playwright-stealth](https://github.com/AtuboDad/playwright_stealth) — 反爬隐身
- [Milvus / Zilliz](https://milvus.io/) — Milvus Lite 单文件向量库
- [BAAI bge-m3](https://huggingface.co/BAAI/bge-m3) — 中英混合 embedding SOTA
- [Ollama](https://ollama.com/) — 本地 LLM / embedding 一键运行
- [LangGraph](https://langchain-ai.github.io/langgraph/) — 可视、可调试的 Agent 编排
- [火山引擎方舟](https://www.volcengine.com/product/ark) — Coding Plan 高性价比 LLM 服务

---

**v1.0 — 2026-06-16** · **v3.0 — 2026-06-24** | Built with ❤️ from 测试转型 AI Agent 开发的路上
