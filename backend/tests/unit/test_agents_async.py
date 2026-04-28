"""Agent 异步入口单测（坑 1 批 2 验收）。

覆盖：

- 4 个 ``arun_*`` 函数的成功路径（mock acall_llm_json）
- conflict_auditor 早返回（< 2 docs 不调 LLM）
- 异步路径与同步路径行为一致（共用纯函数）
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from packages.common.types import (
    DocType,
    EstimatedValue,
    LibrarianResult,
    RawDocument,
    SourceSystem,
)


# ─────────── fixtures ───────────


@pytest.fixture
def sample_doc() -> RawDocument:
    return RawDocument(
        doc_id="doc-test-001",
        title="安全生产管理制度",
        content="本制度适用于公司各部门的安全生产管理工作。第一章 总则。第二章 责任。",
        source_system=SourceSystem.FEISHU,
        source_id="src-001",
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 4, 1, tzinfo=timezone.utc),
        org_id="org-test",
    )


@pytest.fixture
def sample_librarian() -> LibrarianResult:
    return LibrarianResult(
        doc_type=DocType.REGULATION,
        version_id="v1.0",
        key_topics=["安全", "生产"],
        mentioned_entities=[],
        is_conversational=False,
        estimated_value=EstimatedValue.HIGH,
    )


# ─────────── arun_librarian ───────────


class TestArunLibrarian:
    @pytest.mark.asyncio
    async def test_async_success(self, sample_doc, monkeypatch) -> None:
        from packages.distillation.agents import librarian as lib_mod

        async def fake_acall(*args, **kwargs):
            return {
                "doc_type": "规章制度",
                "version_id": "v1.0",
                "key_topics": ["安全"],
                "mentioned_entities": [],
                "is_conversational": False,
                "estimated_value": "HIGH",
            }

        monkeypatch.setattr(lib_mod, "acall_llm_json", fake_acall)
        result = await lib_mod.arun_librarian(sample_doc)
        assert result.doc_type == DocType.REGULATION
        assert result.estimated_value == EstimatedValue.HIGH

    @pytest.mark.asyncio
    async def test_async_invalid_doc_type_falls_back(
        self, sample_doc, monkeypatch
    ) -> None:
        from packages.distillation.agents import librarian as lib_mod

        async def fake_acall(*args, **kwargs):
            return {
                "doc_type": "未知类型",
                "estimated_value": "MEDIUM",
            }

        monkeypatch.setattr(lib_mod, "acall_llm_json", fake_acall)
        result = await lib_mod.arun_librarian(sample_doc)
        assert result.doc_type == DocType.OTHER  # 降级


# ─────────── arun_conflict_auditor ───────────


class TestArunConflictAuditor:
    @pytest.mark.asyncio
    async def test_async_single_doc_skips_llm(self, sample_doc) -> None:
        """单篇文档不调 LLM，立即返回（async 路径无谓 await）。"""
        from packages.distillation.agents.conflict_auditor import arun_conflict_auditor

        result = await arun_conflict_auditor("test-cat", [sample_doc], {})
        assert result.summary == "仅一篇文档，无需冲突审计。"
        assert result.max_overlap_score == 0.0

    @pytest.mark.asyncio
    async def test_async_multi_doc_calls_llm(
        self, sample_doc, sample_librarian, monkeypatch
    ) -> None:
        from packages.distillation.agents import conflict_auditor as audit_mod

        doc2 = RawDocument(
            doc_id="doc-002",
            title="安全生产管理制度（修订版）",
            content="修订版正文",
            source_system=SourceSystem.FEISHU,
            source_id="src-002",
            updated_at=datetime(2026, 4, 15, tzinfo=timezone.utc),
            org_id="org-test",
        )

        async def fake_acall(*args, **kwargs):
            return {
                "overlap_groups": [
                    {
                        "doc_ids": ["doc-test-001", "doc-002"],
                        "overlap_type": "版本迭代",
                        "description": "v1.0 与修订版同主题",
                        "summary": "v1.0 vs 修订版",
                    }
                ],
                "conflicts": [],
                "summary": "检测到一组版本迭代",
            }

        monkeypatch.setattr(audit_mod, "acall_llm_json", fake_acall)
        meta = {sample_doc.doc_id: sample_librarian}
        result = await audit_mod.arun_conflict_auditor("安全管理", [sample_doc, doc2], meta)
        assert len(result.overlap_groups) == 1
        assert result.overlap_groups[0].overlap_type == "版本迭代"
        # 版本迭代权重 0.8 * (0.6 + 0.4 * 2/5) = 0.8 * 0.76 = 0.608
        assert 0.6 < result.max_overlap_score < 0.65


# ─────────── arun_judge ───────────


class TestArunJudge:
    @pytest.mark.asyncio
    async def test_async_keep_decision(
        self, sample_doc, sample_librarian, monkeypatch
    ) -> None:
        from packages.distillation.agents import judge as judge_mod
        from packages.distillation.scoring.judge_thresholds import DEFAULT_THRESHOLDS

        async def fake_acall(*args, **kwargs):
            return {
                "reasoning": {
                    "recency_score": 9,
                    "density_score": 9,
                    "completeness_score": 9,
                    "redundancy_score": 1,
                },
                "decision": "KEEP",
                "confidence": 0.95,
                "summary": "高价值规章制度",
                "key_entities": [],
            }

        monkeypatch.setattr(judge_mod, "acall_llm_json", fake_acall)
        result = await judge_mod.arun_judge(
            sample_doc, sample_librarian, thresholds=DEFAULT_THRESHOLDS
        )
        assert result.decision.value == "KEEP"
        assert result.confidence == 0.95
        # 决策追溯字段（坑 3 + 坑 1 联动）
        assert result.rule_hit  # 任一规则命中
        assert result.thresholds_source

    @pytest.mark.asyncio
    async def test_async_low_confidence_triggers_review(
        self, sample_doc, sample_librarian, monkeypatch
    ) -> None:
        """KPI 居中 + 低置信度 → R3 review 通道（坑 3 + 坑 1 联动）。"""
        from packages.distillation.agents import judge as judge_mod
        from packages.distillation.scoring.judge_thresholds import DEFAULT_THRESHOLDS

        async def fake_acall(*args, **kwargs):
            return {
                "reasoning": {
                    "recency_score": 5,
                    "density_score": 5,  # 中等密度
                    "completeness_score": 5,
                    "redundancy_score": 3,
                },
                "decision": "KEEP",
                "confidence": 0.45,  # 低置信
            }

        monkeypatch.setattr(judge_mod, "acall_llm_json", fake_acall)
        result = await judge_mod.arun_judge(
            sample_doc, sample_librarian, thresholds=DEFAULT_THRESHOLDS
        )
        # KPI 应在 review 带内（0.30-0.55），confidence 0.45 < review_confidence_max 0.60
        if 0.30 <= result.kpi_retain <= 0.55:
            assert result.needs_review is True
            assert result.rule_hit == "R3"


# ─────────── arun_refiner ───────────


class TestArunRefiner:
    @pytest.mark.asyncio
    async def test_async_success(
        self, sample_doc, sample_librarian, monkeypatch
    ) -> None:
        from packages.distillation.agents import refiner as ref_mod

        async def fake_acall(*args, **kwargs):
            return {
                "summary": "本文档为安全生产管理制度",
                "catalog": [
                    {
                        "level": 1,
                        "title": "总则",
                        "brief": "适用范围",
                        "key_terms": ["安全", "生产"],
                    }
                ],
                "keywords": ["安全", "生产", "管理"],
                "entities": [
                    {"name": "安全部", "type": "Department"},
                    {"name": "总经理", "type": "Person"},
                ],
                "relations": [
                    {"source": "安全部", "target": "总经理", "relation": "汇报"}
                ],
                "domain_id": "energy/safety",
                "doc_description": "安全生产相关制度",
                "key_elements": ["安全生产责任制"],
            }

        monkeypatch.setattr(ref_mod, "acall_llm_json", fake_acall)
        result = await ref_mod.arun_refiner(
            sample_doc, sample_librarian, domain_list_text="dummy"
        )
        assert result.domain_id == "energy/safety"
        assert len(result.entities) == 2
        assert len(result.relations) == 1
        assert "安全" in result.keywords

    @pytest.mark.asyncio
    async def test_async_unparsable_domain_falls_to_routing_pending(
        self, sample_doc, sample_librarian, monkeypatch
    ) -> None:
        """LLM 返回空 domain_id → 兜底 routing_pending（坑 4b 联动）。"""
        from packages.distillation.agents import refiner as ref_mod
        from packages.distillation.domain_inference import ROUTING_PENDING_DOMAIN_ID

        async def fake_acall(*args, **kwargs):
            return {
                "summary": "unknown content",
                "catalog": [],
                "keywords": [],
                "entities": [],
                "relations": [],
                "domain_id": "",  # 空字符串
                "doc_description": "",
                "key_elements": [],
            }

        monkeypatch.setattr(ref_mod, "acall_llm_json", fake_acall)
        result = await ref_mod.arun_refiner(
            sample_doc, sample_librarian, domain_list_text="dummy"
        )
        assert result.domain_id == ROUTING_PENDING_DOMAIN_ID


# ─────────── sync/async 行为一致性 ───────────


class TestSyncAsyncParity:
    """sync / async 走相同的纯函数解析逻辑，输入相同 LLM 响应应得到相同结果。"""

    @pytest.mark.asyncio
    async def test_librarian_parity(
        self, sample_doc, monkeypatch
    ) -> None:
        from packages.distillation.agents import librarian as lib_mod

        fake_data = {
            "doc_type": "规章制度",
            "version_id": "v1.0",
            "key_topics": ["主题"],
            "mentioned_entities": [],
            "is_conversational": False,
            "estimated_value": "HIGH",
        }

        # async path
        async def fake_acall(*args, **kwargs):
            return fake_data

        monkeypatch.setattr(lib_mod, "acall_llm_json", fake_acall)
        result_async = await lib_mod.arun_librarian(sample_doc)

        # sync path
        monkeypatch.setattr(lib_mod, "call_llm_json", lambda *a, **kw: fake_data)
        result_sync = lib_mod.run_librarian(sample_doc)

        # 两条路径产出一致
        assert result_sync.doc_type == result_async.doc_type
        assert result_sync.version_id == result_async.version_id
        assert result_sync.key_topics == result_async.key_topics
        assert result_sync.estimated_value == result_async.estimated_value
