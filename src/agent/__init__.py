"""
v3.0 求职 Agent 模块。

把 ai_collector_project 从「RAG 检索器」升级为「真 Agent」的关键一层。

公开 API
--------
- `find_jobs(query: str) -> JobAgentResult`：自然语言查询，端到端跑完整 Agent

模块拆分
--------
- tools.py    — 可被 LLM 调用的工具（vector_search / filter_jobs / ...）
- nodes.py    — LangGraph 节点（parse_intent / retrieve / reflect / summarize）
- graph.py    — 把节点编成 DAG + 入口函数
- prompts.py  — 系统/节点 prompt（独立文件方便迭代）
- my_profile.yaml — 用户画像（学历 / 年限 / 已具备技能）
"""

from src.agent.graph import find_jobs, JobAgentResult  # noqa: F401
