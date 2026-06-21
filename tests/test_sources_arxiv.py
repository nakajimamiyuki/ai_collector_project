"""
ArxivSource 单元测试 —— mock arXiv API，验证解析与 URL 规范化。

关键：不碰真实网络。用 unittest.mock 拦截 requests.get，喂入受控的
Atom XML（见 conftest 的 arxiv_atom_xml fixture），只测我们自己的
解析逻辑：取 id、http->https、去版本号 v1/v2、跨分类去重。
"""
from unittest.mock import patch, MagicMock
import pytest

from src.sources.arxiv import ArxivSource
from src.sources.base import BaseSource


pytestmark = pytest.mark.unit


def _mock_response(content, status=200):
    resp = MagicMock()
    resp.status_code = status
    resp.content = content
    return resp


def test_arxiv_is_a_source():
    """ArxivSource 必须是 BaseSource 子类，且 source_type 正确。"""
    assert issubclass(ArxivSource, BaseSource)
    assert ArxivSource.source_type == "arxiv"


@pytest.mark.asyncio
async def test_fetch_parses_and_normalizes(arxiv_atom_xml):
    """
    给定一段 Atom XML，应解析出 abstract URL，并：
    - http:// 规范化为 https://
    - 去掉版本号 v1/v2
    """
    src = ArxivSource(categories=["cs.AI"], max_results=2)
    with patch("src.sources.arxiv.requests.get",
               return_value=_mock_response(arxiv_atom_xml)):
        urls = await src.fetch_new_urls()

    assert urls == [
        "https://arxiv.org/abs/2606.20560",   # 原 http + v1 -> 规范化
        "https://arxiv.org/abs/2606.20554",   # 原 v2 -> 去版本号
    ]


@pytest.mark.asyncio
async def test_fetch_dedups_across_categories(arxiv_atom_xml):
    """同一篇论文出现在多个分类时应跨分类去重。"""
    src = ArxivSource(categories=["cs.AI", "cs.LG"], max_results=2)
    # 两个分类都返回同样的 XML -> 应去重，不翻倍
    with patch("src.sources.arxiv.requests.get",
               return_value=_mock_response(arxiv_atom_xml)):
        urls = await src.fetch_new_urls()
    assert len(urls) == 2          # 不是 4
    assert len(set(urls)) == len(urls)


@pytest.mark.asyncio
async def test_fetch_handles_http_error():
    """API 返回非 200 时应返回空列表，不抛异常（容错降级）。"""
    src = ArxivSource(categories=["cs.AI"])
    with patch("src.sources.arxiv.requests.get",
               return_value=_mock_response(b"", status=503)):
        urls = await src.fetch_new_urls()
    assert urls == []


@pytest.mark.asyncio
async def test_fetch_handles_network_exception():
    """requests 抛异常时应返回空列表，不让整个流水线崩。"""
    import requests
    src = ArxivSource(categories=["cs.AI"])
    with patch("src.sources.arxiv.requests.get",
               side_effect=requests.RequestException("network down")):
        urls = await src.fetch_new_urls()
    assert urls == []


@pytest.mark.asyncio
async def test_fetch_handles_malformed_xml():
    """返回非法 XML 时应返回空列表，不抛 ParseError。"""
    src = ArxivSource(categories=["cs.AI"])
    with patch("src.sources.arxiv.requests.get",
               return_value=_mock_response(b"<not valid xml")):
        urls = await src.fetch_new_urls()
    assert urls == []
