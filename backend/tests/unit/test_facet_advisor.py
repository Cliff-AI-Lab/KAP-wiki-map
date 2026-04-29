"""M3 #3a 块① · Facet 提议器单测（PRD F1.4）。"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from packages.architect.facet_advisor import (
    _parse_facet_response,
    propose_facets_for_doc_type,
    propose_facets_for_taxonomy,
)
from packages.ontology import reset_registry_for_test


@pytest.fixture(autouse=True)
def _reset():
    reset_registry_for_test()
    yield
    reset_registry_for_test()


# ════════════════════════════════════════════════════════════════════════
#  _parse_facet_response
# ════════════════════════════════════════════════════════════════════════


class TestParseFacetResponse:
    def test_normal_full_schema(self) -> None:
        raw = {
            "doc_type": "equipment_fault",
            "name": "设备故障",
            "description": "设备异常案例",
            "primary_role": "SME",
            "fields": [
                {"key": "equipment_name", "name": "设备名称",
                 "type": "str", "required": True},
                {"key": "downtime", "name": "停机时长",
                 "type": "numeric", "unit": "min", "sensitive": True},
                {"key": "judgment", "name": "判定", "type": "enum",
                 "enum_values": ["合格", "不合格"]},
            ],
        }
        schema = _parse_facet_response(raw, "equipment_fault")
        assert schema is not None
        assert schema.doc_type == "equipment_fault"
        assert schema.name == "设备故障"
        assert schema.primary_role == "SME"
        assert len(schema.fields) == 3

    def test_sensitive_marker_preserved(self) -> None:
        raw = {
            "fields": [
                {"key": "x", "name": "X", "type": "str", "sensitive": True},
            ],
        }
        schema = _parse_facet_response(raw, "x_type")
        assert schema is not None
        assert schema.fields[0].sensitive is True
        assert "x" in schema.sensitive_keys()

    def test_invalid_field_type_defaults_to_str(self) -> None:
        raw = {
            "fields": [
                {"key": "y", "name": "Y", "type": "weird_type"},
            ],
        }
        schema = _parse_facet_response(raw, "y_type")
        assert schema is not None
        assert schema.fields[0].type == "str"

    def test_invalid_primary_role_defaults_sme(self) -> None:
        raw = {
            "primary_role": "InvalidRole",
            "fields": [{"key": "x", "name": "X", "type": "str"}],
        }
        schema = _parse_facet_response(raw, "x")
        assert schema.primary_role == "SME"

    def test_missing_key_or_name_skipped(self) -> None:
        raw = {
            "fields": [
                {"key": "valid", "name": "Valid", "type": "str"},
                {"key": "", "name": "缺 key", "type": "str"},
                {"key": "缺名", "name": "", "type": "str"},
            ],
        }
        schema = _parse_facet_response(raw, "x")
        assert len(schema.fields) == 1
        assert schema.fields[0].key == "valid"

    def test_no_fields_returns_none(self) -> None:
        raw = {"name": "X", "fields": []}
        assert _parse_facet_response(raw, "x") is None

    def test_non_dict_returns_none(self) -> None:
        assert _parse_facet_response("not a dict", "x") is None  # type: ignore

    def test_enum_values_truncated_and_stringified(self) -> None:
        raw = {
            "fields": [
                {"key": "j", "name": "J", "type": "enum",
                 "enum_values": ["a", 1, 2.5, {"bad": True}, "good"]},
            ],
        }
        schema = _parse_facet_response(raw, "x")
        # dict 项被过滤，其他保留
        assert "a" in schema.fields[0].enum_values
        assert "1" in schema.fields[0].enum_values


# ════════════════════════════════════════════════════════════════════════
#  propose_facets_for_doc_type
# ════════════════════════════════════════════════════════════════════════


class TestProposeFacetsForDocType:
    async def test_normal_flow(self) -> None:
        async def fake_llm(system, user):
            return {
                "doc_type": "equipment_fault",
                "name": "设备故障",
                "primary_role": "SME",
                "fields": [
                    {"key": "equipment_name", "name": "设备名称",
                     "type": "str", "required": True},
                    {"key": "downtime", "name": "停机时长",
                     "type": "numeric", "unit": "min", "sensitive": True},
                ],
            }

        with patch(
            "packages.architect.facet_advisor.acall_llm_json",
            side_effect=fake_llm,
        ):
            schema = await propose_facets_for_doc_type(
                industry_code="manufacturing",
                doc_type="equipment_fault",
                sample_texts=["故障 1", "故障 2", "故障 3"],
            )

        assert schema is not None
        assert schema.doc_type == "equipment_fault"
        assert "equipment_name" in [f.key for f in schema.fields]

    async def test_empty_samples_returns_none(self) -> None:
        result = await propose_facets_for_doc_type(
            industry_code="manufacturing",
            doc_type="equipment_fault",
            sample_texts=[],
        )
        assert result is None

    async def test_empty_doc_type_returns_none(self) -> None:
        result = await propose_facets_for_doc_type(
            industry_code="manufacturing",
            doc_type="",
            sample_texts=["sample"],
        )
        assert result is None

    async def test_llm_failure_returns_none(self) -> None:
        with patch(
            "packages.architect.facet_advisor.acall_llm_json",
            side_effect=Exception("LLM down"),
        ):
            schema = await propose_facets_for_doc_type(
                industry_code="manufacturing",
                doc_type="equipment_fault",
                sample_texts=["s"],
            )
        assert schema is None


# ════════════════════════════════════════════════════════════════════════
#  propose_facets_for_taxonomy （批量）
# ════════════════════════════════════════════════════════════════════════


class TestProposeFacetsForTaxonomy:
    async def test_batch_proposal(self) -> None:
        async def fake_llm(system, user):
            # 简单返回，doc_type 从 user prompt 中带回
            return {
                "doc_type": "x",
                "name": "X",
                "fields": [{"key": "a", "name": "A", "type": "str"}],
            }

        with patch(
            "packages.architect.facet_advisor.acall_llm_json",
            side_effect=fake_llm,
        ):
            result = await propose_facets_for_taxonomy(
                industry_code="manufacturing",
                doc_types=["equipment_fault", "sop", "quality_record"],
                sample_texts_by_type={
                    "equipment_fault": ["fault sample"],
                    "sop": ["sop sample"],
                    "quality_record": ["qa sample"],
                },
            )

        assert len(result) == 3

    async def test_skip_doc_types_without_samples(self) -> None:
        async def fake_llm(system, user):
            return {
                "doc_type": "x", "name": "X",
                "fields": [{"key": "a", "name": "A", "type": "str"}],
            }
        with patch(
            "packages.architect.facet_advisor.acall_llm_json",
            side_effect=fake_llm,
        ):
            result = await propose_facets_for_taxonomy(
                industry_code="manufacturing",
                doc_types=["equipment_fault", "no_samples_type"],
                sample_texts_by_type={
                    "equipment_fault": ["sample"],
                },
            )
        assert "equipment_fault" in result
        assert "no_samples_type" not in result


# ════════════════════════════════════════════════════════════════════════
#  Exporter 接入 facets
# ════════════════════════════════════════════════════════════════════════


class TestExporterFacetsIntegration:
    def test_draft_facets_exported_to_template(self) -> None:
        from packages.architect.exporter import export_to_industry_template
        from packages.common.types import TaxonomyDraft
        from packages.templates.registry import (
            FacetField, FacetSchema, TaxonomyNode,
        )

        draft = TaxonomyDraft(
            industry_code="manufacturing",
            industry_name="制造业",
            taxonomy=[TaxonomyNode(id="x", name="X", level=2)],
            facets={
                "custom_doc": FacetSchema(
                    doc_type="custom_doc",
                    name="自定义",
                    fields=[FacetField(key="k", name="K", type="str")],
                ),
            },
        )
        tpl = export_to_industry_template(draft, register_globally=False)
        assert "custom_doc" in tpl.facets
        assert tpl.facets["custom_doc"].name == "自定义"

    def test_dict_facets_serialized_correctly(self) -> None:
        """传入 dict 形式的 facet（如 LLM 返回）也能被 export 接受。"""
        from packages.architect.exporter import export_to_industry_template
        from packages.common.types import TaxonomyDraft
        from packages.templates.registry import TaxonomyNode

        draft = TaxonomyDraft(
            industry_code="manufacturing",
            taxonomy=[TaxonomyNode(id="x", name="X", level=2)],
            facets={
                "x": {
                    "doc_type": "x", "name": "X",
                    "fields": [{"key": "k", "name": "K", "type": "str"}],
                },
            },
        )
        tpl = export_to_industry_template(draft, register_globally=False)
        assert "x" in tpl.facets
        assert tpl.facets["x"].fields[0].key == "k"
