"""M1 ISS 集成 · 批 2-4 · DataScope 5 级 + RemoteClient + retriever 集成。"""

from __future__ import annotations

import pytest
import respx
import httpx

from packages.auth import iss_remote_client
from packages.auth.data_scope import (
    DATA_SCOPE_ALL,
    DATA_SCOPE_CUSTOM,
    DATA_SCOPE_DEPT,
    DATA_SCOPE_DEPT_AND_CHILD,
    DATA_SCOPE_SELF,
    build_milvus_expr,
    matches,
)
from packages.common.auth import UserContext
from packages.common import settings


@pytest.fixture(autouse=True)
def _reset_dept_cache():
    iss_remote_client.reset_dept_cache_for_test()
    yield
    iss_remote_client.reset_dept_cache_for_test()


# ──────── build_milvus_expr ────────


class TestBuildMilvusExpr:
    async def test_all_returns_empty(self) -> None:
        u = UserContext(user_id="1", data_scope_level=DATA_SCOPE_ALL)
        assert await build_milvus_expr(u) == ""

    async def test_dept_returns_eq_expr(self) -> None:
        u = UserContext(user_id="1", data_scope_level=DATA_SCOPE_DEPT, dept_id=100)
        assert await build_milvus_expr(u) == "dept_id == 100"

    async def test_dept_without_dept_id_returns_never(self) -> None:
        u = UserContext(user_id="1", data_scope_level=DATA_SCOPE_DEPT, dept_id=None)
        assert "dept_id == -1" in await build_milvus_expr(u)

    async def test_self_returns_created_by_expr(self) -> None:
        u = UserContext(user_id="alice", data_scope_level=DATA_SCOPE_SELF)
        assert await build_milvus_expr(u) == 'created_by == "alice"'

    async def test_self_anonymous_returns_never(self) -> None:
        u = UserContext(user_id="anonymous", data_scope_level=DATA_SCOPE_SELF)
        assert "dept_id == -1" in await build_milvus_expr(u)

    async def test_custom_with_ids(self) -> None:
        u = UserContext(
            user_id="1", data_scope_level=DATA_SCOPE_CUSTOM, custom_dept_ids=[10, 20, 30],
        )
        assert await build_milvus_expr(u) == "dept_id in [10,20,30]"

    async def test_custom_empty_returns_never(self) -> None:
        u = UserContext(user_id="1", data_scope_level=DATA_SCOPE_CUSTOM, custom_dept_ids=[])
        assert "dept_id == -1" in await build_milvus_expr(u)

    @respx.mock
    async def test_dept_and_child_calls_remote(self, monkeypatch) -> None:
        monkeypatch.setattr(settings, "iss_system_base_url", "http://iss-system:9201")
        respx.get("http://iss-system:9201/system/dept/list").mock(
            return_value=httpx.Response(
                200, json={"code": 200, "data": [{"deptId": 101}, {"deptId": 102}]},
            )
        )
        u = UserContext(user_id="1", data_scope_level=DATA_SCOPE_DEPT_AND_CHILD, dept_id=100)
        expr = await build_milvus_expr(u)
        # 包含自己 + 子部门
        assert "dept_id in [" in expr
        assert "100" in expr and "101" in expr and "102" in expr


# ──────── matches ────────


class TestMatches:
    async def test_all_passes_anything(self) -> None:
        u = UserContext(user_id="1", data_scope_level=DATA_SCOPE_ALL)
        assert await matches(u, doc_dept_id=None, doc_owner_id=None) is True
        assert await matches(u, doc_dept_id=999, doc_owner_id="someone") is True

    async def test_dept_matches_same(self) -> None:
        u = UserContext(user_id="1", data_scope_level=DATA_SCOPE_DEPT, dept_id=100)
        assert await matches(u, doc_dept_id=100, doc_owner_id=None) is True
        assert await matches(u, doc_dept_id=200, doc_owner_id=None) is False

    async def test_dept_rejects_when_doc_dept_missing(self) -> None:
        u = UserContext(user_id="1", data_scope_level=DATA_SCOPE_DEPT, dept_id=100)
        assert await matches(u, doc_dept_id=None, doc_owner_id=None) is False

    async def test_self_matches_owner(self) -> None:
        u = UserContext(user_id="alice", data_scope_level=DATA_SCOPE_SELF)
        assert await matches(u, doc_dept_id=None, doc_owner_id="alice") is True
        assert await matches(u, doc_dept_id=None, doc_owner_id="bob") is False

    async def test_custom_in_list(self) -> None:
        u = UserContext(
            user_id="1", data_scope_level=DATA_SCOPE_CUSTOM, custom_dept_ids=[10, 20],
        )
        assert await matches(u, doc_dept_id=10, doc_owner_id=None) is True
        assert await matches(u, doc_dept_id=30, doc_owner_id=None) is False


