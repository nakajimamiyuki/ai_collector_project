"""
VectorStore 单元测试 —— 用真实 Milvus Lite + 临时文件，不 mock。

为什么不 mock：Milvus Lite 是 pip 装好就能跑的进程内库（跟 SQLite 一样轻），
mock 反而失去对 schema / 索引 / 检索行为契约的真实验证。每个测试一个临时
db 文件，pytest tmp_path 自动清理。
"""
import pytest

from src.rag.embedder import EMBED_DIM
from src.rag.vector_store import VectorStore, SearchHit


pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def store(tmp_path):
    """每个测试一个全新的临时 Milvus Lite 文件。"""
    db_path = str(tmp_path / "test_vec.db")
    return VectorStore(db_path=db_path, collection="test_chunks")


def _fake_vec(seed: float = 0.1) -> list[float]:
    """构造一个 1024 维的假向量。不同 seed 产生不同向量，用于测检索排序。"""
    return [seed] * EMBED_DIM


# ---------------------------------------------------------------------------
# 建表 / 幂等
# ---------------------------------------------------------------------------
def test_init_creates_collection(store):
    """初始化应建好 collection。"""
    assert store.client.has_collection("test_chunks")


def test_init_is_idempotent(tmp_path):
    """对同一个 db 文件二次初始化不应报错（建表前 has_collection 已挡掉）。"""
    db_path = str(tmp_path / "twice.db")
    VectorStore(db_path=db_path, collection="x")
    # 第二次实例化同一路径 —— 不应抛
    s2 = VectorStore(db_path=db_path, collection="x")
    assert s2.client.has_collection("x")


# ---------------------------------------------------------------------------
# upsert：写入 + 维度校验 + url 去重
# ---------------------------------------------------------------------------
def test_upsert_rejects_wrong_dim(store):
    """传入维度不对的 embedding 应早早抛错，避免脏数据入库。"""
    with pytest.raises(ValueError, match="embedding dim mismatch"):
        store.upsert(
            url="https://x.com/1",
            source_type="bilibili",
            title="t",
            text="t",
            embedding=[0.1] * 512,   # 错误维度
        )


def test_upsert_then_search_finds_it(store):
    """写入一条后用同样向量搜应能命中自己。"""
    vec = _fake_vec(0.5)
    store.upsert(
        url="https://x.com/1",
        source_type="bilibili",
        title="测试视频",
        text="一段描述",
        embedding=vec,
    )
    hits = store.search(vec, top_k=5)
    assert len(hits) == 1
    assert hits[0].url == "https://x.com/1"
    assert hits[0].title == "测试视频"
    assert hits[0].source_type == "bilibili"
    assert hits[0].score > 0.99    # 同一向量 COSINE 应接近 1.0


def test_upsert_dedups_by_url(store):
    """同一 url 二次 upsert 应替换旧记录，不产生重复。"""
    store.upsert(
        url="https://x.com/1", source_type="bilibili",
        title="旧标题", text="旧文本", embedding=_fake_vec(0.1),
    )
    store.upsert(
        url="https://x.com/1", source_type="bilibili",
        title="新标题", text="新文本", embedding=_fake_vec(0.1),
    )
    hits = store.search(_fake_vec(0.1), top_k=10)
    assert len(hits) == 1                  # 只剩一条
    assert hits[0].title == "新标题"        # 是新版本


# ---------------------------------------------------------------------------
# search：排序 + top_k + 过滤
# ---------------------------------------------------------------------------
def test_search_ranks_by_similarity(store):
    """与 query 越接近的向量应排得越靠前（COSINE）。"""
    # 三条数据，向量与 query=[0.5] 的余弦相似度递减
    store.upsert(url="https://x/a", source_type="bilibili", title="A", text="a",
                 embedding=_fake_vec(0.5))     # 与 query 完全同向 -> 最相似
    store.upsert(url="https://x/b", source_type="bilibili", title="B", text="b",
                 embedding=_fake_vec(0.3))     # 同向但模长不同 -> COSINE 仍 ~1
    # 构造一个真正不同方向的向量（前半 +1，后半 -1）
    diff_vec = [1.0] * (EMBED_DIM // 2) + [-1.0] * (EMBED_DIM // 2)
    store.upsert(url="https://x/c", source_type="bilibili", title="C", text="c",
                 embedding=diff_vec)

    hits = store.search(_fake_vec(0.5), top_k=3)
    assert len(hits) == 3
    # C 应该排最后（方向不同），A/B 排前面
    assert hits[-1].url == "https://x/c"


def test_search_respects_top_k(store):
    """top_k=2 应只返回 2 条，即使库里有更多。"""
    for i in range(5):
        store.upsert(url=f"https://x/{i}", source_type="bilibili",
                     title=f"T{i}", text=f"t{i}", embedding=_fake_vec(0.1 + i*0.01))
    hits = store.search(_fake_vec(0.15), top_k=2)
    assert len(hits) == 2


def test_search_filters_by_source_type(store):
    """指定 source_type='arxiv' 应只返回 arxiv 的数据，过滤掉 bilibili。"""
    store.upsert(url="https://b/1", source_type="bilibili",
                 title="B 站视频", text="x", embedding=_fake_vec(0.5))
    store.upsert(url="https://a/1", source_type="arxiv",
                 title="arxiv 论文", text="x", embedding=_fake_vec(0.5))
    hits = store.search(_fake_vec(0.5), top_k=10, source_type="arxiv")
    assert len(hits) == 1
    assert hits[0].source_type == "arxiv"
    assert hits[0].url == "https://a/1"


def test_search_rejects_wrong_dim(store):
    """查询向量维度不对应抛错。"""
    with pytest.raises(ValueError, match="query embedding dim mismatch"):
        store.search([0.1] * 512, top_k=5)


def test_search_returns_searchhit_dataclass(store):
    """检索结果应为 SearchHit 实例，保证下游字段访问稳定。"""
    store.upsert(url="https://x/1", source_type="bilibili",
                 title="t", text="x", embedding=_fake_vec(0.5))
    hits = store.search(_fake_vec(0.5), top_k=1)
    assert isinstance(hits[0], SearchHit)
    assert hasattr(hits[0], "score")


# ---------------------------------------------------------------------------
# 空库行为
# ---------------------------------------------------------------------------
def test_search_on_empty_collection_returns_empty_list(store):
    """空库检索应返回空 list，不抛异常。"""
    hits = store.search(_fake_vec(0.5), top_k=5)
    assert hits == []
