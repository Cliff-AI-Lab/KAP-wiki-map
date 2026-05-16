"""M22 #3 · Context-Aware Chunking 单测。

覆盖：
- chunker.build_context_window 工具函数（窗口大小、目标排除、字符上限、缺失 id）
- entity_extractor 接受 context 参数并把它织入 prompt
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest

from packages.common.types import ChunkStrategy, KnowledgeChunk
from packages.storage.chunker import build_context_window


class _FakeEntityType:
    type_id = "E_DEVICE"
    type_name = "设备"
    examples: list[str] = []


def _fake_ontology_types() -> list[_FakeEntityType]:
    return [_FakeEntityType()]


def _mk_chunk(doc_id: str, idx: int, content: str) -> KnowledgeChunk:
    return KnowledgeChunk(
        chunk_id=f"{doc_id}_c{idx:04d}",
        doc_id=doc_id,
        chunk_index=idx,
        content=content,
        chunk_strategy=ChunkStrategy.FIXED.value,
        updated_at=datetime.utcnow(),
    )


class TestBuildContextWindow:
    def test_default_window_includes_neighbors(self):
        chunks = [_mk_chunk("d1", i, f"段落{i}") for i in range(5)]
        target = chunks[2].chunk_id
        ctx = build_context_window(chunks, target, window_size=1)
        # 应含 idx=1 (前文) 和 idx=3 (后文), 不含 idx=2 (target 自身)
        assert "段落1" in ctx
        assert "段落3" in ctx
        assert "段落2" not in ctx
        assert "前文" in ctx and "后文" in ctx

    def test_window_size_zero_returns_empty(self):
        chunks = [_mk_chunk("d1", i, f"x{i}") for i in range(3)]
        ctx = build_context_window(chunks, chunks[1].chunk_id, window_size=0)
        assert ctx == ""

    def test_missing_target_returns_empty(self):
        chunks = [_mk_chunk("d1", i, f"x{i}") for i in range(3)]
        ctx = build_context_window(chunks, "not_exist_chunk_id", window_size=1)
        assert ctx == ""

    def test_max_chars_truncates(self):
        # 制造大 context, 校验截断
        chunks = [_mk_chunk("d1", i, "A" * 1000) for i in range(5)]
        ctx = build_context_window(chunks, chunks[2].chunk_id,
                                   window_size=2, max_chars=500)
        assert len(ctx) <= 500 + len(" …(截断)")
        assert ctx.endswith(" …(截断)")

    def test_window_at_boundary_does_not_overshoot(self):
        # 目标在边界, 前文不够 N 个时也不应越界
        chunks = [_mk_chunk("d1", i, f"段落{i}") for i in range(3)]
        ctx_first = build_context_window(chunks, chunks[0].chunk_id, window_size=2)
        # 前文 0 个 + 后文最多 2 个
        assert "段落1" in ctx_first and "段落2" in ctx_first
        assert "段落0" not in ctx_first  # target 自己不在 context

        ctx_last = build_context_window(chunks, chunks[2].chunk_id, window_size=2)
        assert "段落0" in ctx_last and "段落1" in ctx_last
        assert "段落2" not in ctx_last


@pytest.mark.asyncio
class TestEntityExtractorWithContext:
    """entity_extractor 应把 context 织入 prompt 中。"""

    async def test_default_no_context_section(self, monkeypatch):
        """不传 context 时 prompt 不含"周边上下文"段, 与 M0-M21 行为一致。"""
        from packages.extraction import entity_extractor

        captured = {}

        async def _fake_llm(system: str, user: str, **kw):
            captured["user"] = user
            return {"entities": [], "relations": []}

        monkeypatch.setattr(entity_extractor, "acall_llm_json", _fake_llm)
        # bypass ontology 检查
        monkeypatch.setattr(
            entity_extractor, "_collect_ontology_types",
            lambda i, p: (_fake_ontology_types(), [], {"E_DEVICE"}, set(), {}),
        )

        await entity_extractor.extract_entities_and_relations(
            doc_id="d1",
            content="某设备故障",
            industry_code="energy",
        )
        assert "周边上下文" not in captured["user"]

    async def test_context_passed_into_prompt(self, monkeypatch):
        from packages.extraction import entity_extractor

        captured = {}

        async def _fake_llm(system: str, user: str, **kw):
            captured["user"] = user
            return {"entities": [], "relations": []}

        monkeypatch.setattr(entity_extractor, "acall_llm_json", _fake_llm)
        monkeypatch.setattr(
            entity_extractor, "_collect_ontology_types",
            lambda i, p: (_fake_ontology_types(), [], {"E_DEVICE"}, set(), {}),
        )

        await entity_extractor.extract_entities_and_relations(
            doc_id="d1",
            content="某设备",
            industry_code="energy",
            context="风电场 A 区第 3 号风机的运行数据采集表",
        )
        assert "周边上下文" in captured["user"]
        assert "风电场 A 区" in captured["user"]

    async def test_context_truncated_when_too_long(self, monkeypatch):
        from packages.extraction import entity_extractor

        captured = {}

        async def _fake_llm(system: str, user: str, **kw):
            captured["user"] = user
            return {"entities": [], "relations": []}

        monkeypatch.setattr(entity_extractor, "acall_llm_json", _fake_llm)
        monkeypatch.setattr(
            entity_extractor, "_collect_ontology_types",
            lambda i, p: (_fake_ontology_types(), [], {"E_DEVICE"}, set(), {}),
        )

        long_ctx = "上下文内容" * 1000
        await entity_extractor.extract_entities_and_relations(
            doc_id="d1",
            content="设备",
            industry_code="energy",
            context=long_ctx,
            context_chars_limit=300,
        )
        assert "…(截断)" in captured["user"]