# ──────── ISS Remote Client ────────


class TestRemoteClient:
    async def test_unset_base_url_returns_self_only(self, monkeypatch) -> None:
        monkeypatch.setattr(settings, "iss_system_base_url", "")
        result = await iss_remote_client.fetch_dept_descendants(100)
        assert result == [100]

    @respx.mock
    async def test_fetch_includes_self_and_descendants(self, monkeypatch) -> None:
        monkeypatch.setattr(settings, "iss_system_base_url", "http://iss-system:9201")
        respx.get("http://iss-system:9201/system/dept/list").mock(
            return_value=httpx.Response(
                200,
                json={"code": 200, "data": [
                    {"deptId": 101}, {"deptId": 102}, {"deptId": 103},
                ]},
            )
        )
        result = await iss_remote_client.fetch_dept_descendants(100)
        assert 100 in result
        assert {101, 102, 103}.issubset(set(result))

    @respx.mock
    async def test_network_error_falls_back_to_self(self, monkeypatch) -> None:
        monkeypatch.setattr(settings, "iss_system_base_url", "http://iss-system:9201")
        respx.get("http://iss-system:9201/system/dept/list").mock(
            side_effect=httpx.ConnectError("connection refused")
        )
        result = await iss_remote_client.fetch_dept_descendants(100)
        assert result == [100]

    @respx.mock
    async def test_cache_avoids_second_call(self, monkeypatch) -> None:
        monkeypatch.setattr(settings, "iss_system_base_url", "http://iss-system:9201")
        route = respx.get("http://iss-system:9201/system/dept/list").mock(
            return_value=httpx.Response(200, json={"data": [{"deptId": 101}]}),
        )
        await iss_remote_client.fetch_dept_descendants(100)
        await iss_remote_client.fetch_dept_descendants(100)
        assert route.call_count == 1  # 第二次走缓存


# ──────── Retriever 集成（最小用例）────────


class TestRetrieverDataScopeIntegration:
    """retriever.search 接收 user 参数后能正确按 DataScope 后过滤。

    用 Mock 形式构造 vector_store + metadata_store，验证 RBAC 循环里 DataScope 注入逻辑。
    """

    async def test_anonymous_user_no_data_scope_filter(self) -> None:
        """不传 user → DataScope 不生效，行为同 M0。"""
        from unittest.mock import AsyncMock

        from packages.retrieval.retriever import BookwormRetriever

        mock_vs = AsyncMock()
        mock_vs.search.return_value = [
            {"doc_id": "d1", "score": 0.9, "chunk_id": "c1", "content": "x"},
        ]
        mock_meta = AsyncMock()
        mock_meta.get_document.return_value = {
            "doc_id": "d1", "title": "t", "access_level": "INTERNAL", "dept_id": 999,
        }
        mock_graph = AsyncMock()
        mock_graph.get_doc_entities.return_value = []
        mock_graph._edges = []

        retriever = BookwormRetriever(
            vector_store=mock_vs,
            graph_store=mock_graph,
            metadata_store=mock_meta,
            keyword_scorer=None,
            reranker=None,
            cache=None,
        )
        results = await retriever.search(query="hello", top_k=5)
        # 不传 user，DataScope 不生效，结果应保留
        assert len(results) == 1

    async def test_self_scope_filters_other_user_docs(self) -> None:
        from unittest.mock import AsyncMock

        from packages.retrieval.retriever import BookwormRetriever

        mock_vs = AsyncMock()
        mock_vs.search.return_value = [
            {"doc_id": "d1", "score": 0.9, "chunk_id": "c1", "content": "x"},
            {"doc_id": "d2", "score": 0.85, "chunk_id": "c2", "content": "y"},
        ]
        mock_meta = AsyncMock()

        async def _get_doc(doc_id):
            return {
                "d1": {"doc_id": "d1", "access_level": "INTERNAL", "created_by": "alice"},
                "d2": {"doc_id": "d2", "access_level": "INTERNAL", "created_by": "bob"},
            }[doc_id]

        mock_meta.get_document.side_effect = _get_doc

        mock_graph = AsyncMock()
        mock_graph.get_doc_entities.return_value = []
        mock_graph._edges = []

        retriever = BookwormRetriever(
            vector_store=mock_vs,
            graph_store=mock_graph,
            metadata_store=mock_meta,
            keyword_scorer=None,
            reranker=None,
            cache=None,
        )
        alice = UserContext(
            user_id="alice", data_scope_level=DATA_SCOPE_SELF, source="jwt",
        )
        results = await retriever.search(query="hello", top_k=5, user=alice)
        # alice SELF 范围 → 只看到 d1（她创建的）
        assert len(results) == 1
        assert results[0].doc_id == "d1"
