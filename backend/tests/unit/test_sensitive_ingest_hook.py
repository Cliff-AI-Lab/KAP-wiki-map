"""M2 #2 · W1 脱敏 ingest hook 单测。"""

from __future__ import annotations

from datetime import datetime

import pytest

from packages.common.types import RawDocument, SourceSystem
from packages.sensitive.ingest_hook import (
    collect_token_summary,
    redact_and_persist_doc,
)
from packages.sensitive.mapping_store import SensitiveMappingStore


_TEST_KEY = bytes.fromhex("a" * 64)


@pytest.fixture
async def mstore():
    s = SensitiveMappingStore(aes_key=_TEST_KEY)
    await s.initialize()
    return s


def _make_doc(content: str, doc_id: str = "d1") -> RawDocument:
    return RawDocument(
        doc_id=doc_id,
        title="测试文档",
        content=content,
        source_system=SourceSystem.LOCAL,
        source_id="local-1",
        org_id="default",
        created_at=datetime(2026, 1, 1),
        updated_at=datetime(2026, 4, 1),
    )


# ════════════════════════════════════════════════════════════════════════
#  redact_and_persist_doc
# ════════════════════════════════════════════════════════════════════════


class TestRedactPersistDoc:
    async def test_inplace_replaces_content(self, mstore) -> None:
        doc = _make_doc("张工负责本项目，温度 80℃")
        result = await redact_and_persist_doc(doc, mapping_store=mstore)
        assert "张工" not in doc.content
        assert "工程师A" in doc.content
        assert len(result.tokens) >= 2  # 张工 + 80℃

    async def test_persists_mapping_to_store(self, mstore) -> None:
        doc = _make_doc("张工负责")
        result = await redact_and_persist_doc(doc, mapping_store=mstore)
        # mapping_id 可在 store 中查到原文
        for tok in result.tokens:
            data = await mstore.get(tok.mapping_id)
            assert data is not None
            assert data["original"] == tok.original

    async def test_metadata_records_token_ids(self, mstore) -> None:
        doc = _make_doc("张工和李总一起开会")
        await redact_and_persist_doc(doc, mapping_store=mstore)
        token_ids = doc.metadata.get("redaction_token_ids", [])
        # 张工 + 李总 → 2 个 token id
        assert len(token_ids) >= 2
        assert doc.metadata.get("redaction_count") == len(token_ids)

    async def test_no_sensitive_skipped(self, mstore) -> None:
        """无敏感字段的文档不修改 content + 不存映射。"""
        doc = _make_doc("这是一段普通描述无任何敏感信息")
        original_content = doc.content
        result = await redact_and_persist_doc(doc, mapping_store=mstore)
        assert doc.content == original_content
        assert result.tokens == []

    async def test_persist_disabled_skips_store(self, mstore) -> None:
        """persist_mapping=False 时仍脱敏但不写映射（dev / 不可逆）。"""
        doc = _make_doc("张工")
        result = await redact_and_persist_doc(
            doc, mapping_store=mstore, persist_mapping=False,
        )
        assert "张工" not in doc.content
        # store 不应有任何记录
        assert result.tokens
        assert not await mstore.has(result.tokens[0].mapping_id)

    async def test_empty_content_safe(self, mstore) -> None:
        doc = _make_doc("")
        result = await redact_and_persist_doc(doc, mapping_store=mstore)
        assert result.redacted_text == ""
        assert result.tokens == []

    async def test_cross_doc_consistency(self, mstore) -> None:
        """同一原文在两份文档里 → 同一 mapping_id（跨文档一致 §5.4）。"""
        doc_a = _make_doc("张工提交了报告", doc_id="A")
        doc_b = _make_doc("张工还在加班", doc_id="B")
        ra = await redact_and_persist_doc(doc_a, mapping_store=mstore)
        rb = await redact_and_persist_doc(doc_b, mapping_store=mstore)

        # 两份文档都生成 张工 → 工程师A 的 token
        zhang_a = next(t for t in ra.tokens if t.original == "张工")
        zhang_b = next(t for t in rb.tokens if t.original == "张工")
        assert zhang_a.mapping_id == zhang_b.mapping_id


# ════════════════════════════════════════════════════════════════════════
#  collect_token_summary
# ════════════════════════════════════════════════════════════════════════


class TestTokenSummary:
    async def test_categorizes_by_type(self, mstore) -> None:
        doc = _make_doc("张工和李总，温度 100℃，压力 2 MPa")
        result = await redact_and_persist_doc(doc, mapping_store=mstore)
        summary = collect_token_summary(result.tokens)
        assert summary["total"] == len(result.tokens)
        # 至少应该有 PERSON_NAME 和 PROCESS_PARAM 两类
        assert "PERSON_NAME" in summary["by_category"]
        assert "PROCESS_PARAM" in summary["by_category"]
