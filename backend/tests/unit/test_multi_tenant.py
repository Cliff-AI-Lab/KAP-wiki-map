"""多租户数据模型单元测试。"""

import pytest
from packages.common.types import RawDocument, KnowledgeChunk, SearchResult, SourceSystem
from packages.storage.metadata_store import MetadataStore
from packages.storage.vector_store import VectorStore
from packages.storage.chunker import chunk_document


class TestMultiTenantDefaults:
    """验证新增 org_id 字段的默认值。"""

    def test_raw_document_default_org_id(self):
        doc = RawDocument(
            doc_id="test_001",
            title="测试文档",
            content="内容",
            source_system=SourceSystem.FEISHU,
        )
        assert doc.org_id == "default"

    def test_knowledge_chunk_default_org_id(self):
        chunk = KnowledgeChunk(
            chunk_id="chunk_001",
            doc_id="test_001",
            chunk_index=0,
            content="内容片段",
        )
        assert chunk.org_id == "default"

    def test_search_result_default_org_id(self):
        result = SearchResult(doc_id="test_001")
        assert result.org_id == "default"

    def test_raw_document_custom_org_id(self):
        doc = RawDocument(
            doc_id="test_002",
            title="企业A文档",
            content="内容",
            source_system=SourceSystem.DINGTALK,
            org_id="org_enterprise_a",
        )
        assert doc.org_id == "org_enterprise_a"


@pytest.mark.asyncio
class TestMetadataStoreOrgId:
    """MetadataStore 按 org_id 过滤测试。"""

    async def test_list_documents_filter_by_org_id(self):
        store = MetadataStore(use_memory=True)
        await store.initialize()

        await store.upsert_document({
            "id": "doc_a1", "title": "企业A文档1", "source_system": "feishu",
            "doc_type": "技术文档", "version_id": None,
            "status": "ACTIVE", "decision": "KEEP", "kpi_retain": 0.8,
            "summary": "", "keywords": "", "category_path": "",
            "org_id": "org_a", "created_at": None, "updated_at": None,
        })
        await store.upsert_document({
            "id": "doc_b1", "title": "企业B文档1", "source_system": "dingtalk",
            "doc_type": "会议纪要", "version_id": None,
            "status": "ACTIVE", "decision": "KEEP", "kpi_retain": 0.7,
            "summary": "", "keywords": "", "category_path": "",
            "org_id": "org_b", "created_at": None, "updated_at": None,
        })
        await store.upsert_document({
            "id": "doc_a2", "title": "企业A文档2", "source_system": "feishu",
            "doc_type": "流程说明", "version_id": None,
            "status": "ACTIVE", "decision": "KEEP", "kpi_retain": 0.9,
            "summary": "", "keywords": "", "category_path": "",
            "org_id": "org_a", "created_at": None, "updated_at": None,
        })

        # 按 org_a 过滤
        org_a_docs = await store.list_documents(org_id="org_a")
        assert len(org_a_docs) == 2
        assert all(d["org_id"] == "org_a" for d in org_a_docs)

        # 按 org_b 过滤
        org_b_docs = await store.list_documents(org_id="org_b")
        assert len(org_b_docs) == 1
        assert org_b_docs[0]["id"] == "doc_b1"

        # 不传 org_id 返回全部
        all_docs = await store.list_documents()
        assert len(all_docs) == 3

    async def test_list_documents_combined_filters(self):
        store = MetadataStore(use_memory=True)
        await store.initialize()

        await store.upsert_document({
            "id": "doc_c1", "title": "ACTIVE文档", "source_system": "wecom",
            "doc_type": "通知公告", "version_id": None,
            "status": "ACTIVE", "decision": "KEEP", "kpi_retain": 0.6,
            "summary": "", "keywords": "", "category_path": "",
            "org_id": "org_c", "created_at": None, "updated_at": None,
        })
        await store.upsert_document({
            "id": "doc_c2", "title": "ARCHIVED文档", "source_system": "wecom",
            "doc_type": "通知公告", "version_id": None,
            "status": "ARCHIVED", "decision": "ARCHIVE", "kpi_retain": 0.3,
            "summary": "", "keywords": "", "category_path": "",
            "org_id": "org_c", "created_at": None, "updated_at": None,
        })

        # org_id + status 组合过滤
        active_c = await store.list_documents(org_id="org_c", status="ACTIVE")
        assert len(active_c) == 1
        assert active_c[0]["id"] == "doc_c1"


@pytest.mark.asyncio
class TestVectorStoreOrgId:
    """VectorStore 按 org_id 过滤测试。"""

    async def test_memory_search_filter_by_org_id(self):
        store = VectorStore(use_memory=True)
        await store.initialize()

        embedding = [0.1] * 1536

        chunks = [
            KnowledgeChunk(
                chunk_id="c_a1", doc_id="doc_a1", chunk_index=0,
                content="企业A的内容", embedding=embedding, org_id="org_a",
            ),
            KnowledgeChunk(
                chunk_id="c_b1", doc_id="doc_b1", chunk_index=0,
                content="企业B的内容", embedding=embedding, org_id="org_b",
            ),
            KnowledgeChunk(
                chunk_id="c_a2", doc_id="doc_a2", chunk_index=0,
                content="企业A的另一段内容", embedding=embedding, org_id="org_a",
            ),
        ]
        await store.insert_chunks(chunks)

        # 按 org_a 搜索
        results_a = await store.search(query_embedding=embedding, top_k=10, org_id="org_a")
        assert len(results_a) == 2
        assert all(r["doc_id"].startswith("doc_a") for r in results_a)

        # 按 org_b 搜索
        results_b = await store.search(query_embedding=embedding, top_k=10, org_id="org_b")
        assert len(results_b) == 1
        assert results_b[0]["doc_id"] == "doc_b1"

        # 不传 org_id 返回全部
        results_all = await store.search(query_embedding=embedding, top_k=10)
        assert len(results_all) == 3


class TestChunkerOrgId:
    """Chunker 传递 org_id 测试。"""

    def test_chunk_document_passes_org_id(self):
        chunks = chunk_document(
            doc_id="test_doc",
            content="这是一段足够长的测试文本内容，用于验证分片器能正确传递组织ID参数。" * 5,
            org_id="org_enterprise",
        )
        assert len(chunks) > 0
        for chunk in chunks:
            assert chunk.org_id == "org_enterprise"

    def test_chunk_document_default_org_id(self):
        chunks = chunk_document(
            doc_id="test_doc",
            content="这是一段足够长的测试文本内容。" * 5,
        )
        assert len(chunks) > 0
        for chunk in chunks:
            assert chunk.org_id == "default"
