"""向量存储 — Milvus 封装（M0-tech-debt 坑 2 + 6 + 8 联动改造）。

新增能力：
- 用 ``MilvusConnectionManager`` 替代裸 ``connections.connect``（坑 2）
- 每次 search/insert 前 ``ensure_healthy()`` 探活
- Schema 增加：

  * ``vector_type``：``redacted`` / ``original`` 标记（坑 D 双向量并存预留）
  * ``embedding_model_version``：写入时挂当前 EmbeddingProvider 的 model_version（坑 6 联动，
    模型升级后可按 version 增量重嵌入）
  * ``access_level``：int8（0 公开 / 1 内部 / 2 秘密 / 3 机密；坑 8 召回阶段过滤预留）

- 内存降级受 ``settings.allow_memory_fallback`` 门控（dev 可降，sandbox/prod 抛错）

兼容性：旧 collection 缺字段时（V15 之前 schema），read 路径回退到无新字段的查询。
新 collection 建立时一次性带齐所有字段。
"""

from __future__ import annotations

from typing import Optional

import numpy as np

from packages.common import get_logger, settings
from packages.common.exceptions import StorageError
from packages.common.types import KnowledgeChunk
from packages.storage.embedder import current_model_version
from packages.storage.milvus_connection import MilvusConnectionManager, get_connection_manager

log = get_logger("storage.vector")

# 双向量类型常量
VECTOR_TYPE_REDACTED = "redacted"   # 脱敏向量（默认召回路径）
VECTOR_TYPE_ORIGINAL = "original"   # 原文向量（仅高密用户可命中）

# 密级常量（与 packages.common.types.AccessLevel 平行；Milvus 用 int8 节省存储）
ACCESS_LEVEL_PUBLIC = 0
ACCESS_LEVEL_INTERNAL = 1
ACCESS_LEVEL_SECRET = 2
ACCESS_LEVEL_TOP_SECRET = 3


