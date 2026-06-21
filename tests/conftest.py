"""
pytest 共享 fixtures。

设计原则：每个测试拿到一个完全隔离的临时数据库，互不干扰、
不碰用户真实的 data/collector.db。测试结束自动清理。
"""
import sys
import os
import pytest

# 让 tests/ 能 import src.*（项目根加入 path）
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.db_manager import DBManager


@pytest.fixture
def temp_db(tmp_path):
    """
    每个测试一个全新的临时 DBManager，DB 文件在 pytest 的 tmp_path 下。
    测试结束后 tmp_path 由 pytest 自动清理。
    """
    db_path = str(tmp_path / "test_collector.db")
    return DBManager(db_path=db_path)


@pytest.fixture
def arxiv_atom_xml():
    """一段最小但真实的 arXiv Atom API 响应，用于测 ArxivSource 解析。"""
    return b"""<?xml version='1.0' encoding='UTF-8'?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2606.20560v1</id>
    <title>How Transparent is DiffusionGemma?</title>
    <summary>We study reasoning transparency in diffusion language models.</summary>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/2606.20554v2</id>
    <title>Another AI Paper</title>
    <summary>Some abstract text here.</summary>
  </entry>
</feed>"""
