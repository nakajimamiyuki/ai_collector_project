"""
DBManager 单元测试 —— 状态机、schema 迁移、失败重试。

这些是项目最核心的本地逻辑，无任何外部依赖，可完全离线跑。
覆盖：建表、source_type 字段、add_new_urls 去重、状态流转、
mark_failed 重试计数、requeue_failed 智能回滚、迁移幂等性。
"""
import sqlite3
import pytest

from src.db_manager import DBManager


pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# 建表 / schema
# ---------------------------------------------------------------------------
def test_init_creates_all_tables(temp_db):
    """初始化应建出 4 张表。"""
    conn = sqlite3.connect(temp_db.db_path)
    names = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    conn.close()
    assert {"urls_history", "task_queue", "raw_contents", "final_results"} <= names


def test_task_queue_has_source_type_column(temp_db):
    """v2.0：task_queue 必须有 source_type 字段。"""
    conn = sqlite3.connect(temp_db.db_path)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(task_queue)").fetchall()}
    conn.close()
    assert "source_type" in cols
    assert "retry_count" in cols      # v1.1 字段也在
    assert "error_message" in cols


# ---------------------------------------------------------------------------
# add_new_urls
# ---------------------------------------------------------------------------
def test_add_new_urls_basic(temp_db):
    added = temp_db.add_new_urls(["https://x.com/1", "https://x.com/2"])
    assert added == 2


def test_add_new_urls_dedup(temp_db):
    """重复 URL 不应被重复加入（幂等）。"""
    temp_db.add_new_urls(["https://x.com/1"])
    added_again = temp_db.add_new_urls(["https://x.com/1", "https://x.com/2"])
    assert added_again == 1   # 只有 /2 是新的


def test_add_new_urls_records_source_type(temp_db):
    """source_type 应被正确写入并可查询。"""
    temp_db.add_new_urls(["https://arxiv.org/abs/2606.1"], source_type="arxiv")
    assert temp_db.get_task_source_type("https://arxiv.org/abs/2606.1") == "arxiv"


def test_add_new_urls_default_source_type(temp_db):
    """不传 source_type 时默认 bilibili。"""
    temp_db.add_new_urls(["https://bilibili.com/v/1"])
    assert temp_db.get_task_source_type("https://bilibili.com/v/1") == "bilibili"


# ---------------------------------------------------------------------------
# 状态流转
# ---------------------------------------------------------------------------
def test_status_flow_pending_to_completed(temp_db):
    """PENDING -> COLLECTED(存原文) -> COMPLETED(存结果) 的完整流转。"""
    url = "https://x.com/1"
    temp_db.add_new_urls([url])

    # save_raw_content 内部应把状态推到 COLLECTED
    temp_db.save_raw_content(url, "# some markdown content")
    assert _status_of(temp_db, url) == "COLLECTED"

    # save_final_result 内部应把状态推到 COMPLETED
    temp_db.save_final_result(url, '{"title": "x"}', source_type="bilibili")
    assert _status_of(temp_db, url) == "COMPLETED"


# ---------------------------------------------------------------------------
# 失败重试机制
# ---------------------------------------------------------------------------
def test_mark_failed_increments_retry(temp_db):
    """mark_failed 应置 FAILED 并累加 retry_count。"""
    url = "https://x.com/1"
    temp_db.add_new_urls([url])
    temp_db.mark_failed(url, "boom")
    assert _status_of(temp_db, url) == "FAILED"
    assert _retry_count(temp_db, url) == 1
    temp_db.mark_failed(url, "boom again")
    assert _retry_count(temp_db, url) == 2


def test_mark_failed_truncates_long_error(temp_db):
    """超长 error_message 应被截断到 500 字，防日志爆炸。"""
    url = "https://x.com/1"
    temp_db.add_new_urls([url])
    temp_db.mark_failed(url, "E" * 1000)
    conn = sqlite3.connect(temp_db.db_path)
    msg = conn.execute(
        "SELECT error_message FROM task_queue WHERE url=?", (url,)
    ).fetchone()[0]
    conn.close()
    assert len(msg) == 500


def test_requeue_failed_no_rawcontent_goes_pending(temp_db):
    """采集就失败（无 raw_contents）的任务应回 PENDING 从头重试。"""
    url = "https://x.com/1"
    temp_db.add_new_urls([url])
    temp_db.mark_failed(url, "collector died")
    result = temp_db.requeue_failed()
    assert result["to_pending"] == 1
    assert result["to_collected"] == 0
    assert _status_of(temp_db, url) == "PENDING"


def test_requeue_failed_with_rawcontent_goes_collected(temp_db):
    """已采集成功但 LLM 失败的任务应回 COLLECTED，跳过重抓。"""
    url = "https://x.com/1"
    temp_db.add_new_urls([url])
    temp_db.save_raw_content(url, "# content")   # 现在有 raw_contents 了
    temp_db.mark_failed(url, "llm json invalid")
    result = temp_db.requeue_failed()
    assert result["to_collected"] == 1
    assert _status_of(temp_db, url) == "COLLECTED"


def test_requeue_failed_respects_max_retry(temp_db):
    """retry_count 达到 max_retry 的任务应保留 FAILED，不再重试。"""
    url = "https://x.com/1"
    temp_db.add_new_urls([url])
    # 失败 3 次（DEFAULT_MAX_RETRY=3）
    for _ in range(3):
        temp_db.mark_failed(url, "fail")
    result = temp_db.requeue_failed(max_retry=3)
    assert result["kept_failed"] == 1
    assert _status_of(temp_db, url) == "FAILED"   # 仍是 FAILED


# ---------------------------------------------------------------------------
# 迁移幂等性
# ---------------------------------------------------------------------------
def test_migration_idempotent(temp_db):
    """对同一个 db 再次初始化（触发迁移）不应报错或破坏数据。"""
    temp_db.add_new_urls(["https://arxiv.org/abs/1"], source_type="arxiv")
    # 二次初始化同一路径 —— 迁移应安全跳过
    db2 = DBManager(db_path=temp_db.db_path)
    assert db2.get_task_source_type("https://arxiv.org/abs/1") == "arxiv"


def test_run_summary_shape(temp_db):
    """get_run_summary 返回结构正确。"""
    temp_db.add_new_urls(["https://x.com/1", "https://x.com/2"])
    summary = temp_db.get_run_summary()
    assert "by_status" in summary
    assert "total_final_results" in summary
    assert summary["by_status"].get("PENDING") == 2


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------
def _status_of(db, url):
    conn = sqlite3.connect(db.db_path)
    row = conn.execute("SELECT status FROM task_queue WHERE url=?", (url,)).fetchone()
    conn.close()
    return row[0] if row else None


def _retry_count(db, url):
    conn = sqlite3.connect(db.db_path)
    row = conn.execute("SELECT retry_count FROM task_queue WHERE url=?", (url,)).fetchone()
    conn.close()
    return row[0] if row else None
