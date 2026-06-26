# ai_collector MCP Server 使用说明

> v3.1 Phase 1：把 ai_collector 的核心检索能力暴露成 MCP Tool，
> 让 Claude Desktop / Cursor / Hermes Agent 等 MCP 客户端直接调用。

## 1. 当前能力

MCP Server 名称：`ai-collector`

当前暴露 **3 个 Tool**：

| Tool | 输入 | 输出 | 说明 |
|------|------|------|------|
| `search_jobs` | keyword, city, top_k | JSON 岗位列表 | 字面包含匹配（标题/公司/JD/技能/tags） |
| `query_rag` | question, top_k | JSON 命中列表（带 score） | bge-m3 + Milvus 语义检索，能召回近义词 |
| `get_skill_gap` | top_n | JSON 技能热度+缺口 | 市场技能 Top N + 我的画像缺口对照 |

### 1.1 search_jobs（关键词匹配）

```text
search_jobs(keyword: str, city: str = "", top_k: int = 5) -> str
```

从本地 `data/collector.db` 的 192 条 Boss 直聘岗位中检索。

匹配范围：岗位标题 / 公司名 / JD 正文 / 摘要 / skills / tags。

适合：HR / 你自己已经知道要找哪个关键词时（"MCP"、"LangChain"、"杭州 RAG"）。

示例返回结构：

```json
{
  "query": {"keyword": "MCP", "city": "杭州", "top_k": 2},
  "total_matched": 5,
  "returned": 2,
  "jobs": [
    {
      "id": 291,
      "title": "Agent 开发工程师（Java 方向）",
      "company": "浙江立讯智联科技",
      "city": "杭州",
      "salary": "12-16K",
      "experience": "1-3年",
      "degree": "本科",
      "skills": ["Java", "后端开发经验"],
      "summary": "...",
      "url": "https://www.zhipin.com/job_detail/..."
    }
  ]
}
```

### 1.2 query_rag（语义检索）

```text
query_rag(question: str, top_k: int = 5) -> str
```

走本地 Ollama `bge-m3:latest`（1024 维）+ Milvus Lite 向量库 `data/vector.db`。

适合：你说不清楚要什么关键词、但能描述"我想找的岗位长什么样"。

例子：
- 问：「会用 LangGraph 做反思决策的 Agent 岗位」
- 命中：JD 里写了「基于 LangGraph、LangChain、AutoGen 框架开发 Agent + 运用 CoT」
- 字面匹配根本搜不到「反思决策」这个词，但语义匹配能召回

返回字段：`url / title / score（0-1 余弦相似度）/ company / city / salary / experience / degree / skills / short_desc`。

**前置条件**：

```bash
# 1. 启动 ollama 并拉模型（已 pull 过的话 skip）
ollama serve &
ollama pull bge-m3

# 2. 至少跑过一次索引
python scripts/index_final_results.py
```

如果 ollama 没起 / 向量库没建，工具会返回 `{"error": "...", "hint": "..."}` 而不是抛异常，
客户端能直接拿到可读错误。

### 1.3 get_skill_gap（市场热度 + 个人缺口）

```text
get_skill_gap(top_n: int = 10) -> str
```

在已采集的全部 192 条 Boss 岗位上做技能词频聚合，对照 `src/agent/my_profile.yaml` 算缺口。

返回字段：

- `total_jobs_analyzed`：本次统计基于多少条岗位
- `market_top_skills`：市场上出现次数最多的技能 Top N
- `skill_gap`：我未掌握、但市场高频出现的技能（按命中次数降序，带 `is_learning` 标记）
- `already_have_hits`：我已具备且市场上确实在要的技能（验证学习方向）
- `learning_hits`：我正在学的技能在市场上的热度

实际数据示例（192 条 Boss JD）：

```text
market_top_skills:
  Python        108
  Agent         106
  RAG            82
  Prompt         72
  LangChain      66

skill_gap (我没掌握但市场要的):
  Agent         106
  Prompt         72
  Java           48     ← 转 Java 系会大幅扩盘
  微调            43
  LlamaIndex     32

learning_hits (我正在学的市场热度):
  多模态          41     ← 学这个 ROI 高
  Dify           25
  Coze           16
  LangGraph      16
  MCP            14     ← 学这个稀缺度高
```

适合面试场景：「你怎么决定接下来学什么？」「我让 Agent 给我画了张缺口热力图，按 ROI 排序。」

---

## 2. 安装依赖

项目共享 venv：

```bash
/Users/minjie/shangguigu/.venv/bin/python -m pip install -r requirements.txt \
  -i https://mirrors.aliyun.com/pypi/simple/
```

关键依赖：

```text
mcp==1.26.0
```

为什么锁版本：`mcp 1.28.0` 会拉高 `starlette` 到 `1.3.1`，
与项目中已有 `fastapi 0.115.11` 的 `starlette<0.47.0` 约束冲突。
`mcp==1.26.0 + starlette==0.46.2` 已验证可用。

---

## 3. 已知坑（必读）

### 3.1 macOS OpenMP 双库 abort

