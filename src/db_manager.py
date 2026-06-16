import sqlite3
import os
from datetime import datetime

class DBManager:
    def __init__(self, db_path="data/collector.db"):
        self.db_path = db_path
        # 确保 data 文件夹存在
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()

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
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS task_queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT UNIQUE,
                    status TEXT DEFAULT 'PENDING', -- PENDING, PROCESSING, COLLECTED, COMPLETED, FAILED
                    retry_count INTEGER DEFAULT 0,
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
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS final_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT,
                    structured_json TEXT,
                    processed_at DATETIME,
                    FOREIGN KEY (url) REFERENCES task_queue (url)
                )
            ''')
            conn.commit()

    # --- 业务方法 ---

    def add_new_urls(self, urls):
        """将新发现的 URL 加入任务队列"""
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
                    # 将未处理的 URL 加入队列
                    cursor.execute(
                        "INSERT OR IGNORE INTO task_queue (url, status, created_at) VALUES (?, 'PENDING', ?)",
                        (url, now)
                    )
                    if cursor.rowcount > 0:
                        added_count += 1
                except Exception as e:
                    print(f"Error adding URL {url}: {e}")
            conn.commit()
        return added_count

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

    def save_final_result(self, url, json_data):
        """保存 LLM 处理后的结果"""
        now = datetime.now().isoformat()
        with self._get_connection() as conn:
            conn.execute(
                "INSERT INTO final_results (url, structured_json, processed_at) VALUES (?, ?, ?)",
                (url, json_data, now)
            )
            conn.execute("UPDATE task_queue SET status = 'COMPLETED' WHERE url = ?", (url,))
            conn.commit()
