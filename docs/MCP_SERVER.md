# ai_collector MCP Server 使用说明

> v3.1 Phase 1：把 ai_collector 的岗位检索能力暴露成 MCP Tool，
> 让 Claude Desktop / Cursor / Hermes Agent 等 MCP 客户端直接调用。

## 1. 当前能力

当前 MCP Server 名称：`ai-collector`

当前暴露 1 个 Tool：

```text
search_jobs(keyword: str, city: str = "", top_k: int = 5) -> str
```

功能：从本地 `data/collector.db` 的 192 条 Boss 直聘岗位中检索。

匹配范围：

- 岗位标题
- 公司名
- JD 正文
- 摘要
- skills
- tags

返回格式：JSON 字符串。

示例返回结构：

```json
{
  "query": {"keyword": "MCP", "city": "杭州", "top_k": 2},
  "total_matched": 5,
  "returned": 2,
  "jobs": [
    {
      "id": 123,
      "title": "AI Agent 开发工程师",
      "company": "某某科技",
      "city": "杭州",
      "salary": "15-30K",
      "experience": "1-3年",
      "degree": "本科",
      "skills": ["Python", "MCP", "LangGraph"],
      "summary": "...",
      "url": "https://www.zhipin.com/job_detail/..."
    }
  ]
}
```

---

## 2. 安装依赖

项目共享 venv：

```bash
/Users/minjie/shangguigu/.venv/bin/python -m pip install -r requirements.txt \
  -i https://mirrors.aliyun.com/pypi/simple/
```

关键依赖已锁定：

```text
mcp==1.26.0
```

为什么锁版本：`mcp 1.28.0` 会拉高 `starlette` 到 `1.3.1`，
与项目中已有 `fastapi 0.115.11` 的 `starlette<0.47.0` 约束冲突。
`mcp==1.26.0 + starlette==0.46.2` 已验证可用。

---

## 3. 本地 smoke test

### 3.1 直接函数调用

```bash
cd /Users/minjie/shangguigu/ai_collector_project
/Users/minjie/shangguigu/.venv/bin/python - <<'PY'
import json
from src.mcp_server.ai_collector_mcp import search_jobs

raw = search_jobs.fn('MCP', city='杭州', top_k=2) if hasattr(search_jobs, 'fn') else search_jobs('MCP', city='杭州', top_k=2)
data = json.loads(raw)
print(data['total_matched'], data['returned'])
for job in data['jobs']:
    print(job['title'], job['company'], job['salary'])
PY
```

预期：

```text
5 2
...
```

### 3.2 MCP stdio Client 调用

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
            result = await session.call_tool('search_jobs', {'keyword': 'MCP', 'city': '杭州', 'top_k': 2})
            data = json.loads(result.content[0].text)
            print('total_matched:', data['total_matched'])
            for job in data['jobs']:
                print(job['title'], job['company'], job['salary'])

asyncio.run(main())
PY
```

预期：

```text
tools: ['search_jobs']
total_matched: 5
...
```

---

## 4. Hermes Agent 配置示例

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

然后重启 Hermes。

重启后，Hermes 工具列表中应出现：

```text
mcp_ai_collector_search_jobs
```

可直接问：

```text
杭州有哪些提到 MCP 的 AI Agent 岗位？
```

预期：Hermes 自动调用 `mcp_ai_collector_search_jobs`，返回本地 SQLite 中的真实岗位数据。

---

## 5. Claude Desktop 配置示例

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
帮我查一下杭州有哪些提到 MCP 的岗位
```

---

## 6. 下一步计划

v3.1 后续会继续暴露：

- `match_profile(jd_id)`：按 `my_profile.yaml` 对岗位打分
- `query_rag(question, top_k)`：查询 Milvus RAG 索引
- `get_skill_gap_summary()`：统计市场技能热度 + 我的缺口

当前版本只保证 `search_jobs` 最小闭环稳定。
