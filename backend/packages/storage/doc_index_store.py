"""文档索引存储 — 每份文档一张索引卡，用于两阶段检索的第一阶段。

索引卡包含文档摘要、结构化目录、关键词，以及拼接后的 index_text 向量，
支持在文档级快速定位相关文档，再在命中文档内做精细 chunk 检索。
"""

from __future__ import annotations

import json
from typing import Optional

import numpy as np

from packages.common import get_logger, settings
from packages.common.types import CatalogSection, DocumentIndex

log = get_logger("storage.doc_index")


class DocIndexStore:
    """文档索引存储，支持 Milvus + PostgreSQL 和内存模式。"""

    COLLECTION = "doc_indexes"

    def __init__(self, use_memory: bool = False):
        self._use_memory = use_memory
        self._memory: dict[str, DocumentIndex] = {}  # doc_id -> DocumentIndex
        self._milvus_col = None
        self._pg_conn = None

    async def initialize(self, pg_conn=None) -> None:
        """初始化存储。pg_conn 可复用 MetadataStore 的连接。"""
        if self._use_memory:
            log.info("doc_index_store_memory_mode")
            return

        # PostgreSQL 表
        self._pg_conn = pg_conn
        if self._pg_conn:
            try:
                await self._create_table()
            except Exception as e:
                log.warning("doc_index_pg_table_failed", error=str(e))

        # Milvus collection
        try:
            from pymilvus import (
                Collection,
                CollectionSchema,
                DataType,
                FieldSchema,
                connections,
                utility,
            )

            # 复用已有连接（VectorStore 已建立）
            if not utility.has_collection(self.COLLECTION):
                fields = [
                    FieldSchema(name="doc_id", dtype=DataType.VARCHAR, max_length=64, is_primary=True),
                    FieldSchema(name="index_text", dtype=DataType.VARCHAR, max_length=8192),
                    FieldSchema(name="org_id", dtype=DataType.VARCHAR, max_length=64),
                    FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=settings.embedding_dim),
                ]
                schema = CollectionSchema(fields, description="书虫文档索引卡")
                col = Collection(self.COLLECTION, schema)
                col.create_index(
                    "embedding",
                    {"index_type": "IVF_FLAT", "metric_type": "COSINE", "params": {"nlist": 32}},
                )
                col.load()
                log.info("doc_index_milvus_collection_created")
            else:
                col = Collection(self.COLLECTION)
                col.load()
                log.info("doc_index_milvus_collection_loaded")

            self._milvus_col = col
        except Exception as e:
            log.warning("doc_index_milvus_fallback_to_memory", error=str(e))
            self._use_memory = True

    async def _create_table(self) -> None:
        assert self._pg_conn is not None
        async with self._pg_conn.cursor() as cur:
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS document_indexes (
                    doc_id       VARCHAR(64) PRIMARY KEY,
                    title        VARCHAR(512),
                    summary      TEXT,
                    catalog_json JSONB,
                    keywords     TEXT,
                    index_text   TEXT,
                    doc_type     VARCHAR(64),
                    category_path VARCHAR(256),
                    org_id       VARCHAR(64) DEFAULT 'default',
                    created_at   TIMESTAMPTZ DEFAULT NOW()
                )
            """)
            await self._pg_conn.commit()

    async def upsert_index(self, doc_index: DocumentIndex) -> None:
        """存储或更新文档索引卡。"""
        if self._use_memory:
            self._memory[doc_index.doc_id] = doc_index
            log.info("doc_index_upserted_memory", doc_id=doc_index.doc_id)
            return

        # PostgreSQL
        if self._pg_conn:
            catalog_json = json.dumps(
                [s.model_dump() for s in doc_index.catalog], ensure_ascii=False
            )
            async with self._pg_conn.cursor() as cur:
                await cur.execute(
                    """
                    INSERT INTO document_indexes
                        (doc_id, title, summary, catalog_json, keywords,
                         index_text, doc_type, category_path, org_id)
                    VALUES (%s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s)
                    ON CONFLICT (doc_id) DO UPDATE SET
                        title = EXCLUDED.title,
                        summary = EXCLUDED.summary,
                        catalog_json = EXCLUDED.catalog_json,
                        keywords = EXCLUDED.keywords,
                        index_text = EXCLUDED.index_text,
                        doc_type = EXCLUDED.doc_type,
                        category_path = EXCLUDED.category_path
                    """,
                    (
                        doc_index.doc_id,
                        doc_index.title,
                        doc_index.summary,
                        catalog_json,
                        ",".join(doc_index.keywords),
                        doc_index.index_text,
                        doc_index.doc_type,
                        doc_index.category_path,
                        doc_index.org_id,
                    ),
                )
                await self._pg_conn.commit()

        # Milvus — 向量索引
        if self._milvus_col and doc_index.embedding:
            # 先删除旧记录再插入（Milvus 不支持 upsert）
            self._milvus_col.delete(f'doc_id == "{doc_index.doc_id}"')
            data = [
                [doc_index.doc_id],
                [doc_index.index_text[:8192]],
                [doc_index.org_id],
                [doc_index.embedding],
            ]
            self._milvus_col.insert(data)
            self._milvus_col.flush()

        log.info("doc_index_upserted", doc_id=doc_index.doc_id)

    async def search_indexes(
        self,
        query_embedding: list[float],
        top_k: int = 8,
        org_id: str | None = None,
    ) -> list[dict]:
        """向量检索文档索引卡，返回 [{doc_id, index_text, score}, ...]。"""
        if self._use_memory:
            return self._memory_search(query_embedding, top_k, org_id)

        if not self._milvus_col:
            return self._memory_search(query_embedding, top_k, org_id)

        expr = f'org_id == "{org_id}"' if org_id else None
        results = self._milvus_col.search(
            data=[query_embedding],
            anns_field="embedding",
            param={"metric_type": "COSINE", "params": {"nprobe": 8}},
            limit=top_k,
            expr=expr,
            output_fields=["index_text", "org_id"],
        )
        hits = []
        for hit in results[0]:
            hits.append({
                "doc_id": hit.id,
                "index_text": hit.entity.get("index_text", ""),
                "score": hit.score,
            })
        return hits

    def _memory_search(
        self,
        query_embedding: list[float],
        top_k: int,
        org_id: str | None = None,
    ) -> list[dict]:
        """内存模式的余弦相似度搜索。"""
        if not self._memory:
            return []

        query_vec = np.array(query_embedding, dtype=np.float32)
        query_norm = np.linalg.norm(query_vec)
        if query_norm == 0:
            return []

        scored = []
        for doc_index in self._memory.values():
            if org_id and doc_index.org_id != org_id:
                continue
            if not doc_index.embedding:
                continue
            idx_vec = np.array(doc_index.embedding, dtype=np.float32)
            idx_norm = np.linalg.norm(idx_vec)
            if idx_norm == 0:
                continue
            cos_sim = float(np.dot(query_vec, idx_vec) / (query_norm * idx_norm))
            scored.append((cos_sim, doc_index))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [
            {
                "doc_id": di.doc_id,
                "index_text": di.index_text,
                "score": s,
            }
            for s, di in scored[:top_k]
        ]

    async def get_index(self, doc_id: str) -> DocumentIndex | None:
        """获取单个文档索引卡。"""
        if self._use_memory:
            return self._memory.get(doc_id)

        if not self._pg_conn:
            return self._memory.get(doc_id)

        async with self._pg_conn.cursor() as cur:
            await cur.execute(
                "SELECT * FROM document_indexes WHERE doc_id = %s", (doc_id,)
            )
            row = await cur.fetchone()
            if not row or not cur.description:
                return None
            data = dict(zip([d.name for d in cur.description], row))
            catalog_raw = data.get("catalog_json") or []
            if isinstance(catalog_raw, str):
                catalog_raw = json.loads(catalog_raw)
            return DocumentIndex(
                doc_id=data["doc_id"],
                title=data.get("title", ""),
                summary=data.get("summary", ""),
                catalog=[CatalogSection(**s) for s in catalog_raw],
                keywords=(data.get("keywords") or "").split(","),
                doc_type=data.get("doc_type", ""),
                category_path=data.get("category_path", ""),
                org_id=data.get("org_id", "default"),
                index_text=data.get("index_text", ""),
            )

    @property
    def index_count(self) -> int:
        if self._use_memory:
            return len(self._memory)
        if self._milvus_col:
            return self._milvus_col.num_entities
        return 0

    async def close(self) -> None:
        pass  # 连接由 MetadataStore / VectorStore 管理
