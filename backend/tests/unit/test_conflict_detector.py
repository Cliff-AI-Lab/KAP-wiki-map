"""M3 #3d 块① · 冲突检测预演单测（PRD F1.6）。"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from packages.architect.conflict_detector import (
    DocSample,
    _fallback_keyword_classify,
    _normalize_title,
    classify_doc,
    detect_duplicates,
    preview_classification,
)
from packages.templates.registry import TaxonomyNode


def _taxonomy() -> list[TaxonomyNode]:
    return [
        TaxonomyNode(id="production", name="生产管理", level=2,
                     description="生产计划工艺控制"),
        TaxonomyNode(id="quality", name="质量管理", level=2,
                     description="检验 IQC IPQC OQC"),
        TaxonomyNode(id="equipment", name="设备管理", level=2,
                     description="设备维护点检"),
    ]


# ════════════════════════════════════════════════════════════════════════
#  classify_doc
# ════════════════════════════════════════════════════════════════════════


class TestClassifyDoc:
    async def test_normal_classify(self) -> None:
        async def fake_llm(system, user):
            return {
                "primary_node_id": "production",
                "primary_confidence": 0.9,
                "secondary_node_id": "",
                "secondary_confidence": 0.0,
                "unmatched": False,
                "reasoning": "工艺控制属生产管理",
            }
        with patch(
            "packages.architect.conflict_detector.acall_llm_json",
            side_effect=fake_llm,
        ):
            result = await classify_doc(
                DocSample(doc_id="d1", title="工艺控制规程"),
                _taxonomy(),
            )
        assert result.primary_node_id == "production"
        assert result.primary_confidence == 0.9
        assert result.unmatched is False

    async def test_unmatched_doc(self) -> None:
        async def fake_llm(system, user):
            return {
                "primary_node_id": "",
                "primary_confidence": 0.0,
                "unmatched": True,
                "reasoning": "无任何节点匹配",
            }
        with patch(
            "packages.architect.conflict_detector.acall_llm_json",
            side_effect=fake_llm,
        ):
            result = await classify_doc(
                DocSample(doc_id="d2", title="餐饮预订系统"),
                _taxonomy(),
            )
        assert result.unmatched is True
        assert result.primary_node_id == ""

    async def test_invalid_node_id_filtered(self) -> None:
        """LLM 返回不在主树的 node_id → 设为空。"""
        async def fake_llm(system, user):
            return {
                "primary_node_id": "fake_node",
                "primary_confidence": 0.9,
            }
        with patch(
            "packages.architect.conflict_detector.acall_llm_json",
            side_effect=fake_llm,
        ):
            result = await classify_doc(
                DocSample(doc_id="d3", title="t"), _taxonomy(),
            )
        assert result.primary_node_id == ""
        assert result.unmatched is True

    async def test_llm_failure_falls_back(self) -> None:
        """LLM 失败 → 关键词命中降级。"""
        with patch(
            "packages.architect.conflict_detector.acall_llm_json",
            side_effect=Exception("LLM down"),
        ):
            result = await classify_doc(
                DocSample(doc_id="d4", title="生产管理 工艺规程"),
                _taxonomy(),
            )
        # 关键词命中 → primary 不为空
        assert result.primary_node_id == "production"
        assert "降级" in result.reasoning


class TestKeywordFallback:
    def test_no_match_returns_unmatched(self) -> None:
        result = _fallback_keyword_classify(
            DocSample(doc_id="d", title="毫不相关的内容"), _taxonomy(),
        )
        assert result.unmatched is True

    def test_strong_match_high_confidence(self) -> None:
        result = _fallback_keyword_classify(
            DocSample(doc_id="d", title="设备管理 设备维护 点检规程"),
            _taxonomy(),
        )
        assert result.primary_node_id == "equipment"
        assert result.primary_confidence > 0


# ════════════════════════════════════════════════════════════════════════
#  detect_duplicates
# ════════════════════════════════════════════════════════════════════════


class TestDetectDuplicates:
    def test_normalized_match(self) -> None:
        docs = [
            DocSample(doc_id="a", title="设备维护规程 v1.0"),
            DocSample(doc_id="b", title="设备维护规程 v1.1"),
            DocSample(doc_id="c", title="完全不同的标题"),
        ]
        dups = detect_duplicates(docs)
        assert len(dups) == 1
        assert {dups[0].doc_id_a, dups[0].doc_id_b} == {"a", "b"}

    def test_no_duplicates(self) -> None:
        docs = [
            DocSample(doc_id="a", title="A 报告"),
            DocSample(doc_id="b", title="B 规范"),
        ]
        assert detect_duplicates(docs) == []

    def test_empty_safe(self) -> None:
        assert detect_duplicates([]) == []
        assert detect_duplicates([DocSample(doc_id="x", title="t")]) == []

    def test_normalize_title_strips_versions(self) -> None:
        norm = _normalize_title("设备 维 护 规 程 v1.2.3")
        assert "v" not in norm.lower() or "1" not in norm


# ════════════════════════════════════════════════════════════════════════
#  preview_classification — 完整报告
# ════════════════════════════════════════════════════════════════════════


class TestPreviewClassification:
    async def test_full_report(self) -> None:
        async def fake_llm(system, user):
            # 用 doc 唯一标题字符串匹配（避免与 taxonomy 描述串扰）
            if "工艺规程" in user:
                return {
                    "primary_node_id": "production",
                    "primary_confidence": 0.9,
                }
            if "检验作业指导" in user:
                return {
                    "primary_node_id": "quality",
                    "primary_confidence": 0.7,
                    "secondary_node_id": "production",
                    "secondary_confidence": 0.6,
                }
            return {
                "primary_node_id": "", "primary_confidence": 0,
                "unmatched": True,
            }

        with patch(
            "packages.architect.conflict_detector.acall_llm_json",
            side_effect=fake_llm,
        ):
            docs = [
                DocSample(doc_id="d1", title="工艺规程"),
                DocSample(doc_id="d2", title="检验作业指导（生产线相关）"),
                DocSample(doc_id="d3", title="毫不相关"),
            ]
            report = await preview_classification(docs, _taxonomy())

        assert report.total_docs == 3
        assert report.classified_docs == 2
        assert len(report.orphans) == 1
        assert len(report.conflicts) == 1   # d2 双归
        # 节点覆盖度
        assert report.node_coverage.get("production", 0) >= 1
        assert report.node_coverage.get("quality", 0) == 1

    async def test_no_taxonomy_all_orphan(self) -> None:
        docs = [DocSample(doc_id="d1", title="a"), DocSample(doc_id="d2", title="b")]
        report = await preview_classification(docs, [])
        assert len(report.orphans) == 2
        assert report.classified_docs == 0

    async def test_duplicates_in_report(self) -> None:
        async def fake_llm(system, user):
            return {
                "primary_node_id": "production",
                "primary_confidence": 0.9,
            }
        with patch(
            "packages.architect.conflict_detector.acall_llm_json",
            side_effect=fake_llm,
        ):
            docs = [
                DocSample(doc_id="a", title="设备维护规程 v1"),
                DocSample(doc_id="b", title="设备维护规程 v2"),
            ]
            report = await preview_classification(docs, _taxonomy())
        assert len(report.duplicates) == 1
