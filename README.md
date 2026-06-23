# 🤖 AI Collector Project — 智能内容采集系统 v2.0

[![tests](https://github.com/nakajimamiyuki/ai_collector_project/actions/workflows/tests.yml/badge.svg)](https://github.com/nakajimamiyuki/ai_collector_project/actions/workflows/tests.yml)
[![python](https://img.shields.io/badge/python-3.11-blue.svg)](https://www.python.org/)
[![license](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

> 一个集成 **Playwright 反爬采集 + LLM 结构化清洗** 的全自动化多源内容监控与分析系统（B 站 + arXiv）。
> 这不是传统爬虫，而是一个具备**自主决策、内容理解、容错恢复**能力的 AI Agent。

> 🆕 **v2.0** (2026-06-20)：插件式多源架构（B 站 + arXiv）/ source_type 持久化 / pytest 单元测试（36 测试，离线可跑）。
> 🔹 **v1.1 stable** (2026-06-17)：B 站反爬升级 / LLM 健壮性增强 / 失败自动重试 / 定时运行支持。
> [👉 查看完整 Changelog](#-changelog)

---

## 📚 配套博客系列

三篇 CSDN 文章配合项目代码一起阅读，效果最佳。每篇文章在仓库内也保留了 Markdown 源稿。

| 版本 | 主题 | CSDN 在线版 | 仓库源稿 |
|---|---|---|---|
| **v1.0** | 从 0 到 1：AI 采集 Agent 从想法到能跑 | [📖 在 CSDN 阅读](https://blog.csdn.net/peaceworld_/article/details/162107888) | [`docs/blog/v1.0_*.md`](docs/blog/v1.0_AI采集Agent从0到1.md) |
| **v1.1** | 从能跑到稳定：5 个工程化升级（反爬 / 重试 / 调度 / 健壮性） | [📖 在 CSDN 阅读](https://blog.csdn.net/peaceworld_/article/details/162130079) | [`docs/blog/v1.1_*.md`](docs/blog/v1.1_从能跑到稳定.md) |
| **v2.0** | 为什么我把"加一个数据源"拆成了三个 Phase（重构思考） | [📖 在 CSDN 阅读](https://blog.csdn.net/peaceworld_/article/details/162179687) | [`docs/blog/v2.0_*.md`](docs/blog/v2.0_为什么我把加一个数据源拆成了三个Phase.md) |
| **v2.1** | 把采集器升级成 RAG 系统的一个夜晚（Milvus Lite + bge-m3 实战与踩坑） | _(待发布)_ | [`docs/blog/v2.1_*.md`](docs/blog/v2.1_把采集器升级成RAG系统的一个夜晚.md) |

---

## ✨ 项目亮点

- 🛡️ **反爬强**：Playwright + Stealth 模式，绕过常规的浏览器指纹检测
- 🧠 **AI 加持**：LLM 自动从混乱 HTML 中提取结构化数据（标题、UP 主、标签、核心要点等）
- 🔄 **状态机驱动**：基于 SQLite 的任务状态机（PENDING → PROCESSING → COLLECTED → COMPLETED）
- 💰 **成本优化**：直连火山引擎 Coding Plan，不走在线推理 Endpoint，避免按量计费
- 🛠️ **生产级工程**：模块化 4 层架构 + 完整日志 + 容错重试 + 限流反爬

---

## 📐 系统架构

```
┌─────────────────────────────────────────────────────────┐
│                    AI Pipeline                          │
└─────────────────────────────────────────────────────────┘
        │
        ▼
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│  ① Monitor   │ →  │ ② Collector  │ →  │ ③ Processor  │
│  B站API监控  │    │  Playwright  │    │  LLM 清洗    │
└──────────────┘    └──────────────┘    └──────────────┘
        │                  │                    │
        ▼                  ▼                    ▼
┌─────────────────────────────────────────────────────────┐
│              ④ DBManager (SQLite)                       │
│   urls_history | task_queue | raw_contents | results    │
└─────────────────────────────────────────────────────────┘
```

---

## 🛠️ 环境要求

| 组件 | 版本要求 |
| :--- | :--- |
| Python | 3.10+ (推荐 3.11) |
| 操作系统 | macOS / Linux / Windows |
| 浏览器内核 | Chromium (由 Playwright 自动安装) |
| LLM 服务 | 火山引擎 Coding Plan (或任何 OpenAI 兼容 API) |
| 数据库 | SQLite 3 (Python 内置) |
| 磁盘空间 | ≥ 500 MB (含 Chromium) |

### Python 依赖

```
playwright>=1.40.0         # 浏览器自动化
playwright-stealth>=2.0.0  # 反爬隐身插件
beautifulsoup4>=4.12.0     # HTML 解析
markdownify>=0.11.6        # HTML → Markdown
requests>=2.31.0           # HTTP 客户端
openai>=1.30.0             # LLM API 客户端
python-dotenv>=1.0.0       # 环境变量管理
pandas>=2.0.0              # 数据处理
```

---

## 🚀 部署指南

### 1. 克隆项目

```bash
git clone https://github.com/<你的用户名>/ai_collector_project.git
cd ai_collector_project
```

### 2. 创建虚拟环境

```bash
python3 -m venv .venv
source .venv/bin/activate          # macOS / Linux
# .venv\Scripts\activate            # Windows
```

### 3. 安装依赖

```bash
pip install -r requirements.txt

# 安装 Playwright 浏览器内核 (国内推荐用淘宝镜像加速)
PLAYWRIGHT_DOWNLOAD_HOST=https://npmmirror.com/mirrors/playwright \
    python -m playwright install chromium
```

### 4. 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env` 填入你的 LLM 凭证：

```ini
LLM_API_KEY=ark-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
LLM_API_BASE=https://ark.cn-beijing.volces.com/api/coding/v3
LLM_MODEL=kimi-k2.6
DB_PATH=data/collector.db
```

> 💡 **火山引擎 Coding Plan 配置**：
> - 在 [火山引擎控制台](https://console.volcengine.com/) → 火山方舟 → API Key 管理 中创建。
> - **Base URL 必须用 `/api/coding/v3`** （注意有 `/coding/` 字段），这样才能走套餐而非按量付费。

### 5. 运行系统

```bash
# 单次运行（默认每阶段处理 3 条）
python main.py

# 批量补跑（一次跑 N 条 PENDING）
python run_batch.py 10

# 通过 wrapper 脚本运行（适合 cron）
./run.sh
./run.sh --batch 10
```

首次运行会：
1. 自动创建 `data/collector.db` 数据库与 4 张表
2. **v1.1 新增**：自动把可重试的 FAILED 任务回滚到合适状态（COLLECTED 或 PENDING）
3. 检测 `task_queue` 中的 PENDING 任务
4. 用 Playwright 抓取网页（默认 `headless=True` 后台运行）
5. 调用 LLM 提取结构化数据
6. 写入日志到 `logs/pipeline.log`，最后输出 DB state 摘要

### 6. 配置定时运行（可选）

**方式 A — 系统 crontab：**

```bash
crontab -e

# 每天上午 9:30 自动跑
30 9 * * * /path/to/ai_collector_project/run.sh \
           >> /path/to/ai_collector_project/logs/cron.log 2>&1
```

**方式 B — Hermes Agent 调度（推荐，自带摘要推送）：**

```bash
# 见 ai_collector_cron.py，输出 8 行精简摘要发给你
# 摘要包含：新增 / 处理 / 失败统计 + 最新入库标题
```

---

## 📂 项目结构

```
ai_collector_project/
├── main.py                  # 主调度入口
├── requirements.txt         # Python 依赖清单
├── .env.example             # 环境变量模板
├── .env                     # (本地生成, 不提交)
├── .gitignore
├── README.md
│
├── src/                     # 核心模块
│   ├── db_manager.py        # SQLite 状态机
│   ├── monitor.py           # B 站 API 监控
│   ├── collector.py         # Playwright 采集器
│   └── processor.py         # LLM 清洗器
│
├── data/                    # 数据库目录 (运行时生成)
│   └── collector.db
│
├── logs/                    # 日志目录 (运行时生成)
│   └── pipeline.log
│
├── test_db.py               # 单元测试: 数据库
├── test_monitor.py          # 单元测试: 监控
├── test_collector.py        # 单元测试: 采集
└── test_processor.py        # 单元测试: LLM
```

---

## 📖 文件与函数详解

### `main.py` — 流水线总调度器

| 类 / 函数 | 功能 |
| :--- | :--- |
| `class AIPipeline` | 流水线总控，把 4 个模块串联成自动化系统 |
| `__init__(headless)` | 初始化所有依赖（DB / Monitor / Collector / Processor）+ 日志 |
| `stage1_monitor()` | **阶段 1**: 调用 monitor 发现新视频 URL，写入 task_queue |
| `stage2_collect(max_count)` | **阶段 2**: 从队列取 PENDING 任务，Playwright 抓取，限流 3-8 秒 |
| `stage3_process(max_count)` | **阶段 3**: 取 COLLECTED 任务，调 LLM 清洗为 JSON |
| `run()` | 异步执行三阶段完整流水线，输出耗时与统计 |
| `show_results()` | 终端打印最近 5 条 LLM 结构化结果 |

### `src/db_manager.py` — 数据持久化层

| 函数 | 功能 |
| :--- | :--- |
| `__init__(db_path)` | 初始化 SQLite 连接，自动创建 4 张表 |
| `_init_db()` | 建表：`urls_history` / `task_queue` / `raw_contents` / `final_results` |
| `add_new_urls(urls)` | 批量插入新 URL，自动去重 |
| `get_pending_tasks(limit)` | 拉取待采集任务 |
| `update_task_status(url, status)` | 状态机流转：PENDING → PROCESSING → COLLECTED → COMPLETED / FAILED |
| `save_raw_content(url, text)` | 保存 Playwright 抓取的 Markdown |
| `save_final_result(url, json_data)` | 保存 LLM 清洗结果 |

### `src/monitor.py` — 内容监控层

| 函数 | 功能 |
| :--- | :--- |
| `class BiliMonitor` | B 站监控器，直连 `api.bilibili.com` |
| `fetch_user_videos(uid)` | 拉取指定 UP 主最新视频列表 (含 UA + Referer 伪装) |
| `sync_targets(uids)` | 批量同步多个 UID，新视频写入 task_queue |

### `src/collector.py` — 内容采集层

| 函数 | 功能 |
| :--- | :--- |
| `class BiliCollector` | Playwright 异步采集器 |
| `__init__(headless)` | 初始化，可选可视化模式（调试用） |
| `collect_content(url)` | 核心采集方法：**Stealth 反爬** + **图片资源拦截** + **智能等待** + **HTML→Markdown** |

**采集器 4 大杀手锏**:
1. `Stealth().apply_stealth_async()` — 抹除自动化指纹
2. `route("**/*.{png,jpg,...}", abort)` — 拦截图片资源，提速 3-5 倍
3. `wait_for_selector(".video-desc")` — 智能等待关键 DOM 渲染
4. `markdownify(html)` — HTML 转 Markdown 压缩 Token 消耗

### `src/processor.py` — LLM 清洗层

| 函数 | 功能 |
| :--- | :--- |
| `class LLMProcessor` | 火山引擎 Coding Plan 客户端封装 |
| `__init__()` | 从 `.env` 读取凭证，初始化 OpenAI 兼容客户端 |
| `_build_prompt(markdown)` | 构造结构化提取 Prompt（限制返回纯 JSON） |
| `clean_data(markdown)` | 调 LLM 清洗 → 验证 JSON 合法性 → 返回结构化字符串 |

**LLM 提取字段**: `title` / `up_name` / `publish_time` / `play_count` / `danmaku_count` / `tags` / `summary` / `key_points`

---

## 🎯 当前能做什么

✅ **内容采集**
- 从指定 B 站 UP 主或视频 URL 列表批量抓取页面内容
- 反爬效果良好（Stealth + 限流 + UA 伪装）
- 支持异步并发，单页耗时约 15-25 秒

✅ **AI 结构化提取**
- 自动提取标题、UP 主、播放量、标签等显式字段
- 基于上下文**推断**视频核心要点（即使描述区为空）
- 输出标准 JSON，可直接喂给下游分析或可视化系统

✅ **任务流水线**
- 完整状态机管理（PENDING/PROCESSING/COLLECTED/COMPLETED/FAILED）
- 单点失败不影响整体（容错隔离）
- 日志可追溯，便于排查

✅ **成本控制**
- 火山 Coding Plan 直连，避免在线推理按量计费
- HTML→Markdown 压缩，节省 50%+ Token
- 抓取限流，避免触发反爬被封

---

## 📜 Changelog

### v1.1 (2026-06-17) — Stability Release

修复了 v1.0 在真实环境下暴露的 4 个核心问题，并加入定时运行支持。

🛡️ **B 站反爬升级**
- 参数 `uid=` → `mid=`（B 站官方推荐，老参数已逐步弃用）
- 完整浏览器 headers（UA + Referer + Origin + Accept-Language）
- 支持 `.env` 里配置 `BILI_COOKIE`，requests / Playwright 双路径都注入登录态
- 识别 B 站业务错误码（-799 WBI 签名 / -412 风控 / -111 鉴权）
- HTTP 412/403/429 或业务错误 → 自动 fallback 到 Playwright（打开 space 页扒 BV 号）

🔍 **Collector 选择器全面更新**（基于 2026-06 实地探测）
- `.video-desc` / `.desc-content` ❌ 已下线
- `.video-desc-container` / `#v_desc` ✅ 新主选择器
- title / up_name / desc / tags 4 个核心字段独立提取，多套备选选择器降级
- 结构化字段拼到 markdown 顶部，给 LLM 明确 anchor

🧠 **LLM 处理健壮性**
- `max_tokens` 2000 → 4000，避免长内容 JSON 截断
- 输入上下文上限 6000 → 8000，更多 anchor 给 LLM
- 新增 `_safe_json_parse()` 二段解析（直接 + 截取大括号）
- 失败时把原始 LLM 输出落盘到 `logs/llm_failures/`，便于复盘
- 检测 `finish_reason="length"` 主动告警
- LLM 单次请求 90s 超时，避免偶发长尾卡死整个流水线

🔁 **失败自动重试**
- `task_queue` 表新增 `error_message` + `last_attempt_at` 字段（幂等迁移，老库自动升级）
- `mark_failed(url, reason)` 替代 `update_task_status('FAILED')`，记录失败原因 + 自增 retry_count
- `requeue_failed(max_retry=3)` 智能恢复：
    - 已有 `raw_contents`（LLM 阶段失败）→ 回到 COLLECTED，跳过重抓
    - 没有 `raw_contents`（采集阶段失败）→ 回到 PENDING，从头重试
    - `retry_count >= max_retry` 保留 FAILED，不再重试
- `main.py` 启动时自动调用 `requeue_failed()`，失败任务下次自动复活

⏰ **定时运行支持**
- `run.sh`：POSIX shell wrapper，可直接挂到 crontab/launchd/systemd
- `run.sh --batch N`：一次跑 N 条 PENDING（手动追赶用）
- `ai_collector_cron.py`：8 行精简摘要的 cron entrypoint
- 计算运行前后 DB diff，输出新增 / 处理 / 失败统计 + 最新入库标题

📊 **运行报告增强**
- `db.get_run_summary()` 返回状态 histogram + final_results 计数
- Pipeline 收尾日志新增 requeue 统计 + DB state 全景

🐛 **Bug 修复**
- main.py 在 async 上下文中调用同步 `sync_targets()` 导致 `RuntimeError: event loop is already running` —— 已加 `sync_targets_async()` 异步入口
- `print()` 全部替换为 `logger`，方便日志收集

🧪 **实战验证**
- 端到端跑通：从 0 个数据 → 18 条 AI 行业新闻入库（涵盖 GLM-5.2 / Cursor 收购 / DiffusionGemma 等）
- 验证了失败自动重试：昨天 v1.0 留下的 1 条 FAILED 在今天自动复活
- 验证了 LLM timeout：偶发 90s+ 长尾不再卡死流水线

---

## 🔧 优化空间 (Roadmap v1.2+)

### 🟡 中优先级

- [ ] **元数据补齐**：collector 当前只抓 4 个字段（title/up/desc/tags），扩展到 7 个：publish_time、play_count、danmaku_count
- [ ] **OpenAI SDK retry 控制**：`max_retries=2` 默认值导致单条 LLM 失败要 5 分钟，考虑改 `max_retries=0` 让流水线快速跳过
- [ ] **支持更多平台**：知乎、微博、小红书、Twitter/X
- [ ] **持久化登录态**：Playwright `storage_state` 保留 Cookie，免得每天手动复制
- [ ] **去重机制升级**：基于 URL 规范化（去除 `?spm_id_from=` 等参数）
- [ ] **并发采集**：用 `asyncio.gather` 并发抓取多个 URL

### 🟢 长期规划

- [ ] **LLM 切换层**：抽象 LLM Provider，支持 DeepSeek / OpenAI / Claude / 本地 Ollama
- [ ] **Web UI 可视化**：用 Streamlit 或 FastAPI 展示采集结果
- [ ] **Embedding + 向量库**：将结构化数据存入 ChromaDB / Weaviate，支持语义搜索
- [ ] **Agent 化**：引入 LangGraph，让系统自己决定下一步采集策略
- [ ] **告警通知**：采集到关键内容时推送到微信/Telegram

### ✅ 已在 v1.1 解决（v1.0 时代的高优先级问题）

- [x] ~~B 站 API 412 风控~~ → cookie 注入 + Playwright fallback
- [x] ~~LLM Token 截断~~ → max_tokens 4000 + 二段 JSON 解析 + 90s timeout
- [x] ~~DOM 选择器过期~~ → 多套备选选择器 + 结构化字段独立抓取
- [x] ~~失败重试~~ → mark_failed + requeue_failed + 自动复活
- [x] ~~Cron 自动化~~ → run.sh + ai_collector_cron.py

---

## 🧪 测试

```bash
# 单元测试
python test_db.py             # 数据库读写
python test_monitor.py        # B 站 API 监控
python test_collector.py      # Playwright 采集 (会弹出浏览器窗口)
python test_processor.py      # LLM 清洗

# 全流水线集成测试
python main.py
```

---

## 📊 数据库 Schema

### `task_queue` (任务队列)
| 字段 | 类型 | 说明 |
| :--- | :--- | :--- |
| id | INTEGER | 主键自增 |
| url | TEXT UNIQUE | 视频 URL |
| status | TEXT | PENDING/PROCESSING/COLLECTED/COMPLETED/FAILED |
| retry_count | INTEGER | 重试次数 (v1.1 起由 `mark_failed` 自动维护) |
| error_message | TEXT | **v1.1 新增** — 最近一次失败原因（截断 500 字） |
| last_attempt_at | DATETIME | **v1.1 新增** — 最近一次执行时间 |
| created_at | DATETIME | 入队时间 |

### `raw_contents` (原始抓取)
| 字段 | 类型 | 说明 |
| :--- | :--- | :--- |
| url | TEXT PK | 视频 URL |
| markdown_text | TEXT | Playwright 抓取的 Markdown |
| collected_at | DATETIME | 抓取完成时间 |

### `final_results` (LLM 清洗结果)
| 字段 | 类型 | 说明 |
| :--- | :--- | :--- |
| id | INTEGER | 主键自增 |
| url | TEXT | 视频 URL |
| structured_json | TEXT | LLM 输出的结构化 JSON |
| processed_at | DATETIME | 处理完成时间 |

---

## 📝 LLM 输出示例

```json
{
  "title": "【官方 MV】Never Gonna Give You Up - Rick Astley",
  "up_name": "索尼音乐中国",
  "publish_time": "2020-01-01 07:43:23",
  "play_count": "9977.2万",
  "danmaku_count": "13.8万",
  "tags": ["Never Gonna Give You Up", "Rick Astley", "欧美MV"],
  "summary": "Rick Astley 经典代表作《Never Gonna Give You Up》的官方 MV...",
  "key_points": [
    "经典 80 年代流行金曲官方 MV",
    "Rick Astley 标志性嗓音与舞蹈动作回顾",
    "Rickroll 网络梗文化现象"
  ]
}
```

---

## 🤝 贡献

这是一个学习项目，欢迎 Issue 和 PR！

## 📄 License

MIT License

## 🙏 致谢

- [Playwright](https://playwright.dev/) — 强大的浏览器自动化框架
- [playwright-stealth](https://github.com/AtuboDad/playwright_stealth) — 反爬隐身插件
- [火山引擎方舟](https://www.volcengine.com/product/ark) — 高性价比 LLM 服务
- 灵感来自 RSSHub / Newsblur 等开源信息聚合项目

---

**v1.0 — 2026-06-16** | Built with ❤️ by AI Agent 学习者
