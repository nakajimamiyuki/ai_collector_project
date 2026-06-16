# 🤖 AI Collector Project — 智能内容采集系统 v1.0

> 一个集成 **Playwright 反爬采集 + LLM 结构化清洗** 的全自动化 B 站内容监控与分析系统。
> 这不是传统爬虫，而是一个具备**自主决策、内容理解、容错恢复**能力的 AI Agent。

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
python main.py
```

首次运行会：
1. 自动创建 `data/collector.db` 数据库与 4 张表
2. 检测 `task_queue` 中的 PENDING 任务
3. 用 Playwright 抓取网页（默认 `headless=True` 后台运行）
4. 调用 LLM 提取结构化数据
5. 写入日志到 `logs/pipeline.log`

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

## 🔧 优化空间 (Roadmap v2.0)

### 🔴 高优先级

| 问题 | 现象 | 解决方向 |
| :--- | :--- | :--- |
| **B 站 API 412 风控** | Monitor 阶段无法获取新视频列表 | 改用 Playwright 抓 UP 主空间页 / 注入 Cookie |
| **LLM Token 截断** | 长文本 JSON 输出被截断导致解析失败 | 把 `max_tokens` 提到 4000+ / 使用流式响应 / Prompt 限制总结字数 |
| **DOM 选择器过期** | `.video-desc` 在新版 B 站找不到 | 升级为多选择器 fallback 机制 |

### 🟡 中优先级

- [ ] **支持更多平台**：知乎、微博、小红书、Twitter/X
- [ ] **持久化登录态**：Playwright 持久化 context 保留 Cookie
- [ ] **失败重试**：对 FAILED 任务自动重试 3 次（带指数退避）
- [ ] **去重机制升级**：基于 URL 规范化（去除 `?spm_id_from=` 参数等）
- [ ] **并发采集**：用 `asyncio.gather` 并发抓取多个 URL
- [ ] **Cron 自动化**：crontab 定时调度（每 4 小时一次）

### 🟢 长期规划

- [ ] **LLM 切换层**：抽象 LLM Provider，支持 DeepSeek / OpenAI / Claude / 本地 Ollama
- [ ] **Web UI 可视化**：用 Streamlit 或 FastAPI 展示采集结果
- [ ] **Embedding + 向量库**：将结构化数据存入 ChromaDB / Weaviate，支持语义搜索
- [ ] **Agent 化**：引入 LangGraph，让系统自己决定下一步采集策略
- [ ] **告警通知**：采集到关键内容时推送到微信/Telegram

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
| retry_count | INTEGER | 重试次数 |
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
