"""
OllamaEmbedder 单元测试 —— mock HTTP 调用，不碰真实 ollama。

为什么 mock：CI 里没有 ollama 服务；本地跑测试也不该依赖 ollama 在跑。
真实集成验证留给 scripts/index_final_results.py 第一次跑时自然触发。
"""
from unittest.mock import patch, MagicMock
import pytest

from src.rag.embedder import OllamaEmbedder, EMBED_DIM


pytestmark = pytest.mark.unit


def _ok_response(vec=None):
    """构造一个 200 + 合法 embedding 的假响应。"""
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"embedding": vec or [0.1] * EMBED_DIM}
    return resp


# ---------------------------------------------------------------------------
# 基本属性
# ---------------------------------------------------------------------------
def test_embedder_exposes_dim():
    """dim 必须等于 bge-m3 的 1024，是建表时引用的硬契约。"""
    assert OllamaEmbedder().dim == 1024
    assert EMBED_DIM == 1024


# ---------------------------------------------------------------------------
# embed_one 正常路径
# ---------------------------------------------------------------------------
def test_embed_one_returns_vector():
    e = OllamaEmbedder()
    with patch("src.rag.embedder.requests.post", return_value=_ok_response()):
        vec = e.embed_one("hello world")
    assert len(vec) == EMBED_DIM
    assert all(isinstance(x, float) for x in vec[:5])


def test_embed_one_sends_model_and_prompt():
    """请求体里必须带 model + prompt，否则 ollama 不知道用哪个模型。"""
    e = OllamaEmbedder(model="bge-m3:latest")
    with patch("src.rag.embedder.requests.post", return_value=_ok_response()) as mock_post:
        e.embed_one("某段中文")
    payload = mock_post.call_args.kwargs["json"]
    assert payload["model"] == "bge-m3:latest"
    assert payload["prompt"] == "某段中文"


# ---------------------------------------------------------------------------
# embed_one 错误路径（全部应抛清晰异常，不能默默返回脏数据）
# ---------------------------------------------------------------------------
def test_embed_one_rejects_empty_text():
    """空字符串/纯空白应在调用前就拦下，避免浪费 ollama 一次推理。"""
    e = OllamaEmbedder()
    with pytest.raises(ValueError, match="empty"):
        e.embed_one("")
    with pytest.raises(ValueError, match="empty"):
        e.embed_one("   \n\t  ")


def test_embed_one_raises_on_http_error():
    """ollama 返回非 200 时应抛 RuntimeError，不能默默返回 None。"""
    e = OllamaEmbedder()
    bad_resp = MagicMock(status_code=500, text="internal error")
    with patch("src.rag.embedder.requests.post", return_value=bad_resp):
        with pytest.raises(RuntimeError, match="HTTP 500"):
            e.embed_one("x")


def test_embed_one_raises_on_unreachable_ollama():
    """ollama 没起来时应抛 RuntimeError，错误消息要点明 ollama 不可达。"""
    import requests as req
    e = OllamaEmbedder()
    with patch("src.rag.embedder.requests.post",
               side_effect=req.RequestException("connection refused")):
        with pytest.raises(RuntimeError, match="ollama unreachable"):
            e.embed_one("x")


def test_embed_one_raises_on_wrong_dim():
    """
    如果 ollama 不知怎么返回了错误维度（比如模型名拼错跑到了别的模型），
    必须早早拦下，否则下游建表 / 检索会出莫名其妙的错。
    """
    e = OllamaEmbedder()
    wrong_dim_resp = _ok_response(vec=[0.1] * 512)   # 不是 1024
    with patch("src.rag.embedder.requests.post", return_value=wrong_dim_resp):
        with pytest.raises(RuntimeError, match="unexpected embedding dim"):
            e.embed_one("x")


# ---------------------------------------------------------------------------
# embed_many：批量场景的"尽力而为"语义
# ---------------------------------------------------------------------------
def test_embed_many_skips_failed_items_with_zero_vec():
    """
    批量索引时，单条失败不应中断整个 batch —— 失败用零向量占位 + 日志报警，
    保证已 embed 成功的部分能正常入库。
    """
    e = OllamaEmbedder()
    good = _ok_response()
    bad = MagicMock(status_code=500, text="boom")
    # 三条：成功 / 失败 / 成功
    with patch("src.rag.embedder.requests.post", side_effect=[good, bad, good]):
        out = e.embed_many(["a", "b", "c"])
    assert len(out) == 3
    assert out[0][0] != 0.0           # 第一条是真向量
    assert out[1] == [0.0] * EMBED_DIM  # 第二条是零向量占位
    assert out[2][0] != 0.0           # 第三条正常恢复
