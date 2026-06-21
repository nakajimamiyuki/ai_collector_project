"""
BiliCollector 分派逻辑单元测试。

collect_content 按 source_type / URL 把任务分派到不同采集策略：
  - arxiv  -> _collect_arxiv（requests，同步）
  - 其它   -> _collect_bilibili（Playwright，异步）
这里只验证"分派对不对"，把两个具体采集方法 mock 掉，不真的抓网页。
"""
from unittest.mock import patch, AsyncMock, MagicMock
import pytest

from src.collector import BiliCollector


pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_dispatch_arxiv_by_explicit_source_type():
    """显式 source_type='arxiv' 应走 _collect_arxiv，不碰 Playwright。"""
    c = BiliCollector()
    url = "https://arxiv.org/abs/1"
    with patch.object(c, "_collect_arxiv", return_value="ARXIV_MD") as m_arxiv, \
         patch.object(c, "_collect_bilibili", new=AsyncMock()) as m_bili:
        await c.collect_content(url, source_type="arxiv")
    m_arxiv.assert_called_once_with(url)
    m_bili.assert_not_called()


@pytest.mark.asyncio
async def test_dispatch_bilibili_by_explicit_source_type():
    """显式 source_type='bilibili' 应走 _collect_bilibili。"""
    c = BiliCollector()
    url = "https://bilibili.com/v/1"
    with patch.object(c, "_collect_bilibili", new=AsyncMock(return_value="BILI_MD")) as m_bili, \
         patch.object(c, "_collect_arxiv") as m_arxiv:
        await c.collect_content(url, source_type="bilibili")
    m_bili.assert_called_once()
    assert m_bili.call_args.args[0] == url   # URL 被透传
    m_arxiv.assert_not_called()


@pytest.mark.asyncio
async def test_dispatch_infers_arxiv_from_url():
    """source_type=None 时，arxiv.org 的 URL 应被推断为 arxiv（兜底逻辑）。"""
    c = BiliCollector()
    url = "https://arxiv.org/abs/2606.1"
    with patch.object(c, "_collect_arxiv", return_value="ARXIV_MD") as m_arxiv, \
         patch.object(c, "_collect_bilibili", new=AsyncMock()) as m_bili:
        await c.collect_content(url)
    m_arxiv.assert_called_once_with(url)
    m_bili.assert_not_called()


@pytest.mark.asyncio
async def test_dispatch_infers_bilibili_from_url():
    """source_type=None 且非 arxiv 的 URL 默认走 bilibili。"""
    c = BiliCollector()
    url = "https://www.bilibili.com/video/BVxxxx"
    with patch.object(c, "_collect_bilibili", new=AsyncMock(return_value="BILI_MD")) as m_bili, \
         patch.object(c, "_collect_arxiv") as m_arxiv:
        await c.collect_content(url)
    m_bili.assert_called_once()
    assert m_bili.call_args.args[0] == url
    m_arxiv.assert_not_called()


def test_collect_arxiv_parses_static_html():
    """
    _collect_arxiv 用 requests 抓静态页 —— mock 掉 requests，喂入一段
    arxiv abstract 页 HTML，验证标题/摘要被抽出且去掉 'Title:'/'Abstract:' 前缀。
    """
    html = b"""
    <html><body>
      <h1 class="title">Title:How Transparent is DiffusionGemma?</h1>
      <div class="authors">Authors:Joshua Engels, Callum McDougall</div>
      <blockquote class="abstract">Abstract:We study reasoning transparency.</blockquote>
      <td class="subjects">Machine Learning (cs.LG)</td>
    </body></html>
    """
    resp = MagicMock()
    resp.status_code = 200
    resp.content = html

    c = BiliCollector()
    with patch("src.collector.requests.get", return_value=resp):
        md = c._collect_arxiv("https://arxiv.org/abs/2606.20560")

    assert md is not None
    assert "How Transparent is DiffusionGemma?" in md
    assert "We study reasoning transparency." in md
    # 前缀应被剥掉
    assert "Title:" not in md
    assert "Abstract:" not in md


def test_collect_arxiv_handles_http_error():
    """arxiv 页返回非 200 时应返回 None，不崩。"""
    resp = MagicMock()
    resp.status_code = 404
    resp.content = b""
    c = BiliCollector()
    with patch("src.collector.requests.get", return_value=resp):
        md = c._collect_arxiv("https://arxiv.org/abs/x")
    assert md is None
