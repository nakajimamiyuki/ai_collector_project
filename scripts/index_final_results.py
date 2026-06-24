"""
批量索引脚本：从 SQLite final_results → embed → 写入 Milvus Lite。

用法：
    python scripts/index_final_results.py                 # 索引全部
    python scripts/index_final_results.py --limit 10      # 只索引前 10 条
    python scripts/index_final_results.py --rebuild       # 重建（删旧 db 后全量索引）

设计：
- 幂等：同一 url 二次跑会覆盖（VectorStore.upsert 内部按 url 去重）
- 容错：单条 embed 失败只打日志、跳过，不中断整批
- 进度可见：每条打印 [N/M] url，方便看到 ollama 推理节奏
"""
import os

# macOS OpenMP 双库冲突 escape hatch（必须在 import numpy/faiss/milvus 前设置）
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import sqlite3
import sys
from pathlib import Path

# 让脚本能 import src.* —— 兼容直接 python scripts/xxx.py 跑
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.rag.embedder import OllamaEmbedder
from src.rag.vector_store import VectorStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


SQLITE_PATH = PROJECT_ROOT / "data" / "collector.db"
VECTOR_DB_PATH = PROJECT_ROOT / "data" / "vector.db"


def build_embed_text(structured: dict) -> str:
    """
    把 structured_json 里的字段拼成一段送 embed 的文本。

    顺序：标题最重要 → 简介 → 要点 → 标签
    每段用换行分隔，保证 embedding 模型能看到字段边界。
    """
    parts: list[str] = []

    title = structured.get("title") or ""
    if title:
        parts.append(f"标题：{title}")

    summary = structured.get("summary") or ""
    if summary:
        parts.append(f"简介：{summary}")

    key_points = structured.get("key_points") or []
    if isinstance(key_points, list) and key_points:
        parts.append("要点：" + "；".join(str(kp) for kp in key_points))

    tags = structured.get("tags") or []
    if isinstance(tags, list) and tags:
        parts.append("标签：" + "、".join(str(t) for t in tags))

    return "\n".join(parts).strip()


def load_final_results(sqlite_path: Path, limit: int | None) -> list[tuple[str, str, dict]]:
    """从 SQLite 加载所有 final_results，返回 [(url, source_type, parsed_json), ...]。"""
    if not sqlite_path.exists():
        raise FileNotFoundError(f"SQLite 不存在: {sqlite_path}")

    conn = sqlite3.connect(sqlite_path)
    sql = "SELECT url, source_type, structured_json FROM final_results ORDER BY id"
    if limit:
        sql += f" LIMIT {int(limit)}"
    rows = conn.execute(sql).fetchall()
    conn.close()

    out = []
    for url, source_type, sj in rows:
        try:
            parsed = json.loads(sj) if sj else {}
        except json.JSONDecodeError as e:
            logger.warning(f"[parse] {url}: structured_json 解析失败，跳过 ({e})")
            continue
        out.append((url, source_type or "bilibili", parsed))
    return out


def main():
    ap = argparse.ArgumentParser(description="批量索引 final_results 到向量库")
    ap.add_argument("--limit", type=int, default=None, help="只处理前 N 条（调试用）")
    ap.add_argument("--rebuild", action="store_true",
                    help="重建：删旧 vector.db 后全量索引")
    args = ap.parse_args()

    if args.rebuild and VECTOR_DB_PATH.exists():
        logger.info(f"[rebuild] 删除旧 vector db: {VECTOR_DB_PATH}")
        # Milvus Lite 3.x 把 db_path 当目录用（包含 LOCK + collections/）
        if VECTOR_DB_PATH.is_dir():
            shutil.rmtree(VECTOR_DB_PATH)
        else:
            os.remove(VECTOR_DB_PATH)

    VECTOR_DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    embedder = OllamaEmbedder()
    store = VectorStore(db_path=str(VECTOR_DB_PATH))

    logger.info(f"[load] 从 {SQLITE_PATH} 读 final_results...")
    records = load_final_results(SQLITE_PATH, args.limit)
    total = len(records)
    logger.info(f"[load] 共 {total} 条待索引")

    if total == 0:
        logger.warning("没有数据可索引，退出")
        return

    ok, skipped, failed = 0, 0, 0
    for i, (url, source_type, structured) in enumerate(records, 1):
        text = build_embed_text(structured)
        if not text:
            logger.warning(f"[{i}/{total}] 跳过（拼接文本为空）: {url}")
            skipped += 1
            continue

        try:
            vec = embedder.embed_one(text)
        except Exception as e:
            logger.error(f"[{i}/{total}] embed 失败: {url} | {e}")
            failed += 1
            continue

        try:
            store.upsert(
                url=url,
                source_type=source_type,
                title=structured.get("title") or "(无标题)",
                text=text,
                embedding=vec,
            )
            ok += 1
            logger.info(f"[{i}/{total}] ✅ {source_type} | {(structured.get('title') or url)[:60]}")
        except Exception as e:
            logger.error(f"[{i}/{total}] upsert 失败: {url} | {e}")
            failed += 1

    logger.info("=" * 60)
    logger.info(f"索引完成：成功 {ok} / 跳过 {skipped} / 失败 {failed} / 总计 {total}")
    logger.info(f"向量库位置：{VECTOR_DB_PATH}")


if __name__ == "__main__":
    main()
