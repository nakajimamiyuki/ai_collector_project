"""
RAG 检索 CLI demo —— 用自然语言搜采集到的内容。

用法：
    python scripts/search.py "最近关于 RAG 的内容"
    python scripts/search.py "GLM-5.2 发布" --top-k 3
    python scripts/search.py "diffusion 模型" --source arxiv
    python scripts/search.py "Anthropic"
"""
import os

# macOS OpenMP 双库冲突 escape hatch（必须在 import numpy/faiss/milvus 前设置）
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.rag.embedder import OllamaEmbedder
from src.rag.vector_store import VectorStore


SQLITE_PATH = PROJECT_ROOT / "data" / "collector.db"
VECTOR_DB_PATH = PROJECT_ROOT / "data" / "vector.db"


def main():
    ap = argparse.ArgumentParser(description="语义搜采集到的内容")
    ap.add_argument("query", help="自然语言查询")
    ap.add_argument("--top-k", type=int, default=5, help="返回前 N 条（默认 5）")
    ap.add_argument("--source", choices=["arxiv", "bilibili", "boss_zhipin"], default=None,
                    help="只搜某一类来源（默认全部）")
    args = ap.parse_args()

    if not VECTOR_DB_PATH.exists():
        print(f"❌ 向量库不存在：{VECTOR_DB_PATH}", file=sys.stderr)
        print("   先跑：python scripts/index_final_results.py --rebuild", file=sys.stderr)
        sys.exit(1)

    embedder = OllamaEmbedder()
    store = VectorStore(db_path=str(VECTOR_DB_PATH))

    print(f"🔍 查询：{args.query}")
    if args.source:
        print(f"   过滤来源：{args.source}")
    print()

    # 1) 把查询 embed 成向量
    query_vec = embedder.embed_one(args.query)

    # 2) 在 Milvus 里搜
    hits = store.search(query_vec, top_k=args.top_k, source_type=args.source)

    if not hits:
        print("（无匹配结果）")
        return

    # 3) 展示 + 回 SQLite 拿 summary 加显
    conn = sqlite3.connect(SQLITE_PATH)
    for i, hit in enumerate(hits, 1):
        # 视觉化分数：相似度条
        bar_len = int(hit.score * 20)
        bar = "█" * bar_len + "░" * (20 - bar_len)
        source_icon = "📄" if hit.source_type == "arxiv" else "📺"

        print(f"{i}. {source_icon} [{hit.score:.3f} {bar}] {hit.title}")
        print(f"   {hit.url}")

        # 回 SQLite 拿 summary 加显（让结果更丰满）
        row = conn.execute(
            "SELECT structured_json FROM final_results WHERE url=?",
            (hit.url,),
        ).fetchone()
        if row:
            import json as _json
            try:
                d = _json.loads(row[0])
                summary = d.get("summary") or ""
                if summary:
                    print(f"   {summary[:120]}{'…' if len(summary) > 120 else ''}")
            except Exception:
                pass
        print()

    conn.close()


if __name__ == "__main__":
    main()
