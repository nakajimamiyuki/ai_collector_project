import os
import json
import logging
from datetime import datetime
from pathlib import Path

from openai import OpenAI
from dotenv import load_dotenv

# 加载 .env 配置
load_dotenv()

logger = logging.getLogger(__name__)


class LLMProcessor:
    # 类常量：方便后续微调，不必改代码逻辑
    MAX_TOKENS = 4000               # v1.1: 从 2000 提到 4000，避免长 JSON 截断
    INPUT_CHAR_LIMIT = 8000         # v1.1: 输入上下文从 6000 提到 8000
    TEMPERATURE = 0.2
    LLM_TIMEOUT_SEC = 90            # v1.1: 单次 LLM 请求超时（防止偶发 latency 卡死流水线）
    FAILURE_LOG_DIR = Path("logs/llm_failures")  # 解析失败的原始输出落盘位置

    def __init__(self):
        api_key = os.getenv("LLM_API_KEY")
        base_url = os.getenv("LLM_API_BASE")
        self.model = os.getenv("LLM_MODEL")

        if not all([api_key, base_url, self.model]):
            raise ValueError(
                "Missing LLM credentials in .env file. "
                "Please check LLM_API_KEY, LLM_API_BASE, and LLM_MODEL."
            )

        # 初始化 OpenAI 兼容客户端 (火山引擎 Coding Plan)
        self.client = OpenAI(
            api_key=api_key,
            base_url=base_url,
        )

        # 确保失败日志目录存在
        self.FAILURE_LOG_DIR.mkdir(parents=True, exist_ok=True)

    def _build_prompt(self, markdown_text, source_type="bilibili"):
        """按信息源类型构建结构化提取 Prompt。"""
        if source_type == "arxiv":
            return self._build_arxiv_prompt(markdown_text)
        return self._build_bilibili_prompt(markdown_text)

    def _build_bilibili_prompt(self, markdown_text):
        """B 站视频结构化提取 Prompt（v1.1 原样保留）。"""
        return f"""你是一个专业的数据分析师。请从以下 B 站视频页面的 Markdown 文本中精准提取关键信息，并以严格的 JSON 格式返回。

要求字段：
- title: 视频标题（去除播放量、弹幕等无关信息）
- up_name: UP 主名称
- publish_time: 发布时间（格式: YYYY-MM-DD HH:MM:SS，如未找到则填 null）
- play_count: 播放量（保留原始字符串，例如 "9977.2万"）
- danmaku_count: 弹幕数量（保留原始字符串）
- tags: 视频标签 (字符串数组)
- summary: 视频核心内容总结 (50-150 字以内，基于上下文推断)
- key_points: 视频可能讨论的核心要点 (字符串数组，3-5 个)

特别注意：
1. 必须返回纯 JSON 对象，禁止包含 ```json 代码块标记或其他解释文字、前缀、后缀。
2. 如果某字段在原文中找不到，请填 null（数组字段填 []）。
3. 字符串内的双引号必须用 \\" 转义，不要输出未转义的换行。
4. summary 字段需要你基于标题、标签、UP主等线索进行合理推断，请控制长度，避免输出被截断。
5. key_points 控制在 3-5 条，每条不超过 30 字。

待分析文本：
---
{markdown_text[:self.INPUT_CHAR_LIMIT]}
---

请直接输出 JSON："""

    def _build_arxiv_prompt(self, markdown_text):
        """arXiv 论文结构化提取 Prompt（v2.0 新增）。"""
        return f"""你是一个专业的 AI 论文分析师。请从以下 arXiv 论文页面的 Markdown 文本（含标题、作者、分类、摘要）中提取关键信息，并以严格的 JSON 格式返回。

要求字段（注意：与视频不同，论文统一用以下字段）：
- title: 论文标题
- up_name: 论文第一作者或作者团队（用作者字段填充；若无则 null）
- publish_time: 发布时间（arXiv 页通常无精确时间，填 null 即可）
- play_count: 固定填 null（论文无此概念）
- danmaku_count: 固定填 null（论文无此概念）
- tags: 论文学科分类标签（如 "cs.AI"、"cs.CL"，字符串数组；从"分类"行提取）
- summary: 用中文概括论文核心贡献 (50-150 字，基于摘要)
- key_points: 论文的核心要点/方法/结论 (字符串数组，3-5 个，用中文)

特别注意：
1. 必须返回纯 JSON 对象，禁止包含 ```json 代码块标记或其他解释文字、前缀、后缀。
2. summary 和 key_points 必须用中文输出，即使原文是英文。
3. 字符串内的双引号必须用 \\" 转义，不要输出未转义的换行。
4. 找不到的字段填 null（数组字段填 []）。
5. key_points 控制在 3-5 条，每条不超过 30 字。

待分析文本：
---
{markdown_text[:self.INPUT_CHAR_LIMIT]}
---

请直接输出 JSON："""

    @staticmethod
    def _safe_json_parse(raw_output):
        """
        健壮的 JSON 解析。
        策略：
          1. 先去掉 ```json ... ``` 等代码块包裹
          2. 直接 json.loads
          3. 失败时截取第一个 '{' 到最后一个 '}' 再 loads
        返回 (parsed_dict_or_None, error_message_or_None)
        """
        if not raw_output:
            return None, "empty output"

        text = raw_output.strip()

        # 去除代码块包裹（更稳健的实现）
        if text.startswith("```"):
            # 去掉首行 ``` 或 ```json
            lines = text.splitlines()
            if lines:
                lines = lines[1:]
            # 去掉末尾 ```
            if lines and lines[-1].strip().startswith("```"):
                lines = lines[:-1]
            text = "\n".join(lines).strip()

        # 第一次尝试：直接解析
        try:
            return json.loads(text), None
        except json.JSONDecodeError as e:
            first_err = str(e)

        # 第二次尝试：截取最外层大括号
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            candidate = text[start:end + 1]
            try:
                return json.loads(candidate), None
            except json.JSONDecodeError as e:
                return None, f"first_pass: {first_err} | bracket_pass: {e}"

        return None, f"first_pass: {first_err} | no balanced braces found"

    def _dump_failure(self, raw_output, error_message):
        """把解析失败的原始输出落盘，方便复盘"""
        try:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            path = self.FAILURE_LOG_DIR / f"llm_fail_{ts}.txt"
            path.write_text(
                f"# LLM JSON parse failure\n"
                f"# time: {datetime.now().isoformat()}\n"
                f"# model: {self.model}\n"
                f"# error: {error_message}\n"
                f"# ---raw output below---\n\n"
                f"{raw_output}",
                encoding="utf-8",
            )
            logger.warning(f"[Processor] Raw failed output saved to: {path}")
        except Exception as e:
            logger.error(f"[Processor] Failed to dump failure log: {e}")

    def clean_data(self, markdown_text, url=None, source_type=None):
        """
        调用 LLM 将 Markdown 转化为结构化 JSON 字符串。
        成功 → 返回 JSON 字符串
        失败 → 返回 None（不抛异常，调用方继续走状态机）

        Args:
            markdown_text: 待提取的 Markdown 文本。
            url: 可选，内容来源 URL。当 source_type 未显式给出时用于兜底推断。
            source_type: 可选，显式来源类型（bilibili / arxiv）。优先级高于 url 推断。
        """
        if not markdown_text or len(markdown_text) < 20:
            logger.warning("[Processor] Markdown text too short, skipping LLM.")
            return None

        # 优先用显式 source_type；否则按 URL 兜底推断
        if source_type is None:
            source_type = "bilibili"
            if url and "arxiv.org" in url:
                source_type = "arxiv"

        prompt = self._build_prompt(markdown_text, source_type=source_type)

        try:
            logger.info(f"[Processor] Calling LLM ({self.model}) ...")
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "你是一个数据提取助手，只返回严格 JSON 对象，不包含任何解释文字或代码块标记。"},
                    {"role": "user", "content": prompt},
                ],
                temperature=self.TEMPERATURE,
                max_tokens=self.MAX_TOKENS,
                timeout=self.LLM_TIMEOUT_SEC,  # v1.1: 防止偶发长尾卡死整个流水线
            )
        except Exception as e:
            logger.error(f"[Processor] LLM API call failed: {e}")
            return None

        raw_output = (response.choices[0].message.content or "").strip()
        if not raw_output:
            logger.warning("[Processor] LLM returned empty content.")
            return None

        # 检查 finish_reason，length 表示被截断
        finish_reason = getattr(response.choices[0], "finish_reason", None)
        if finish_reason == "length":
            logger.warning(
                f"[Processor] LLM output hit max_tokens limit (={self.MAX_TOKENS}). "
                f"Output may be truncated."
            )

        parsed, err = self._safe_json_parse(raw_output)
        if parsed is None:
            logger.warning(f"[Processor] JSON parse failed: {err}")
            self._dump_failure(raw_output, err)
            return None

        logger.info(
            f"[Processor] LLM extracted OK. Title: {parsed.get('title', 'N/A')}"
        )
        return json.dumps(parsed, ensure_ascii=False, indent=2)
