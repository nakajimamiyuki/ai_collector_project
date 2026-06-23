"""
Milvus Lite 向量存储封装。

设计：
- 一条 final_results = 一个向量（title + summary + key_points 拼接后 embed）
- 检索返回 url + title + source_type + 相似度分数，调用方拿 url 回 SQLite 查全量
- 用 Milvus Lite（单文件，无需起服务），生产可平滑迁到 Milvus Cluster

为什么不分 chunk：
- 当前数据量 ~50 条，整段 embed 足够，引入 chunk 反而引入"拼接召回"复杂度
- 等数据上千条 + 单条内容很长时再上 chunk 不迟（YAGNI）
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Iterable

from pymilvus import MilvusClient, DataType

from src.rag.embedder import EMBED_DIM

logger = logging.getLogger(__name__)


DEFAULT_COLLECTION = "ai_collector_chunks"

# Milvus VARCHAR 必须指定 max_length；这些数字是按当前数据保守上限定的，
# 写小了插入会截断 / 报错，写太大白白占内存。
URL_MAX = 512
SOURCE_TYPE_MAX = 32
TITLE_MAX = 512
TEXT_MAX = 8192     # title + summary + key_points 拼起来一般 1-3k，给 8k 余量


@dataclass
class SearchHit:
    """检索结果的最小契约 —— 用 dataclass 避免下游写一堆 dict['xxx']。"""
    url: str
    source_type: str
    title: str
    score: float       # 0-1 余弦相似度（已从 Milvus 的 cosine distance 转换），越大越相似


class VectorStore:
    """Milvus Lite 上的向量库；保持薄封装，不抢业务逻辑。"""

    def __init__(
        self,
        db_path: str,
        collection: str = DEFAULT_COLLECTION,
    ):
        self.db_path = db_path
        self.collection = collection
        # MilvusClient(uri="path.db") 自动用 Milvus Lite 单文件模式
        self.client = MilvusClient(uri=db_path)
        self._ensure_collection()

    # ------------------------------------------------------------------
    # schema / 建表
    # ------------------------------------------------------------------
    def _ensure_collection(self) -> None:
        """幂等建表：已存在则跳过，第一次跑时建出来；最后总是 load 到内存。"""
        if not self.client.has_collection(self.collection):
            schema = self.client.create_schema(
                auto_id=True,
                enable_dynamic_field=False,
            )
            schema.add_field("id", DataType.INT64, is_primary=True)
            schema.add_field("url", DataType.VARCHAR, max_length=URL_MAX)
            schema.add_field("source_type", DataType.VARCHAR, max_length=SOURCE_TYPE_MAX)
            schema.add_field("title", DataType.VARCHAR, max_length=TITLE_MAX)
            schema.add_field("text", DataType.VARCHAR, max_length=TEXT_MAX)
            schema.add_field("embedding", DataType.FLOAT_VECTOR, dim=EMBED_DIM)

            # 索引：HNSW + COSINE。COSINE 对中文 embedding 通常比 L2 召回更准。
            index_params = self.client.prepare_index_params()
            index_params.add_index(
                field_name="embedding",
                index_type="AUTOINDEX",   # Milvus Lite 仅支持 AUTOINDEX，云上版可换 HNSW/IVF
                metric_type="COSINE",
            )
            self.client.create_collection(
                collection_name=self.collection,
                schema=schema,
                index_params=index_params,
            )
            logger.info(f"[VectorStore] collection '{self.collection}' created at {self.db_path}")

        # 必须 load 到内存才能 search —— Milvus 跨进程时 collection 默认是 released 状态
        self.client.load_collection(self.collection)

    # ------------------------------------------------------------------
    # 写入
    # ------------------------------------------------------------------
    def upsert(
        self,
        *,
        url: str,
        source_type: str,
        title: str,
        text: str,
        embedding: list[float],
    ) -> None:
        """
        按 url 去重写入：先删后插。
        Milvus Lite 不支持 UPSERT 主键操作（id 是 auto），所以这里手动做。
        """
        if len(embedding) != EMBED_DIM:
            raise ValueError(
                f"embedding dim mismatch: got {len(embedding)}, want {EMBED_DIM}"
            )
        # 截断超长字段，防止 Milvus 报 length exceeded
        title = (title or "")[:TITLE_MAX]
        text = (text or "")[:TEXT_MAX]
        source_type = (source_type or "")[:SOURCE_TYPE_MAX]

        # 1) 删旧
        self.client.delete(
            collection_name=self.collection,
            filter=f'url == "{url}"',
        )
        # 2) 插新
        self.client.insert(
            collection_name=self.collection,
            data=[{
                "url": url,
                "source_type": source_type,
                "title": title,
                "text": text,
                "embedding": embedding,
            }],
        )

    def count(self) -> int:
        """当前 collection 里有多少条 —— 给批量索引脚本最后打报告用。"""
        stats = self.client.get_collection_stats(self.collection)
        return int(stats.get("row_count", 0))

    # ------------------------------------------------------------------
    # 检索
    # ------------------------------------------------------------------
    def search(
        self,
        query_embedding: list[float],
        top_k: int = 5,
        source_type: str | None = None,
    ) -> list[SearchHit]:
        """
        语义检索。可选按 source_type 过滤（'arxiv' / 'bilibili'）。
        返回相似度从高到低（COSINE 下分数越大越相似）。
        """
        if len(query_embedding) != EMBED_DIM:
            raise ValueError(
                f"query embedding dim mismatch: got {len(query_embedding)}, want {EMBED_DIM}"
            )

        filter_expr = f'source_type == "{source_type}"' if source_type else ""

        results = self.client.search(
            collection_name=self.collection,
            data=[query_embedding],
            limit=top_k,
            filter=filter_expr,
            output_fields=["url", "source_type", "title"],
        )

        # Milvus 返回的是 [[hit, hit, ...]] —— 外层每个 query 一个列表
        # COSINE metric 下 Milvus 返回的是 "cosine distance"（0=完全同向, 2=完全反向），
        # 我们把它转成更直觉的 0-1 相似度（1=完全匹配, 0.5=正交, 0=完全相反）。
        hits: list[SearchHit] = []
        if results and results[0]:
            for h in results[0]:
                ent = h.get("entity", {})
                distance = float(h.get("distance", 0.0))
                similarity = 1.0 - distance / 2.0
                hits.append(SearchHit(
                    url=ent.get("url", ""),
                    source_type=ent.get("source_type", ""),
                    title=ent.get("title", ""),
                    score=similarity,
                ))
        return hits
