"""
基于本地 Ollama bge-m3 的 Embedding 封装。

为什么用 ollama 而不是 sentence-transformers / HuggingFace 直装：
1. 模型已经在本地（用户 ollama 已 pull），零额外下载
2. ollama 进程统一管理模型生命周期，省去显存/内存调度
3. HTTP 接口跨语言/跨进程通用，未来切到别的客户端不用改

为什么用 bge-m3：
- 1024 维，中文 SOTA embedding 之一（BAAI 智源出品）
- 支持中英混合，对 AI/技术领域的术语理解好
"""
from __future__ import annotations

import logging
from typing import Iterable

import requests

logger = logging.getLogger(__name__)


DEFAULT_OLLAMA_URL = "http://localhost:11434"
DEFAULT_MODEL = "bge-m3:latest"
EMBED_DIM = 1024            # bge-m3 固定输出维度
DEFAULT_TIMEOUT = 30        # 单次调用超时（秒）


class OllamaEmbedder:
    """对 Ollama HTTP /api/embeddings 的最小封装。"""

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        base_url: str = DEFAULT_OLLAMA_URL,
        timeout: int = DEFAULT_TIMEOUT,
    ):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    @property
    def dim(self) -> int:
        """向量维度（固定值，便于建表时引用，避免硬编码扩散）。"""
        return EMBED_DIM

    def embed_one(self, text: str) -> list[float]:
        """
        对单段文本生成 embedding。

        失败时抛 RuntimeError —— 调用方应在批量场景里自己捕获并跳过单条，
        而不是吞掉错误，避免后面索引出现"看似成功但向量是垃圾"的脏数据。
        """
        if not text or not text.strip():
            raise ValueError("embed_one: text is empty")

        try:
            resp = requests.post(
                f"{self.base_url}/api/embeddings",
                json={"model": self.model, "prompt": text},
                timeout=self.timeout,
            )
        except requests.RequestException as e:
            raise RuntimeError(f"ollama unreachable at {self.base_url}: {e}") from e

        if resp.status_code != 200:
            raise RuntimeError(
                f"ollama returned HTTP {resp.status_code}: {resp.text[:200]}"
            )

        data = resp.json()
        vec = data.get("embedding")
        if not vec or not isinstance(vec, list):
            raise RuntimeError(f"ollama returned bad payload: {data}")
        if len(vec) != EMBED_DIM:
            raise RuntimeError(
                f"unexpected embedding dim: got {len(vec)}, want {EMBED_DIM} "
                f"(model={self.model})"
            )
        return vec

    def embed_many(self, texts: Iterable[str]) -> list[list[float]]:
        """
        批量 embedding。一条挂掉不影响其他条（用空列表占位 + 日志报警），
        让批量索引脚本可以"尽力而为"而不是一票否决。
        """
        out: list[list[float]] = []
        for i, text in enumerate(texts):
            try:
                out.append(self.embed_one(text))
            except Exception as e:
                logger.warning(f"[embed_many] item #{i} failed, using zero-vec: {e}")
                out.append([0.0] * EMBED_DIM)
        return out
