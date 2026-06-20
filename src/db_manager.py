import sqlite3
import os
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class DBManager:
    # v1.1: 失败任务最大重试次数
    DEFAULT_MAX_RETRY = 3

    def __init__(self, db_path="data/collector.db"):
        self.db_path = db_path
        # 确保 data 文件夹存在
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()
        self._migrate_v1_1()  # v1.1: 兼容旧库的字段升级
        self._migrate_v2_0()  # v2.0: 增加 source_type 字段并回填老数据

    def _get_connection(self):
        """获取数据库连接，设置 row_factory 使结果可以通过列名访问"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        """初始化数据库表结构"""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # 1. URL 历史表：记录所有见过并处理过的 URL
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS urls_history (
                    url TEXT PRIMARY KEY,
                    first_seen_at DATETIME,
                    last_seen_at DATETIME
                )
            ''')

            # 2. 任务队列表：驱动采集和处理的流程
            #    v1.1: 新表创建时直接带上 error_message 和 last_attempt_at
            #    v2.0: 增加 source_type，标记内容来源（bilibili / arxiv / ...）
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS task_queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT UNIQUE,
                    status TEXT DEFAULT 'PENDING',
                    source_type TEXT DEFAULT 'bilibili',
                    retry_count INTEGER DEFAULT 0,
                    error_message TEXT,
                    last_attempt_at DATETIME,
                    created_at DATETIME
                )
            ''')

            # 3. 原始内容表：存储 Playwright 抓取的 Markdown
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS raw_contents (
                    url TEXT PRIMARY KEY,
                    markdown_text TEXT,
                    collected_at DATETIME,
                    FOREIGN KEY (url) REFERENCES task_queue (url)
                )
            ''')

            # 4. 最终结果表：存储 LLM 清洗后的结构化数据
            #    v2.0: 增加 source_type，便于按来源分组（如飞书报告分类）
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS final_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT,
                    source_type TEXT DEFAULT 'bilibili',
                    structured_json TEXT,
                    processed_at DATETIME,
                    FOREIGN KEY (url) REFERENCES task_queue (url)
                )
            ''')
            conn.commit()

    def _migrate_v1_1(self):
        """
        v1.1 schema migration：兼容旧库（v1.0 创建的 task_queue 没有
        error_message / last_attempt_at 字段）。幂等：每次启动安全调用。
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(task_queue)")
            existing = {row["name"] for row in cursor.fetchall()}

            if "error_message" not in existing:
                cursor.execute("ALTER TABLE task_queue ADD COLUMN error_message TEXT")
                logger.info("[DB] migrated: added task_queue.error_message")
            if "last_attempt_at" not in existing:
                cursor.execute(
                    "ALTER TABLE task_queue ADD COLUMN last_attempt_at DATETIME"
                )
                logger.info("[DB] migrated: added task_queue.last_attempt_at")
            conn.commit()

    def _migrate_v2_0(self):
        """
        v2.0 schema migration：为 task_queue / final_results 增加 source_type
        字段，并回填老库里已有的 arxiv URL 的正确类型。
        幂等：每次启动安全调用。

        回填规则：
          - URL 含 'arxiv.org'  -> 'arxiv'
          - 其余                -> 保持默认 'bilibili'（v1.x 时期都是 B 站）
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # 1) task_queue.source_type
            cursor.execute("PRAGMA table_info(task_queue)")
            tq_cols = {row["name"] for row in cursor.fetchall()}
            if "source_type" not in tq_cols:
                cursor.execute(
                    "ALTER TABLE task_queue ADD COLUMN source_type TEXT DEFAULT 'bilibili'"
                )
                logger.info("[DB] migrated: added task_queue.source_type")
                # 回填：老库里已有的 arxiv 任务
                cursor.execute(
                    "UPDATE task_queue SET source_type = 'arxiv' "
                    "WHERE url LIKE '%arxiv.org%'"
                )
                logger.info(
                    f"[DB] migrated: backfilled {cursor.rowcount} task_queue "
                    f"rows to source_type='arxiv'"
                )

            # 2) final_results.source_type
            cursor.execute("PRAGMA table_info(final_results)")
            fr_cols = {row["name"] for row in cursor.fetchall()}
            if "source_type" not in fr_cols:
                cursor.execute(
                    "ALTER TABLE final_results ADD COLUMN source_type TEXT DEFAULT 'bilibili'"
                )
                logger.info("[DB] migrated: added final_results.source_type")
                cursor.execute(
                    "UPDATE final_results SET source_type = 'arxiv' "
                    "WHERE url LIKE '%arxiv.org%'"
                )
                logger.info(
                    f"[DB] migrated: backfilled {cursor.rowcount} final_results "
                    f"rows to source_type='arxiv'"
                )

            conn.commit()

    # --- 业务方法 ---

    def add_new_urls(self, urls, source_type="bilibili"):
        """
        将新发现的 URL 加入任务队列。
        Args:
            urls: URL 列表。
            source_type: 这批 URL 的来源类型（bilibili / arxiv / ...）。
        """
        added_count = 0
        now = datetime.now().isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            for url in urls:
                try:
                    # 记录到历史表
                    cursor.execute(
                        "INSERT OR IGNORE INTO urls_history (url, first_seen_at, last_seen_at) VALUES (?, ?, ?)",
                        (url, now, now)
                    )
                    # 将未处理的 URL 加入队列（带来源类型）
                    cursor.execute(
                        "INSERT OR IGNORE INTO task_queue (url, status, source_type, created_at) "
                        "VALUES (?, 'PENDING', ?, ?)",
                        (url, source_type, now)
                    )
                    if cursor.rowcount > 0:
                        added_count += 1
                except Exception as e:
                    logger.error(f"[DB] Error adding URL {url}: {e}")
            conn.commit()
        return added_count

    def get_task_source_type(self, url):
        """查询某个任务的来源类型，找不到时返回 None。"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT source_type FROM task_queue WHERE url = ?", (url,)
            )
            row = cursor.fetchone()
            return row["source_type"] if row else None

    def get_pending_tasks(self, limit=10):
        """获取待采集的任务"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT url FROM task_queue WHERE status = 'PENDING' LIMIT ?", (limit,))
            return [row['url'] for row in cursor.fetchall()]

    def update_task_status(self, url, status):
        """更新任务状态 (例如 PENDING -> PROCESSING -> COLLECTED)"""
        with self._get_connection() as conn:
            conn.execute("UPDATE task_queue SET status = ? WHERE url = ?", (status, url))
            conn.commit()

    def save_raw_content(self, url, text):
        """保存采集到的 Markdown 内容"""
        now = datetime.now().isoformat()
        with self._get_connection() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO raw_contents (url, markdown_text, collected_at) VALUES (?, ?, ?)",
                (url, text, now)
            )
            conn.execute("UPDATE task_queue SET status = 'COLLECTED' WHERE url = ?", (url,))
            conn.commit()

    def save_final_result(self, url, json_data, source_type="bilibili"):
        """保存 LLM 处理后的结果（带来源类型）"""
        now = datetime.now().isoformat()
        with self._get_connection() as conn:
            conn.execute(
                "INSERT INTO final_results (url, source_type, structured_json, processed_at) "
                "VALUES (?, ?, ?, ?)",
                (url, source_type, json_data, now)
            )
            conn.execute("UPDATE task_queue SET status = 'COMPLETED' WHERE url = ?", (url,))
            conn.commit()

    # ------------------------------------------------------------------
    # v1.1 失败重试相关方法
    # ------------------------------------------------------------------
    def mark_failed(self, url, error_message=None):
        """
        把一个任务标记为 FAILED：
        - status -> 'FAILED'
        - retry_count += 1
        - error_message 写入（截断到 500 字以防日志爆炸）
        - last_attempt_at = now
        """
        if error_message:
            error_message = str(error_message)[:500]
        now = datetime.now().isoformat()
        with self._get_connection() as conn:
            conn.execute(
                """
                UPDATE task_queue
                SET status = 'FAILED',
                    retry_count = COALESCE(retry_count, 0) + 1,
                    error_message = ?,
                    last_attempt_at = ?
                WHERE url = ?
                """,
                (error_message, now, url),
            )
            conn.commit()
        logger.warning(f"[DB] mark_failed: {url} | reason: {error_message}")

    def requeue_failed(self, max_retry=None):
        """
        把可重试的 FAILED 任务回滚到合适的状态：
          - 已有 raw_contents（采集成功但 LLM 失败）→ 回到 COLLECTED，跳过重抓
          - 没有 raw_contents（采集就失败了）       → 回到 PENDING，从头重试
        retry_count >= max_retry 的任务保留 FAILED，不再重试。

        返回 dict: {'to_collected': N, 'to_pending': M, 'kept_failed': K}
        """
        if max_retry is None:
            max_retry = self.DEFAULT_MAX_RETRY

        with self._get_connection() as conn:
            cursor = conn.cursor()

            # 1) 有 raw_contents 的失败任务 -> 直接回 COLLECTED
            cursor.execute(
                """
                UPDATE task_queue
                SET status = 'COLLECTED'
                WHERE status = 'FAILED'
                  AND COALESCE(retry_count, 0) < ?
                  AND url IN (SELECT url FROM raw_contents)
                """,
                (max_retry,),
            )
            to_collected = cursor.rowcount

            # 2) 没 raw_contents 的失败任务 -> 回 PENDING
            cursor.execute(
                """
                UPDATE task_queue
                SET status = 'PENDING'
                WHERE status = 'FAILED'
                  AND COALESCE(retry_count, 0) < ?
                """,
                (max_retry,),
            )
            to_pending = cursor.rowcount

            # 3) 保留下来的 FAILED（已经超过 max_retry）
            cursor.execute(
                "SELECT COUNT(*) FROM task_queue WHERE status = 'FAILED'"
            )
            kept_failed = cursor.fetchone()[0]

            conn.commit()

        if to_collected or to_pending:
            logger.info(
                f"[DB] requeue_failed: {to_collected} -> COLLECTED, "
                f"{to_pending} -> PENDING, {kept_failed} kept FAILED "
                f"(max_retry={max_retry})"
            )
        return {
            "to_collected": to_collected,
            "to_pending": to_pending,
            "kept_failed": kept_failed,
        }

    def get_run_summary(self):
        """v1.1: 返回当前数据库的状态摘要，给 main.py 做运行后报告。"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT status, COUNT(*) FROM task_queue GROUP BY status"
            )
            by_status = {row[0]: row[1] for row in cursor.fetchall()}

            cursor.execute("SELECT COUNT(*) FROM final_results")
            total_results = cursor.fetchone()[0]

        return {
            "by_status": by_status,
            "total_final_results": total_results,
        }
