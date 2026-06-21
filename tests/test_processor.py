"""
LLMProcessor 单元测试 —— JSON 解析健壮性 + source_type 选 prompt。

_safe_json_parse 是 @staticmethod，可直接测，无需实例化（实例化要 .env 凭证）。
覆盖：纯 JSON、```json 代码块包裹、前后有解释文字（截大括号）、
非法 JSON、空输入。再加 prompt 按 source_type 分流的验证。
"""
import json
from unittest.mock import patch, MagicMock
import pytest

from src.processor import LLMProcessor


pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# _safe_json_parse —— 核心健壮性逻辑
# ---------------------------------------------------------------------------
def test_parse_clean_json():
    parsed, err = LLMProcessor._safe_json_parse('{"title": "hi", "tags": []}')
    assert err is None
    assert parsed["title"] == "hi"


def test_parse_strips_json_code_fence():
    """LLM 常爱用 ```json ... ``` 包裹，应被剥掉。"""
    raw = '```json\n{"title": "x"}\n```'
    parsed, err = LLMProcessor._safe_json_parse(raw)
    assert err is None
    assert parsed["title"] == "x"


def test_parse_strips_bare_code_fence():
    """没有 json 标记的 ``` 包裹也应处理。"""
    raw = '```\n{"a": 1}\n```'
    parsed, err = LLMProcessor._safe_json_parse(raw)
    assert err is None
    assert parsed["a"] == 1


def test_parse_extracts_from_surrounding_text():
    """前后有解释文字时，应截取最外层大括号。"""
    raw = '好的，这是结果：{"title": "y", "n": 2} 希望对你有帮助'
    parsed, err = LLMProcessor._safe_json_parse(raw)
    assert err is None
    assert parsed["title"] == "y"
    assert parsed["n"] == 2


def test_parse_empty_returns_error():
    parsed, err = LLMProcessor._safe_json_parse("")
    assert parsed is None
    assert err is not None


def test_parse_invalid_returns_error():
    """彻底非法、没有大括号的内容应返回错误而非崩溃。"""
    parsed, err = LLMProcessor._safe_json_parse("this is not json at all")
    assert parsed is None
    assert err is not None


def test_parse_broken_json_returns_error():
    """有大括号但内容损坏，两次尝试都失败应返回错误。"""
    parsed, err = LLMProcessor._safe_json_parse('{"title": "x", broken')
    assert parsed is None
    assert err is not None


# ---------------------------------------------------------------------------
# prompt 按 source_type 分流 —— 测行为契约，不测字符串内容
#
# 旧版本断言 prompt 里包含 "B 站"/"up_name"/"论文" 等字符串，是 snapshot 测试：
# 改一下 prompt 措辞测试就红，但行为并没坏。改成测三条 invariant：
#   1. 不同 source_type 产出不同的 prompt（分流真的起作用）
#   2. 用户输入被透传到 prompt 里
#   3. 不传 source_type 时走 bilibili 默认分支（与显式 bilibili 等价）
# ---------------------------------------------------------------------------
def _make_processor_without_env():
    """
    绕开 __init__ 的凭证检查，构造一个只用来测 prompt 方法的实例。
    用 __new__ 跳过 __init__，再补上需要的类属性。
    """
    p = LLMProcessor.__new__(LLMProcessor)
    return p


def test_build_prompt_routes_by_source_type():
    """不同 source_type 应产生不同的 prompt（分流真的起作用）。"""
    p = _make_processor_without_env()
    bili_prompt = p._build_prompt("text", source_type="bilibili")
    arxiv_prompt = p._build_prompt("text", source_type="arxiv")
    assert bili_prompt != arxiv_prompt


def test_build_prompt_passes_through_user_input():
    """用户输入应被原样嵌入到 prompt 里，无论走哪条分支。"""
    p = _make_processor_without_env()
    sentinel = "USER_INPUT_SENTINEL_xy9z"
    assert sentinel in p._build_prompt(sentinel, source_type="bilibili")
    assert sentinel in p._build_prompt(sentinel, source_type="arxiv")


def test_build_prompt_defaults_to_bilibili():
    """不传 source_type 时应与显式 bilibili 走同一分支。"""
    p = _make_processor_without_env()
    assert p._build_prompt("text") == p._build_prompt("text", source_type="bilibili")
