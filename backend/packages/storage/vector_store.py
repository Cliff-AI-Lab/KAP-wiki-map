"""向量存储 — Milvus 封装，含内存 fallback。"""

from __future__ import annotations

import hashlib
from typing import Optional

import numpy as np

from packages.common import get_logger, settings
from packages.common.types import KnowledgeChunk

log = get_logger("storage.vector")


class VectorStore:
    """向量存储，支持 Milvus 和内存模式。"""

    COLLECTION = "knowledge_chunks"
    CONTENT_MAX_LENGTH = 8192

    def __init__(self, use_memory: bool = False):
        self._use_memory = use_memory
        self._memory_chunks: list[KnowledgeChunk] = []
        self._client = None
        self._has_domain_id = True  # 旧 schema 可能缺少 domain_id 字段

    async def initialize(self) -> None:
        if self._use_memory:
            log.info("vector_store_memory_mode")
            return

        try:
            from pymilvus import connections, utility, Collection, CollectionSchema, FieldSchema, DataType

            connections.connect(host=settings.milvus_host, port=str(settings.milvus_port))

            # V11.3: 检查旧 collection 是否缺少 domain_id 字段
            # 不自动 drop（会丢数据），改为标记并跳过插入带 domain 的 chunks
            if utility.has_collection(self.COLLECTION):
                col = Collection(self.COLLECTION)
                existing_fields = {f.name for f in col.schema.fields}
                if "domain_id" not in existing_fields:
                    log.error(
                        "milvus_schema_outdated",
                        missing_field="domain_id",
                        action="请手动备份后执行: utility.drop_collection('knowledge_chunks') 再重启",
                    )
                    # 继续使用旧 collection，domain_filter 和 insert 自动降级
                    self._client = col
                    self._has_domain_id = False
                    col.load()
                    return

            if not utility.has_collection(self.COLLECTION):
                fields = [
                    FieldSchema(name="chunk_id", dtype=DataType.VARCHAR, max_length=64, is_primary=True),
                    FieldSchema(name="doc_id", dtype=DataType.VARCHAR, max_length=64),
                    FieldSchema(name="content", dtype=DataType.VARCHAR, max_length=VectorStore.CONTENT_MAX_LENGTH),
                    FieldSchema(name="category_path", dtype=DataType.VARCHAR, max_length=256),
                    FieldSchema(name="doc_type", dtype=DataType.VARCHAR, max_length=32),
                    FieldSchema(name="source_system", dtype=DataType.VARCHAR, max_length=32),
                    FieldSchema(name="parent_chunk_id", dtype=DataType.VARCHAR, max_length=64),
                    FieldSchema(name="org_id", dtype=DataType.VARCHAR, max_length=64),
                    FieldSchema(name="domain_id", dtype=DataType.VARCHAR, max_length=128),
                    FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=settings.embedding_dim),
                ]
                schema = CollectionSchema(fields, description="书虫知识切片")
                col = Collection(self.COLLECTION, schema)
                col.create_index("embedding", {"index_type": "IVF_FLAT", "metric_type": "COSINE", "params": {"nlist": 128}})
                col.load()
                log.info("milvus_collection_created")
            else:
                col = Collection(self.COLLECTION)
                col.load()
                log.info("milvus_collection_loaded")

            self._client = col
        except Exception as e:
            log.warning("vector_store_fallback_to_memory", error=str(e))
            self._use_memory = True

    async def insert_chunks(self, chunks: list[KnowledgeChunk]) -> int:
        if not chunks:
            return 0

        # 校验 embedding 有效性
        valid_chunks = []
        for c in chunks:
            if not c.embedding:
                log.warning("vector_empty_embedding", chunk_id=c.chunk_id, doc_id=c.doc_id)
                continue
            if len(c.embedding) != settings.embedding_dim:
                log.warning(
                    "vector_dim_mismatch",
                    chunk_id=c.chunk_id,
                    doc_id=c.doc_id,
                    expected=settings.embedding_dim,
                    actual=len(c.embedding),
                )
                continue
            valid_chunks.append(c)

        if len(valid_chunks) < len(chunks):
            log.warning(
                "vector_chunks_filtered",
                total=len(chunks),
                valid=len(valid_chunks),
                skipped=len(chunks) - len(valid_chunks),
            )

        if not valid_chunks:
            return 0
        chunks = valid_chunks

        if self._use_memory:
            self._memory_chunks.extend(chunks)
            log.info("vector_store_memory_insert", count=len(chunks))
            return len(chunks)

        truncated = 0
        contents = []
        for c in chunks:
            if len(c.content) > self.CONTENT_MAX_LENGTH:
                truncated += 1
                contents.append(c.content[:self.CONTENT_MAX_LENGTH])
            else:
                contents.append(c.content)
        if truncated:
            log.warning(
                "vector_content_truncated",
                truncated_count=truncated,
                max_length=self.CONTENT_MAX_LENGTH,
            )

        data = [
            [c.chunk_id for c in chunks],
            [c.doc_id for c in chunks],
            contents,
            [c.category_path for c in chunks],
            [c.doc_type for c in chunks],
            [c.source_system for c in chunks],
            [c.parent_chunk_id or "" for c in chunks],
            [c.org_id for c in chunks],
        ]
        if self._has_domain_id:
            data.append([c.domain_id or "" for c in chunks])
        data.append([c.embedding for c in chunks])
        self._client.insert(data)
        self._client.flush()
        log.info("milvus_insert_done", count=len(chunks))
        return len(chunks)

    async def search(
        self,
        query_embedding: list[float],
        top_k: int = 5,
        category_filter: Optional[str] = None,
        org_id: Optional[str] = None,
        doc_id_filter: Optional[list[str]] = None,
        domain_filter: Optional[list[str]] = None,
    ) -> list[dict]:
        """向量检索。

        domain_filter: Skills 模式 — 仅在指定知识域内检索。
        doc_id_filter: 两阶段模式 — 仅在指定文档内检索。
        """
        if self._use_memory:
            return self._memory_search(query_embedding, top_k, category_filter, org_id, doc_id_filter, domain_filter)

        def _safe_str(val: str) -> str:
            """转义 Milvus 表达式中的双引号，防止注入。"""
            return val.replace('\\', '\\\\').replace('"', '\\"')

        expr_parts = []
        if category_filter:
            expr_parts.append(f'category_path == "{_safe_str(category_filter)}"')
        if org_id:
            expr_parts.append(f'org_id == "{_safe_str(org_id)}"')
        if doc_id_filter:
            id_list = ", ".join(f'"{_safe_str(did)}"' for did in doc_id_filter)
            expr_parts.append(f"doc_id in [{id_list}]")
        if domain_filter and self._has_domain_id:
            # Skills 模式：按知识体系分支过滤，支持前缀匹配（旧 schema 降级跳过）
            domain_conditions = []
            for d in domain_filter:
                safe_d = _safe_str(d)
                domain_conditions.append(f'domain_id == "{safe_d}"')
                domain_conditions.append(f'domain_id like "{safe_d}/%"')
            expr_parts.append(f"({' or '.join(domain_conditions)})")
        expr = " and ".join(expr_parts) if expr_parts else None
        output_fields = ["doc_id", "content", "category_path", "doc_type", "source_system", "parent_chunk_id", "org_id"]
        if self._has_domain_id:
            output_fields.append("domain_id")
        results = self._client.search(
            data=[query_embedding],
            anns_field="embedding",
            param={"metric_type": "COSINE", "params": {"nprobe": 16}},
            limit=top_k,
            expr=expr,
            output_fields=output_fields,
        )
        hits = []
        for hit in results[0]:
            hits.append({
                "chunk_id": hit.id,
                "doc_id": hit.entity.get("doc_id"),
                "content": hit.entity.get("content"),
                "category_path": hit.entity.get("category_path"),
                "doc_type": hit.entity.get("doc_type", ""),
                "source_system": hit.entity.get("source_system", ""),
                "score": hit.score,
            })
        return hits

    def _memory_search(
        self,
        query_embedding: list[float],
        top_k: int,
        category_filter: Optional[str],
        org_id: Optional[str] = None,
        doc_id_filter: Optional[list[str]] = None,
        domain_filter: Optional[list[str]] = None,
    ) -> list[dict]:
        """内存模式的余弦相似度搜索。"""
        if not self._memory_chunks:
            return []

        query_vec = np.array(query_embedding, dtype=np.float32)
        query_norm = np.linalg.norm(query_vec)
        if query_norm == 0:
            return []

        doc_id_set = set(doc_id_filter) if doc_id_filter else None
        domain_set = set(domain_filter) if domain_filter else None

        scored = []
        for chunk in self._memory_chunks:
            if category_filter and chunk.category_path != category_filter:
                continue
            if org_id and chunk.org_id != org_id:
                continue
            if doc_id_set and chunk.doc_id not in doc_id_set:
                continue
            # Skills 模式域过滤：与 Milvus 行为对齐 — 空 domain_id 的 chunk 也被排除
            if domain_set:
                if not chunk.domain_id or not any(
                    chunk.domain_id == d or chunk.domain_id.startswith(d + "/") for d in domain_set
                ):
                    continue
            if not chunk.embedding:
                continue
            chunk_vec = np.array(chunk.embedding, dtype=np.float32)
            chunk_norm = np.linalg.norm(chunk_vec)
            if chunk_norm == 0:
                continue
            cos_sim = float(np.dot(query_vec, chunk_vec) / (query_norm * chunk_norm))
            scored.append((cos_sim, chunk))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [
            {
                "chunk_id": c.chunk_id,
                "doc_id": c.doc_id,
                "content": c.content,
                "category_path": c.category_path,
                "score": s,
            }
            for s, c in scored[:top_k]
        ]

    async def clear_all(self) -> None:
        """清除所有向量数据（仅用于测试/重灌）。"""
        if self._use_memory:
            self._memory_chunks.clear()
            log.info("vector_store_cleared_memory")
            return
        if self._client:
            from pymilvus import utility
            if utility.has_collection(self.COLLECTION):
                self._client.delete(expr="chunk_id != ''")
                self._client.flush()
            log.info("vector_store_cleared_milvus")

    @property
    def chunk_count(self) -> int:
        if self._use_memory:
            return len(self._memory_chunks)
        return self._client.num_entities if self._client else 0

    def get_all_chunks_for_bm25(self) -> list[dict]:
        """导出所有 chunk 的文本数据，用于构建 BM25 索引。"""
        if self._use_memory:
            return [
                {"chunk_id": c.chunk_id, "doc_id": c.doc_id, "content": c.content}
                for c in self._memory_chunks
            ]
        if not self._client:
            return []
        # Milvus: query all chunks
        # Milvus 单次查询 limit 最大 16384，分批加载
        results = []
        batch_size = 10000
        offset = 0
        while True:
            batch = self._client.query(
                expr="chunk_id != ''",
                output_fields=["chunk_id", "doc_id", "content"],
                limit=batch_size,
                offset=offset,
            )
            results.extend(batch)
            if len(batch) < batch_size:
                break
            offset += batch_size
        return [
            {"chunk_id": r["chunk_id"], "doc_id": r["doc_id"], "content": r["content"]}
            for r in results
        ]