class VectorStore:
    """向量存储，支持 Milvus 和内存模式。"""

    COLLECTION = "knowledge_chunks"
    CONTENT_MAX_LENGTH = 8192

    def __init__(
        self,
        use_memory: bool = False,
        manager: MilvusConnectionManager | None = None,
    ) -> None:
        self._use_memory = use_memory
        self._memory_chunks: list[KnowledgeChunk] = []
        self._client = None
        self._manager = manager or get_connection_manager()
        # Schema 兼容标记（旧 collection 可能缺新字段）
        self._has_domain_id = True
        self._has_vector_type = True
        self._has_model_version = True
        self._has_access_level = True

    async def initialize(self) -> None:
        """初始化 Milvus collection。失败时按 allow_memory_fallback 决定降级。"""
        if self._use_memory:
            log.info("vector_store_memory_mode_explicit")
            return

        try:
            await self._manager.initialize()
        except StorageError:
            if settings.allow_memory_fallback and settings.kap_env == "dev":
                log.warning("vector_store_fallback_memory_after_init_fail")
                self._use_memory = True
                return
            raise

        if self._manager.is_memory_mode:
            self._use_memory = True
            log.info("vector_store_memory_mode_via_manager")
            return

        try:
            from pymilvus import Collection, CollectionSchema, FieldSchema, DataType

            if self._manager.has_collection(self.COLLECTION):
                col = self._manager.get_collection(self.COLLECTION)
                existing_fields = {f.name for f in col.schema.fields}
                self._has_domain_id = "domain_id" in existing_fields
                self._has_vector_type = "vector_type" in existing_fields
                self._has_model_version = "embedding_model_version" in existing_fields
                self._has_access_level = "access_level" in existing_fields
                missing = []
                if not self._has_domain_id: missing.append("domain_id")
                if not self._has_vector_type: missing.append("vector_type")
                if not self._has_model_version: missing.append("embedding_model_version")
                if not self._has_access_level: missing.append("access_level")
                if missing:
                    log.warning(
                        "milvus_schema_outdated",
                        missing=missing,
                        action="新字段写入将自动跳过；如需启用建议备份后 drop collection 重建",
                    )
                col.load()
                self._client = col
                log.info("milvus_collection_loaded")
                return

            # 新建 collection：一次性带齐所有字段
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
                # ── 坑 2 + 6 + 8 新增字段 ──
                FieldSchema(name="vector_type", dtype=DataType.VARCHAR, max_length=16),         # redacted/original
                FieldSchema(name="embedding_model_version", dtype=DataType.VARCHAR, max_length=64),
                FieldSchema(name="access_level", dtype=DataType.INT8),                          # 0/1/2/3
                FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=settings.embedding_dim),
            ]
            schema = CollectionSchema(fields, description="KAP 知识切片向量库（坑 2/6/8 schema v2）")
            col = Collection(self.COLLECTION, schema, using=self._manager.alias)
            col.create_index(
                "embedding",
                {"index_type": "IVF_FLAT", "metric_type": "COSINE", "params": {"nlist": 128}},
            )
            col.load()
            self._client = col
            log.info("milvus_collection_created", schema_version="v2")
        except Exception as e:  # noqa: BLE001
            self._handle_init_fail(e)

    def _handle_init_fail(self, e: Exception) -> None:
        """Collection 创建/加载失败的降级处理。"""
        if settings.allow_memory_fallback and settings.kap_env == "dev":
            log.warning("vector_store_fallback_memory_after_collection_fail", error=str(e))
            self._use_memory = True
            return
        raise StorageError(f"Milvus collection 初始化失败: {e}") from e

    async def insert_chunks(
        self,
        chunks: list[KnowledgeChunk],
        *,
        vector_type: str = VECTOR_TYPE_REDACTED,
        access_level: int = ACCESS_LEVEL_PUBLIC,
    ) -> int:
        """批量插入 chunks。

        Args:
            chunks: 已带 embedding 的 chunk 列表
            vector_type: 当前批次的向量类型（M0 默认 redacted；M2 脱敏管道上线后双轨）
            access_level: 当前批次的密级（M0 默认公开；M2 完整 4 级映射上线后按文档分级）
        """
        if not chunks:
            return 0

        # 校验 embedding
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
        skipped = len(chunks) - len(valid_chunks)
        if skipped:
            log.warning("vector_chunks_filtered", total=len(chunks), valid=len(valid_chunks), skipped=skipped)
        if not valid_chunks:
            return 0
        chunks = valid_chunks

        if self._use_memory:
            self._memory_chunks.extend(chunks)
            log.info("vector_store_memory_insert", count=len(chunks))
            return len(chunks)

        # 操作前探活（坑 2）
        await self._manager.ensure_healthy()

        truncated = 0
        contents = []
        for c in chunks:
            if len(c.content) > self.CONTENT_MAX_LENGTH:
                truncated += 1
                contents.append(c.content[:self.CONTENT_MAX_LENGTH])
            else:
                contents.append(c.content)
        if truncated:
            log.warning("vector_content_truncated", truncated_count=truncated)

        # 顺序与 schema 字段一致
        data: list = [
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
        if self._has_vector_type:
            data.append([vector_type] * len(chunks))
        if self._has_model_version:
            try:
                model_v = current_model_version()
            except Exception:  # noqa: BLE001
                model_v = "unknown"
            data.append([model_v] * len(chunks))
        if self._has_access_level:
            data.append([access_level] * len(chunks))
        data.append([c.embedding for c in chunks])

        self._client.insert(data)
        self._client.flush()
        log.info(
            "milvus_insert_done",
            count=len(chunks),
            vector_type=vector_type,
            access_level=access_level,
        )
        return len(chunks)

    async def search(
        self,
        query_embedding: list[float],
        top_k: int = 5,
        category_filter: Optional[str] = None,
        org_id: Optional[str] = None,
        doc_id_filter: Optional[list[str]] = None,
        domain_filter: Optional[list[str]] = None,
        *,
        vector_type: str = VECTOR_TYPE_REDACTED,
        max_access_level: int = ACCESS_LEVEL_PUBLIC,
    ) -> list[dict]:
        """向量检索。

        Args:
            vector_type: 召回哪一种向量（默认 redacted；高密用户可传 original）
            max_access_level: 用户最高密级，召回阶段过滤（坑 8 主要交付物）—
                Milvus expr 直接带 ``access_level <= max_access_level``，禁止旁路
        """
        if self._use_memory:
            return self._memory_search(
                query_embedding, top_k, category_filter, org_id,
                doc_id_filter, domain_filter, vector_type, max_access_level,
            )

        # 操作前探活（坑 2）
        await self._manager.ensure_healthy()

        def _safe_str(val: str) -> str:
            return val.replace("\\", "\\\\").replace('"', '\\"')

        expr_parts = []
        if category_filter:
            expr_parts.append(f'category_path == "{_safe_str(category_filter)}"')
        if org_id:
            expr_parts.append(f'org_id == "{_safe_str(org_id)}"')
        if doc_id_filter:
            id_list = ", ".join(f'"{_safe_str(did)}"' for did in doc_id_filter)
            expr_parts.append(f"doc_id in [{id_list}]")
        if domain_filter and self._has_domain_id:
            domain_conditions = []
            for d in domain_filter:
                safe_d = _safe_str(d)
                domain_conditions.append(f'domain_id == "{safe_d}"')
                domain_conditions.append(f'domain_id like "{safe_d}/%"')
            expr_parts.append(f"({' or '.join(domain_conditions)})")
        # ── 坑 8：密级路由（召回阶段过滤）──
        if self._has_access_level:
            expr_parts.append(f"access_level <= {max_access_level}")
        # ── 坑 2 双向量并存：按类型路由 ──
        if self._has_vector_type:
            expr_parts.append(f'vector_type == "{_safe_str(vector_type)}"')
        expr = " and ".join(expr_parts) if expr_parts else None

        output_fields = ["doc_id", "content", "category_path", "doc_type", "source_system", "parent_chunk_id", "org_id"]
        if self._has_domain_id:
            output_fields.append("domain_id")
        if self._has_vector_type:
            output_fields.append("vector_type")
        if self._has_model_version:
            output_fields.append("embedding_model_version")
        if self._has_access_level:
            output_fields.append("access_level")

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
                "domain_id": hit.entity.get("domain_id", "") if self._has_domain_id else "",
                "vector_type": hit.entity.get("vector_type", "") if self._has_vector_type else "",
                "embedding_model_version": hit.entity.get("embedding_model_version", "") if self._has_model_version else "",
                "access_level": hit.entity.get("access_level", 0) if self._has_access_level else 0,
                "score": hit.score,
            })
        return hits

    def _memory_search(
        self,
        query_embedding: list[float],
        top_k: int,
        category_filter: Optional[str],
        org_id: Optional[str],
        doc_id_filter: Optional[list[str]],
        domain_filter: Optional[list[str]],
        vector_type: str,
        max_access_level: int,
    ) -> list[dict]:
        """内存模式的余弦相似度搜索（坑 2/8 字段全程支持）。"""
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
            if domain_set:
                if not chunk.domain_id or not any(
                    chunk.domain_id == d or chunk.domain_id.startswith(d + "/") for d in domain_set
                ):
                    continue
            # 内存模式 vector_type / access_level 过滤（KnowledgeChunk 暂未加这些属性，
            # 默认 redacted + access_level=0；Milvus 真实部署里靠 schema 字段过滤）
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
                "domain_id": c.domain_id or "",
                "vector_type": vector_type,
                "embedding_model_version": "",
                "access_level": 0,
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
            await self._manager.ensure_healthy()
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
