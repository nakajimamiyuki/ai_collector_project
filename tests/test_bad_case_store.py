"""BadCaseStore 单元测试。

测试目标：
- 所有读写走临时文件，不碰 data/agent_runs.db
- 验证 record_run / mark / list / stats 的契约
- 特别覆盖：零结果自动 bad、status 合法性校验、按 status 过滤
"""
import pytest

from src.agent.bad_case_store import BadCaseStore, VALID_STATUSES

pytestmark = pytest.mark.unit


@pytest.fixture
def store(tmp_path):
    return BadCaseStore(db_path=tmp_path / "agent_runs.db")


# ----------------------------------------------------------------------
# record_run
# ----------------------------------------------------------------------
def test_record_run_returns_id_and_can_be_fetched(store):
    run_id = store.record_run(
        query="找杭州 MCP 岗位",
        result_count=5,
        elapsed_seconds=3.2,
        reflect_rounds=1,
        trace=["parse", "retrieve", "reflect", "summarize"],
        final_report="# Top 推荐\n- ...",
    )
    assert run_id > 0

    run = store.get(run_id)
    assert run is not None
    assert run.query == "找杭州 MCP 岗位"
    assert run.result_count == 5
    assert run.elapsed_seconds == pytest.approx(3.2)
    assert run.reflect_rounds == 1
    assert run.status == "unreviewed"
    assert "parse" in run.trace_json
    assert run.final_report.startswith("# Top 推荐")


def test_record_run_with_zero_results_auto_marks_bad(store):
    """v3.0 反思耗光仍然 0 结果 → 自动 bad，root_cause=zero_result。"""
    run_id = store.record_run(
        query="郑州 50K AGI 内核岗",
        result_count=0,
        elapsed_seconds=12.5,
        reflect_rounds=3,
    )
    run = store.get(run_id)
    assert run is not None
    assert run.status == "bad"
    assert run.root_cause == "zero_result"


def test_record_run_explicit_status_overrides_zero_auto(store):
    """如果上层（比如人工跑回归）已经断言 good，零结果也不要被反复打回 bad。"""
    run_id = store.record_run(
        query="测试空查询场景",
        result_count=0,
        elapsed_seconds=0.5,
        status="good",
    )
    run = store.get(run_id)
    assert run is not None
    assert run.status == "good"
    assert run.root_cause == ""


def test_record_run_rejects_invalid_status(store):
    with pytest.raises(ValueError, match="invalid status"):
        store.record_run(
            query="x",
            result_count=1,
            elapsed_seconds=0,
            status="nice",
        )


# ----------------------------------------------------------------------
# mark
# ----------------------------------------------------------------------
def test_mark_updates_status_and_root_cause(store):
    run_id = store.record_run(
        query="t", result_count=2, elapsed_seconds=1.0
    )
    ok = store.mark(
        run_id,
        status="bad",
        root_cause="filter_too_strict",
        fix_commit="abc1234",
        fix_notes="把 salary_min 从 20K 降到 15K",
    )
    assert ok is True

    run = store.get(run_id)
    assert run is not None
    assert run.status == "bad"
    assert run.root_cause == "filter_too_strict"
    assert run.fix_commit == "abc1234"
    assert run.fix_notes.startswith("把 salary_min")


def test_mark_partial_update_only_changes_given_fields(store):
    run_id = store.record_run(
        query="t", result_count=2, elapsed_seconds=1.0
    )
    store.mark(run_id, root_cause="rag_miss")
    # 只动 root_cause，status 保留 'unreviewed'
    run = store.get(run_id)
    assert run is not None
    assert run.status == "unreviewed"
    assert run.root_cause == "rag_miss"


def test_mark_on_missing_id_returns_false(store):
    assert store.mark(9999, status="good") is False


def test_mark_with_no_fields_returns_false(store):
    run_id = store.record_run(
        query="t", result_count=2, elapsed_seconds=1.0
    )
    assert store.mark(run_id) is False  # 全 None = 啥也没改


def test_mark_rejects_invalid_status(store):
    run_id = store.record_run(
        query="t", result_count=2, elapsed_seconds=1.0
    )
    with pytest.raises(ValueError, match="invalid status"):
        store.mark(run_id, status="awesome")


# ----------------------------------------------------------------------
# list / stats
# ----------------------------------------------------------------------
def test_list_returns_newest_first(store):
    a = store.record_run(query="A", result_count=1, elapsed_seconds=0)
    b = store.record_run(query="B", result_count=1, elapsed_seconds=0)
    c = store.record_run(query="C", result_count=1, elapsed_seconds=0)

    runs = store.list()
    # 同秒插入时按 id DESC，最后插入的 C 排第一
    assert [r.id for r in runs] == [c, b, a]


def test_list_filters_by_status(store):
    g = store.record_run(query="g", result_count=1, elapsed_seconds=0, status="good")
    b = store.record_run(query="b", result_count=0, elapsed_seconds=0)   # auto bad
    u = store.record_run(query="u", result_count=2, elapsed_seconds=0)   # unreviewed

    good = store.list(status="good")
    bad = store.list(status="bad")
    unr = store.list(status="unreviewed")

    assert [r.id for r in good] == [g]
    assert [r.id for r in bad] == [b]
    assert [r.id for r in unr] == [u]


def test_list_respects_limit(store):
    for i in range(5):
        store.record_run(query=f"q{i}", result_count=1, elapsed_seconds=0)
    assert len(store.list(limit=3)) == 3


def test_stats_counts_by_status(store):
    store.record_run(query="g1", result_count=1, elapsed_seconds=0, status="good")
    store.record_run(query="g2", result_count=1, elapsed_seconds=0, status="good")
    store.record_run(query="b1", result_count=0, elapsed_seconds=0)  # auto bad
    store.record_run(query="u1", result_count=1, elapsed_seconds=0)

    stats = store.stats()
    assert stats == {"unreviewed": 1, "good": 2, "bad": 1, "total": 4}


def test_empty_store_stats_zero(store):
    assert store.stats() == {"unreviewed": 0, "good": 0, "bad": 0, "total": 0}


def test_valid_statuses_constant():
    """sanity：常量没被改坏。"""
    assert VALID_STATUSES == {"unreviewed", "good", "bad"}