`milvus-lite` + `faiss` + `ollama` 在 macOS 同进程会触发：

```text
OMP: Error #15: Initializing libomp.dylib, but found libomp.dylib already initialized.
```

直接 abort，stdio 连接被 client 看到 `Connection closed`。

**修复**：MCP server 入口文件顶部已经写好：

```python
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
```

只要走 `python src/mcp_server/ai_collector_mcp.py` 启动，就自动生效。

### 3.2 子进程 sys.path 不含项目根

`python src/mcp_server/...py` 直接当脚本跑时，sys.path 只有脚本所在目录，
延迟 import `from src.agent.tools import ...` 会 `ModuleNotFoundError: No module named 'src'`。

**修复**：MCP server 入口顶部已经把 PROJECT_ROOT 注入 sys.path。

### 3.3 query_rag 首次调用慢

Milvus Lite 第一次启动需要 ~3 秒拉服务进程。后续调用同一个 server 会复用，毫秒级。

---

## 4. 本地 smoke test

### 4.1 直接函数调用（最快）

```bash
cd /Users/minjie/shangguigu/ai_collector_project
/Users/minjie/shangguigu/.venv/bin/python - <<'PY'
import json
from src.mcp_server.ai_collector_mcp import search_jobs, query_rag, get_skill_gap

for tool, args in [
    (search_jobs, dict(keyword='MCP', city='杭州', top_k=2)),
    (get_skill_gap, dict(top_n=5)),
    # query_rag 需要 ollama + vector.db 在线
    # (query_rag, dict(question='LangGraph 反思决策', top_k=2)),
]:
    fn = getattr(tool, 'fn', None) or tool
    print(json.loads(fn(**args)))
PY
```

### 4.2 MCP stdio Client 调用（端到端）

```bash
cd /Users/minjie/shangguigu/ai_collector_project
/Users/minjie/shangguigu/.venv/bin/python - <<'PY'
import asyncio, json
from pathlib import Path
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def main():
    server = StdioServerParameters(
        command='/Users/minjie/shangguigu/.venv/bin/python',
        args=[str(Path('src/mcp_server/ai_collector_mcp.py').resolve())],
    )
    async with stdio_client(server) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            print('tools:', [t.name for t in tools.tools])
            result = await session.call_tool('get_skill_gap', {'top_n': 5})
            print(result.content[0].text)

asyncio.run(main())
PY
```

预期输出 `tools: ['search_jobs', 'query_rag', 'get_skill_gap']`。

---

## 5. Hermes Agent 配置

编辑：

```text
/Users/minjie/.hermes/config.yaml
```

加入：

```yaml
mcp_servers:
  ai_collector:
    command: "/Users/minjie/shangguigu/.venv/bin/python"
    args:
      - "/Users/minjie/shangguigu/ai_collector_project/src/mcp_server/ai_collector_mcp.py"
    timeout: 60
    connect_timeout: 30
```

重启 Hermes 后，工具列表中会出现：

```text
mcp_ai_collector_search_jobs
mcp_ai_collector_query_rag
mcp_ai_collector_get_skill_gap
```

可以直接问：

- 「杭州有哪些提到 MCP 的岗位？」→ 走 `search_jobs`
- 「找一些会用 LangGraph 做反思决策的 Agent 岗」→ Hermes 应选 `query_rag`
- 「市场上现在最缺哪些技能？我应该接下来学什么？」→ 走 `get_skill_gap`

---

## 6. Claude Desktop 配置

编辑：

```text
~/Library/Application Support/Claude/claude_desktop_config.json
```

加入：

```json
{
  "mcpServers": {
    "ai-collector": {
      "command": "/Users/minjie/shangguigu/.venv/bin/python",
      "args": [
        "/Users/minjie/shangguigu/ai_collector_project/src/mcp_server/ai_collector_mcp.py"
      ]
    }
  }
}
```

重启 Claude Desktop 后问：

```text
帮我用 query_rag 查"会用 LangGraph + RAG 的初中级岗位"，再用 get_skill_gap 看我离这些岗位差什么技能
```

---

## 7. 路线图

✅ 已完成（v3.1 Phase 1）：

- `search_jobs(keyword, city, top_k)`
- `query_rag(question, top_k)`
- `get_skill_gap(top_n)`

🔜 后续：

- `match_profile(jd_id)`：按 `my_profile.yaml` 对单个岗位做 0-100 分匹配
- 资源（Resources）暴露：让客户端能 `read_resource` 拉某个具体 JD 全文
- HTTP/SSE 传输：脱离单机 stdio，云端调用

---

## 8. 简历金句

> 自研一个 MCP Server（ai-collector），暴露 3 个 Tool：
> 字面检索（search_jobs）、语义检索（query_rag，bge-m3 + Milvus）、
> 个人技能缺口分析（get_skill_gap，对照本地 YAML 画像）。
> Server 已在 Hermes Agent 与 Claude Desktop 两端验证可调用，
> 单元测试 11 个全绿（4 个 search_jobs / 4 个 query_rag / 3 个 get_skill_gap）。
