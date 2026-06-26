"""v3.0 求职 Agent 的运行记录 + Bad Case 闭环存储。

为什么独立一个库（不塞进 collector.db）：
- collector.db 是 v1/v2 pipeline 的状态机，schema 已稳定，不想加新表污染
- agent_runs 是 v3 维度的数据，未来想单独导出/迁移更方便
- 单元测试时能直接 monkeypatch DB_PATH，零干扰

字段说明：
- status:
    'unreviewed'  跑完默认，人没看
    'good'        命中预期，结果可用
    'bad'         命中失败 / 结果错配 / 反思耗光
- root_cause:     bad case 时的根因（自由文本，建议用固定标签）
                  推荐标签: data_sparse / prompt_off / filter_too_strict / rag_miss / llm_error
- fix_commit:     修这条 bad case 对应的 git 短 SHA（手动 mark 时填）
"""
from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterator

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "agent_runs.db"


# ----------------------------------------------------------------------
# 数据类（DTO）
# ----------------------------------------------------------------------
@dataclass
class AgentRun:
    """一次 Agent 跑的完整记录。"""

    id: int | None
    run_at: str                      # ISO timestamp
    query: str
    result_count: int                # filter 后的最终结果数
    elapsed_seconds: float
    reflect_rounds: int
    status: str                      # 'unreviewed' / 'good' / 'bad'
    root_cause: str = ""
    fix_commit: str = ""
    fix_notes: str = ""
    trace_json: str = ""             # 序列化后的 trace（list[str]）
    final_report: str = ""


VALID_STATUSES = {"unreviewed", "good", "bad"}


# ----------------------------------------------------------------------
# Store
# ----------------------------------------------------------------------
class BadCaseStore:
    """对 agent_runs 表的薄封装。所有方法都是同步的，单 SQLite 足够。"""

    def __init__(self, db_path: str | Path = DEFAULT_DB_PATH):
        self.db_path = Path(db_path)
        os.makedirs(self.db_path.parent, exist_ok=True)
        self._init_db()

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_db(self) -> None:
        """幂等建表。"""
        with self._conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS agent_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_at DATETIME NOT NULL,
                    query TEXT NOT NULL,
                    result_count INTEGER NOT NULL,
                    elapsed_seconds REAL DEFAULT 0,
                    reflect_rounds INTEGER DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'unreviewed',
                    root_cause TEXT DEFAULT '',
                    fix_commit TEXT DEFAULT '',
                    fix_notes TEXT DEFAULT '',
                    trace_json TEXT DEFAULT '',
                    final_report TEXT DEFAULT ''
                )
                """
            )
            # 索引：按 status 列 list 用，按 run_at 排序用
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_agent_runs_status "
                "ON agent_runs(status)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_agent_runs_run_at "
                "ON agent_runs(run_at DESC)"
            )

    # ------------------------------------------------------------------
    # 写入
    # ------------------------------------------------------------------
    def record_run(
        self,
        *,
        query: str,
        result_count: int,
        elapsed_seconds: float,
        reflect_rounds: int = 0,
        trace: list[str] | None = None,
        final_report: str = "",
        status: str = "unreviewed",
    ) -> int:
        """落一条新记录，返回 id。

        result_count == 0 时**自动**把 status 设为 'bad'（明显的零命中）。
        如果上层已经给了 status='good'，不覆盖。
        """
        if status not in VALID_STATUSES:
            raise ValueError(
                f"invalid status {status!r}, must be one of {sorted(VALID_STATUSES)}"
            )

        # 零结果 = 明显的 bad case；除非调用方坚持是 good，否则自动 mark
        auto_bad_reason = ""
        if result_count == 0 and status == "unreviewed":
            status = "bad"
            auto_bad_reason = "zero_result"

        with self._conn() as conn:
            cursor = conn.execute(
                """
                INSERT INTO agent_runs
                    (run_at, query, result_count, elapsed_seconds, reflect_rounds,
                     status, root_cause, trace_json, final_report)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    datetime.now().isoformat(timespec="seconds"),
                    query,
                    int(result_count),
                    float(elapsed_seconds),
                    int(reflect_rounds),
                    status,
                    auto_bad_reason,
                    json.dumps(trace or [], ensure_ascii=False),
                    final_report,
                ),
            )
            return int(cursor.lastrowid or 0)

    def mark(
        self,
        run_id: int,
        *,
        status: str | None = None,
        root_cause: str | None = None,
        fix_commit: str | None = None,
        fix_notes: str | None = None,
    ) -> bool:
        """人工 review 后更新一条记录。返回是否真的更新成功。

        所有字段都是可选的——只想改 root_cause 就只传 root_cause。
        """
        if status is not None and status not in VALID_STATUSES:
            raise ValueError(
                f"invalid status {status!r}, must be one of {sorted(VALID_STATUSES)}"
            )

        sets: list[str] = []
        values: list[object] = []
        if status is not None:
            sets.append("status = ?")
            values.append(status)
        if root_cause is not None:
            sets.append("root_cause = ?")
            values.append(root_cause)
        if fix_commit is not None:
            sets.append("fix_commit = ?")
            values.append(fix_commit)
        if fix_notes is not None:
            sets.append("fix_notes = ?")
            values.append(fix_notes)

        if not sets:
            return False

        values.append(run_id)
        with self._conn() as conn:
            cursor = conn.execute(
                f"UPDATE agent_runs SET {', '.join(sets)} WHERE id = ?",
                values,
            )
            return cursor.rowcount > 0

    # ------------------------------------------------------------------
    # 读取
    # ------------------------------------------------------------------
    def get(self, run_id: int) -> AgentRun | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM agent_runs WHERE id = ?", (run_id,)
            ).fetchone()
        return _row_to_run(row) if row else None

    def list(
        self,
        *,
        status: str | None = None,
        limit: int = 50,
    ) -> list[AgentRun]:
        """按时间倒序列表；可按 status 过滤。"""
        sql = "SELECT * FROM agent_runs"
        params: list[object] = []
        if status:
            sql += " WHERE status = ?"
            params.append(status)
        sql += " ORDER BY run_at DESC, id DESC LIMIT ?"
        params.append(int(limit))

        with self._conn() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [_row_to_run(r) for r in rows]

    def stats(self) -> dict[str, int]:
        """各 status 的计数。"""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT status, COUNT(*) AS n FROM agent_runs GROUP BY status"
            ).fetchall()
        out = {"unreviewed": 0, "good": 0, "bad": 0}
        for r in rows:
            out[r["status"]] = r["n"]
        out["total"] = sum(out.values())
        return out


# ----------------------------------------------------------------------
# 工具：row -> AgentRun
# ----------------------------------------------------------------------
def _row_to_run(row: sqlite3.Row) -> AgentRun:
    return AgentRun(
        id=row["id"],
        run_at=row["run_at"],
        query=row["query"],
        result_count=row["result_count"],
        elapsed_seconds=row["elapsed_seconds"] or 0.0,
        reflect_rounds=row["reflect_rounds"] or 0,
        status=row["status"],
        root_cause=row["root_cause"] or "",
        fix_commit=row["fix_commit"] or "",
        fix_notes=row["fix_notes"] or "",
        trace_json=row["trace_json"] or "",
        final_report=row["final_report"] or "",
    )
