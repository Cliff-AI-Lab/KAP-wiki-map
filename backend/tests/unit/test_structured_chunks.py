"""M22 #4 · ISS 解析结果 bypass 入口单测。

覆盖：
- StructuredChunksRequest schema 校验（必填字段 / content_type / 边界长度）
- POST /knowledge/structured-chunks 完整入库链路（happy path）
- 非法 content_type 返回 400
- 审计落库 + chunks_stored 数对得上
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from api.schemas.knowledge import (
    StructuredChunkInput,
    StructuredChunksRequest,
    _ALLOWED_CONTENT_TYPES,
)


# ────────── Schema 校验 ──────────


class TestSchemaValidation:
    def test_content_type_set_matches_chunk_strategy(self):
        # 与 M22 #2 ChunkStrategy 枚举对齐
        assert _ALLOWED_CONTENT_TYPES == {
            "text", "table_row", "equation", "image_caption",
        }

    def test_minimal_request(self):
        req = StructuredChunksRequest(
            doc_id="d1",
            parser_name="ABBYY-15",
            chunks=[StructuredChunkInput(content="hello")],
        )
        assert req.doc_id == "d1"
        assert req.parser_name == "ABBYY-15"
        assert len(req.chunks) == 1
        assert req.chunks[0].content_type == "text"
        assert req.project_id == "default"
        assert req.access_level == "INTERNAL"

    def test_empty_chunks_rejected(self):
        with pytest.raises(Exception):  # pydantic ValidationError
            StructuredChunksRequest(
                doc_id="d1",
                parser_name="P",
                chunks=[],
            )

    def test_missing_parser_name_rejected(self):
        with pytest.raises(Exception):
            StructuredChunksRequest(
                doc_id="d1",
                parser_name="",  # min_length=1
                chunks=[StructuredChunkInput(content="x")],
            )

    def test_chunk_content_max_length(self):
        # 20000 上限
        StructuredChunksRequest(
            doc_id="d1",
            parser_name="P",
            chunks=[StructuredChunkInput(content="a" * 20000)],
        )
        with pytest.raises(Exception):
            StructuredChunksRequest(
                doc_id="d1",
                parser_name="P",
                chunks=[StructuredChunkInput(content="a" * 20001)],
            )


# ────────── 端点集成 ──────────


@pytest.fixture
def app_with_mocks(monkeypatch):
    """构造带 mock dep override 的 app。

    knowledge.py 用模块级 get_xxx() 直接调（不是 FastAPI Depends），
    所以 dependency_overrides 拦不住, 必须 monkeypatch 模块函数。
    """
    from api import deps as deps_mod
    from api.middleware import auth as auth_mod
    from api.routers import knowledge as knowledge_mod
    from packages.common.audit import AuditEntry

    # mock 实例
    vec = MagicMock()
    vec.insert_chunks = AsyncMock(return_value=None)
    raw = MagicMock()
    raw.save_raw = AsyncMock(return_value=None)
    meta = MagicMock()
    meta.upsert_document = AsyncMock(return_value=None)
    dom = MagicMock()
    audit_calls: list[AuditEntry] = []
    audit = MagicMock()

    async def _capture(entry: AuditEntry):
        audit_calls.append(entry)

    audit.log = AsyncMock(side_effect=_capture)

    # mock embedder.aembed_texts
    async def _fake_aembed_texts(texts: list[str]) -> list[list[float]]:
        return [[0.1, 0.2, 0.3] for _ in texts]

    monkeypatch.setattr("packages.storage.embedder.aembed_texts",
                        _fake_aembed_texts)

    # mock api.deps.* 模块级 getter（knowledge.py 直接 import 后调用）
    monkeypatch.setattr(knowledge_mod, "get_vector_store", lambda: vec)
    monkeypatch.setattr(knowledge_mod, "get_metadata_store", lambda: meta)
    monkeypatch.setattr(knowledge_mod, "get_audit_logger", lambda: audit)
    monkeypatch.setattr(knowledge_mod, "get_domain_store", lambda: dom)
    monkeypatch.setattr(deps_mod, "get_raw_store", lambda: raw)
    # bypass 路由内部 from api.deps import get_raw_store, 也走 deps_mod 的 mock

    # mock current_user（knowledge_mod 已 import get_current_user）
    fake_user = MagicMock(
        user_id="u1", org_id="org1", dept_id="d1",
        access_level="INTERNAL",
    )
    monkeypatch.setattr(knowledge_mod, "get_current_user", lambda req: fake_user)
    monkeypatch.setattr(auth_mod, "get_current_user", lambda req: fake_user)

    from api.routers.knowledge import router
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")

    return app, vec, raw, meta, audit, audit_calls


class TestStructuredChunksEndpoint:
    def test_happy_path(self, app_with_mocks):
        app, vec, raw, meta, audit, audit_calls = app_with_mocks
        client = TestClient(app)
        body = {
            "doc_id": "ext_001",
            "doc_title": "外部解析的报告",
            "project_id": "proj_a",
            "parser_name": "ABBYY-FineReader-15",
            "source_system": "abbyy",
            "doc_type": "report",
            "category_path": "/制造/工艺",
            "chunks": [
                {"content": "第一段文本", "content_type": "text"},
                {"content": "设备=A1 | 厂家=甲", "content_type": "table_row"},
                {"content": "公式 $$E=mc^2$$", "content_type": "equation"},
            ],
        }
        r = client.post("/api/v1/knowledge/structured-chunks", json=body)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["status"] == "ok"
        assert data["doc_id"] == "ext_001"
        assert data["chunks_stored"] == 3
        assert data["parser_name"] == "ABBYY-FineReader-15"
        assert data["audit_logged"] is True

        # vec.insert_chunks 被调一次, 入参是 3 个 KnowledgeChunk
        vec.insert_chunks.assert_awaited_once()
        chunks_arg = vec.insert_chunks.await_args.args[0]
        assert len(chunks_arg) == 3
        # chunk_strategy 映射对：text → fixed, table_row → table_row, equation → equation
        strategies = [c.chunk_strategy for c in chunks_arg]
        assert "fixed" in strategies
        assert "table_row" in strategies
        assert "equation" in strategies

        # raw_store + meta_store + audit 都被调
        raw.save_raw.assert_awaited_once()
        meta.upsert_document.assert_awaited_once()
        audit.log.assert_awaited_once()

        # 审计 details 含 parser_name + via
        assert len(audit_calls) == 1
        details = audit_calls[0].details
        assert details["parser_name"] == "ABBYY-FineReader-15"
        assert details["via"] == "structured_chunks"
        assert details["chunk_count"] == 3
        assert details["content_types"]["text"] == 1
        assert details["content_types"]["table_row"] == 1
        assert details["content_types"]["equation"] == 1

    def test_invalid_content_type_returns_400(self, app_with_mocks):
        app, *_ = app_with_mocks
        client = TestClient(app)
        body = {
            "doc_id": "ext_002",
            "parser_name": "P",
            "chunks": [
                {"content": "x", "content_type": "magic_unknown_type"},
            ],
        }
        r = client.post("/api/v1/knowledge/structured-chunks", json=body)
        assert r.status_code == 400
        assert "magic_unknown_type" in r.text or "content_type" in r.text

    def test_empty_chunks_rejected_by_schema(self, app_with_mocks):
        app, *_ = app_with_mocks
        client = TestClient(app)
        body = {
            "doc_id": "ext_003",
            "parser_name": "P",
            "chunks": [],
        }
        r = client.post("/api/v1/knowledge/structured-chunks", json=body)
        assert r.status_code == 422  # pydantic ValidationError
