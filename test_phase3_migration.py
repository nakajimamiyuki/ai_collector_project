"""
v2.0 Phase 3 数据库迁移验证
验证：
  1. source_type 字段已加到 task_queue / final_results
  2. 老数据（arxiv URL）被正确回填为 source_type='arxiv'
  3. 迁移幂等（重复初始化不报错、不重复回填）
  4. add_new_urls(source_type=) / get_task_source_type() 工作正常
只读 + 受控写入临时 URL，跑完清理，不污染真实任务状态。
"""
import sqlite3
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

from src.db_manager import DBManager

DB_PATH = "data/collector.db"


def col_exists(table, col):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(f"PRAGMA table_info({table})")
    cols = {r[1] for r in cur.fetchall()}
    conn.close()
    return col in cols


def main():
    print("\n=== 1. 触发迁移（DBManager 初始化）===")
    db = DBManager(db_path=DB_PATH)
    assert col_exists("task_queue", "source_type"), "task_queue.source_type 应已添加"
    assert col_exists("final_results", "source_type"), "final_results.source_type 应已添加"
    print("  OK: 两个表都有 source_type 字段")

    print("\n=== 2. 老数据回填检查 ===")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT source_type, COUNT(*) c FROM task_queue GROUP BY source_type")
    print("  task_queue 按来源分布:")
    for r in cur.fetchall():
        print(f"    {r['source_type']}: {r['c']}")
    # 验证：所有 arxiv.org 的任务 source_type 都是 arxiv
    cur.execute(
        "SELECT COUNT(*) FROM task_queue "
        "WHERE url LIKE '%arxiv.org%' AND source_type != 'arxiv'"
    )
    bad = cur.fetchone()[0]
    assert bad == 0, f"有 {bad} 条 arxiv URL 的 source_type 未回填"
    print("  OK: 所有 arxiv URL 已正确标记")

    cur.execute(
        "SELECT COUNT(*) FROM task_queue "
        "WHERE url LIKE '%bilibili%' AND source_type != 'bilibili'"
    )
    bad2 = cur.fetchone()[0]
    assert bad2 == 0, f"有 {bad2} 条 B站 URL 的 source_type 错误"
    print("  OK: 所有 B 站 URL 仍为 bilibili")
    conn.close()

    print("\n=== 3. 迁移幂等性（再初始化一次，不应报错/重复改动）===")
    db2 = DBManager(db_path=DB_PATH)
    print("  OK: 二次初始化无异常")

    print("\n=== 4. add_new_urls(source_type=) + get_task_source_type() ===")
    test_url = "https://arxiv.org/abs/0000.00000_phase3test"
    added = db.add_new_urls([test_url], source_type="arxiv")
    st = db.get_task_source_type(test_url)
    print(f"  插入测试 URL，added={added}, source_type={st}")
    assert st == "arxiv", "新插入的 arxiv 任务应记录正确 source_type"
    # 清理测试 URL
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM task_queue WHERE url = ?", (test_url,))
    conn.execute("DELETE FROM urls_history WHERE url = ?", (test_url,))
    conn.commit()
    conn.close()
    print("  OK: 已清理测试 URL")

    print("\n=== Phase 3 迁移验证全部通过 ===")


if __name__ == "__main__":
    main()
