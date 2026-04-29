"""M1 W4 写入侧 · documents.dept_id / created_by 字段测试。

覆盖：
- metadata_store.upsert_document 正确存储 dept_id / created_by（内存模式）
- get_document 能取回这两个字段
- retriever DataScope 过滤在文档有字段时严格生效
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from packages.auth.data_scope import DATA_SCOPE_DEPT, DATA_SCOPE_SELF
from packages.common.auth import UserContext
from packages.retrieval.retriever import BookwormRetriever
from packages.storage.metadata_store import MetadataStore


@pytest.fixture
async def store():
    s = MetadataStore(use_memory=True)
    await s.initialize()
    return s


# ──────── upsert / get with new fields ────────


class TestUpsertDeptIdAndCreator:
    async def test_dept_id_int_stored(self, store) -> None:
        await store.upsert_document({
            "id": "d1",
            "title": "测试文档",
            "source_system": "local",
            "decision": "KEEP",
            "kpi_retain": 0.8,
            "dept_id": 100,
            "created_by": "alice",
        })
        d = await store.get_document("d1")
        assert d["dept_id"] == 100
        assert d["created_by"] == "alice"

    async def test_default_none_and_empty(self, store) -> None:
        """缺省字段不强制传 → dept_id=None / created_by=''。"""
        await store.upsert_document({
            "id": "d2",
            "title": "无字段文档",
            "source_system": "local",
            "decision": "KEEP",
            "kpi_retain": 0.5,
        })
        d = await store.get_document("d2")
        assert d["dept_id"] is None
        assert d["created_by"] == ""


# ──────── retriever 端到端 DataScope 激活 ────────


def _build_retriever(meta_docs: dict[str, dict]):
    """构造 retriever，向量返回所有 doc_id 对应 hit。"""
    mock_vs = AsyncMock()
    mock_vs.search.return_value = [
        {"doc_id": did, "score": 0.9, "chunk_id": f"c_{did}", "content": "x"}
        for did in meta_docs.keys()
    ]
    mock_meta = AsyncMock()

    async def _get_doc(doc_id):
        return meta_docs.get(doc_id)

    mock_meta.get_document.side_effect = _get_doc

    mock_graph = AsyncMock()
    mock_graph.get_doc_entities.return_value = []
    mock_graph._edges = []

    return BookwormRetriever(
        vector_store=mock_vs,
        graph_store=mock_graph,
        metadata_store=mock_meta,
        keyword_scorer=None,
        reranker=None,
        cache=None,
    )


class TestDataScopeActivation:
    async def test_dept_filter_excludes_other_dept(self) -> None:
        """W4 写入侧补 dept_id 后，DEPT 范围用户只能看本部门文档。"""
        retr = _build_retriever({
            "d1": {"doc_id": "d1", "access_level": "INTERNAL", "dept_id": 100, "created_by": "alice"},
            "d2": {"doc_id": "d2", "access_level": "INTERNAL", "dept_id": 200, "created_by": "bob"},
        })
        user = UserContext(
            user_id="alice", dept_id=100,
            data_scope_level=DATA_SCOPE_DEPT, source="jwt",
        )
        results = await retr.search("hello", top_k=5, user=user)
        ids = [r.doc_id for r in results]
        assert "d1" in ids
        assert "d2" not in ids

    async def test_self_filter_excludes_others_creations(self) -> None:
        retr = _build_retriever({
            "d1": {"doc_id": "d1", "access_level": "INTERNAL", "dept_id": 100, "created_by": "alice"},
            "d2": {"doc_id": "d2", "access_level": "INTERNAL", "dept_id": 100, "created_by": "bob"},
        })
        user = UserContext(
            user_id="alice", dept_id=100,
            data_scope_level=DATA_SCOPE_SELF, source="jwt",
        )
        results = await retr.search("hello", top_k=5, user=user)
        ids = [r.doc_id for r in results]
        assert ids == ["d1"]

    async def test_legacy_doc_without_fields_transparent(self) -> None:
        """V15 老文档无 dept_id / created_by → 透明放行（M0 兼容）。"""
        retr = _build_retriever({
            "old1": {"doc_id": "old1", "access_level": "INTERNAL"},
        })
        user = UserContext(
            user_id="alice", dept_id=100,
            data_scope_level=DATA_SCOPE_DEPT, source="jwt",
        )
        results = await retr.search("hello", top_k=5, user=user)
        # 旧文档无任何范围字段，DataScope 透明放行
        assert len(results) == 1
