"""M3 #4 W4 LLM 实体抽取单测（决策书 §5.2）。"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from packages.extraction.entity_extractor import (
    _stable_entity_id,
    extract_entities_and_relations,
)
from packages.ontology import reset_registry_for_test


@pytest.fixture(autouse=True)
def _reset():
    reset_registry_for_test()
    yield
    reset_registry_for_test()


# ════════════════════════════════════════════════════════════════════════
#  _stable_entity_id
# ════════════════════════════════════════════════════════════════════════


class TestStableEntityId:
    def test_same_inputs_same_id(self) -> None:
        a = _stable_entity_id("d1", "汽轮机1#", "equipment")
        b = _stable_entity_id("d1", "汽轮机1#", "equipment")
        assert a == b

    def test_different_doc_different_id(self) -> None:
        a = _stable_entity_id("d1", "汽轮机1#", "equipment")
        b = _stable_entity_id("d2", "汽轮机1#", "equipment")
        assert a != b

    def test_id_has_ent_prefix(self) -> None:
        eid = _stable_entity_id("d1", "n", "t")
        assert eid.startswith("ent_")


# ════════════════════════════════════════════════════════════════════════
#  extract_entities_and_relations
# ════════════════════════════════════════════════════════════════════════


class TestExtraction:
    async def test_normal_extraction(self) -> None:
        async def fake_llm(system, user):
            return {
                "entities": [
                    {"name": "数控车床 CK6140", "type_id": "equipment",
                     "confidence": 0.9, "evidence": "数控车床 CK6140 工作"},
                    {"name": "车削工艺", "type_id": "process",
                     "confidence": 0.8, "evidence": "采用车削工艺"},
                ],
                "relations": [
                    {"source_name": "车削工艺", "target_name": "数控车床 CK6140",
                     "relation_type_id": "uses", "confidence": 0.85,
                     "evidence": "车削工艺使用数控车床"},
                ],
            }

        with patch(
            "packages.extraction.entity_extractor.acall_llm_json",
            side_effect=fake_llm,
        ):
            result = await extract_entities_and_relations(
                doc_id="d1",
                content="数控车床 CK6140 工作中，采用车削工艺加工零件。",
                industry_code="manufacturing",
            )

        assert len(result.entities) == 2
        assert len(result.relations) == 1
        # 实体类型 ID 都在本体注册集合内
        assert all(e.type_id in ("equipment", "process") for e in result.entities)
        # 关系约束生效
        rel = result.relations[0]
        assert rel.relation_type_id == "uses"

    async def test_invalid_type_id_filtered(self) -> None:
        """LLM 返回不在本体里的 type_id → 实体被丢弃。"""
        async def fake_llm(system, user):
            return {
                "entities": [
                    {"name": "X", "type_id": "valid_equipment", "confidence": 0.9},
                    {"name": "Y", "type_id": "fake_type", "confidence": 0.9},
                    {"name": "Z", "type_id": "equipment", "confidence": 0.9},
                ],
            }
        with patch(
            "packages.extraction.entity_extractor.acall_llm_json",
            side_effect=fake_llm,
        ):
            result = await extract_entities_and_relations(
                doc_id="d", content="...", industry_code="manufacturing",
            )
        # 只有 equipment 类型在本体里，valid_equipment 和 fake_type 被丢弃
        assert len(result.entities) == 1
        assert result.entities[0].type_id == "equipment"

    async def test_invalid_relation_type_filtered(self) -> None:
        async def fake_llm(system, user):
            return {
                "entities": [
                    {"name": "A", "type_id": "process"},
                    {"name": "B", "type_id": "equipment"},
                ],
                "relations": [
                    {"source_name": "A", "target_name": "B",
                     "relation_type_id": "fake_relation"},
                    {"source_name": "A", "target_name": "B",
                     "relation_type_id": "uses"},
                ],
            }
        with patch(
            "packages.extraction.entity_extractor.acall_llm_json",
            side_effect=fake_llm,
        ):
            result = await extract_entities_and_relations(
                doc_id="d", content="...", industry_code="manufacturing",
            )
        # fake_relation 被过滤
        assert len(result.relations) == 1
        assert result.relations[0].relation_type_id == "uses"

    async def test_relation_with_unknown_entity_filtered(self) -> None:
        """关系引用了不在 entities 中的 source/target → 丢弃。"""
        async def fake_llm(system, user):
            return {
                "entities": [{"name": "A", "type_id": "equipment"}],
                "relations": [
                    {"source_name": "A", "target_name": "Ghost",
                     "relation_type_id": "uses"},
                ],
            }
        with patch(
            "packages.extraction.entity_extractor.acall_llm_json",
            side_effect=fake_llm,
        ):
            result = await extract_entities_and_relations(
                doc_id="d", content="...", industry_code="manufacturing",
            )
        assert result.relations == []

    async def test_relation_source_type_mismatch_filtered(self) -> None:
        """关系定义域不匹配 → 丢弃。

        本体: governs(standard → process/product/...) — source 必须是 standard。
        """
        async def fake_llm(system, user):
            return {
                "entities": [
                    # 给 standard 实体（合法 source）
                    {"name": "GB/T 6075", "type_id": "standard"},
                    # 给 equipment 实体（不在 source_types 内）
                    {"name": "数控车床", "type_id": "equipment"},
                    {"name": "车削", "type_id": "process"},
                ],
                "relations": [
                    {"source_name": "GB/T 6075", "target_name": "车削",
                     "relation_type_id": "governs"},  # 合法
                    {"source_name": "数控车床", "target_name": "车削",
                     "relation_type_id": "governs"},  # 非法 source
                ],
            }
        with patch(
            "packages.extraction.entity_extractor.acall_llm_json",
            side_effect=fake_llm,
        ):
            result = await extract_entities_and_relations(
                doc_id="d", content="...", industry_code="manufacturing",
            )
        # 仅合法的 governs 留下
        assert len(result.relations) == 1
        gov_rel = result.relations[0]
        assert gov_rel.relation_type_id == "governs"

    async def test_sensitive_entity_marked(self) -> None:
        """敏感实体（人名/工艺参数）应标记 is_sensitive=True。"""
        async def fake_llm(system, user):
            return {
                "entities": [
                    {"name": "张工", "type_id": "personnel", "confidence": 0.8},
                    {"name": "数控车床", "type_id": "equipment", "confidence": 0.9},
                ],
            }
        with patch(
            "packages.extraction.entity_extractor.acall_llm_json",
            side_effect=fake_llm,
        ):
            result = await extract_entities_and_relations(
                doc_id="d",
                content="张工负责数控车床 CK6140 的操作。",
                industry_code="manufacturing",
            )
        zhang = next(e for e in result.entities if e.name == "张工")
        assert zhang.is_sensitive is True
        # 数控车床不是敏感
        eq = next(e for e in result.entities if e.name == "数控车床")
        assert eq.is_sensitive is False
        assert result.sensitive_entity_count == 1

    async def test_empty_content_returns_empty_result(self) -> None:
        result = await extract_entities_and_relations(
            doc_id="d", content="", industry_code="manufacturing",
        )
        assert result.entities == []
        assert result.relations == []

    async def test_no_ontology_returns_error(self) -> None:
        result = await extract_entities_and_relations(
            doc_id="d", content="some content",
            industry_code="nonexistent_industry",
        )
        assert "未找到" in result.error
        assert result.entities == []

    async def test_llm_failure_returns_error(self) -> None:
        with patch(
            "packages.extraction.entity_extractor.acall_llm_json",
            side_effect=Exception("LLM down"),
        ):
            result = await extract_entities_and_relations(
                doc_id="d", content="content",
                industry_code="manufacturing",
            )
        assert "LLM 调用失败" in result.error
        assert result.entities == []

    async def test_overall_confidence_is_average(self) -> None:
        async def fake_llm(system, user):
            return {
                "entities": [
                    {"name": "A", "type_id": "equipment", "confidence": 0.8},
                    {"name": "B", "type_id": "equipment", "confidence": 0.6},
                ],
            }
        with patch(
            "packages.extraction.entity_extractor.acall_llm_json",
            side_effect=fake_llm,
        ):
            result = await extract_entities_and_relations(
                doc_id="d", content="...",
                industry_code="manufacturing",
            )
        assert result.overall_confidence == pytest.approx(0.7)

    async def test_confidence_clamped(self) -> None:
        async def fake_llm(system, user):
            return {
                "entities": [
                    {"name": "A", "type_id": "equipment", "confidence": 99},
                    {"name": "B", "type_id": "equipment", "confidence": -0.5},
                ],
            }
        with patch(
            "packages.extraction.entity_extractor.acall_llm_json",
            side_effect=fake_llm,
        ):
            result = await extract_entities_and_relations(
                doc_id="d", content="...", industry_code="manufacturing",
            )
        assert all(0.0 <= e.confidence <= 1.0 for e in result.entities)
