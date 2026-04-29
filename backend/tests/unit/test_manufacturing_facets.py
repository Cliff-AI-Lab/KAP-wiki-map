"""M1 #2 · 制造行业 facet 模板包单测（PRD §10.4 1129 行）。"""

from __future__ import annotations

import pytest

from packages.templates.facets_manufacturing import (
    EQUIPMENT_FAULT_SCHEMA,
    MANUFACTURING_FACETS,
    PROCESS_STANDARD_SCHEMA,
    QUALITY_RECORD_SCHEMA,
    SOP_SCHEMA,
)
from packages.templates.registry import (
    FacetField,
    FacetSchema,
    get_facet_schema,
    get_template,
    validate_facet_metadata,
)


# ──────── 4 套 schema 完整性 ────────


class TestSchemaCompleteness:
    def test_all_four_facets_registered(self) -> None:
        assert set(MANUFACTURING_FACETS.keys()) == {
            "equipment_fault", "process_standard", "sop", "quality_record",
        }

    def test_each_schema_has_required_fields(self) -> None:
        """每套 schema 至少有 1 个 required 字段。"""
        for code, schema in MANUFACTURING_FACETS.items():
            assert len(schema.required_keys()) >= 1, f"{code} 无 required 字段"

    def test_each_schema_has_sensitive_fields(self) -> None:
        """4 套 schema 都至少标了 1 个敏感字段（决策书 §5.4 联动）。"""
        for code, schema in MANUFACTURING_FACETS.items():
            assert len(schema.sensitive_keys()) >= 1, f"{code} 无敏感字段标记"


# ──────── 设备故障 ────────


class TestEquipmentFaultSchema:
    def test_required_fields(self) -> None:
        keys = set(EQUIPMENT_FAULT_SCHEMA.required_keys())
        assert "equipment_name" in keys
        assert "fault_phenomenon" in keys
        assert "resolution" in keys
        assert "occurred_at" in keys

    def test_repaired_by_is_sensitive(self) -> None:
        """维修人是人名敏感字段（脱敏管线触发点）。"""
        sensitive = EQUIPMENT_FAULT_SCHEMA.sensitive_keys()
        assert "repaired_by" in sensitive

    def test_primary_role_sme(self) -> None:
        assert EQUIPMENT_FAULT_SCHEMA.primary_role == "SME"


# ──────── 工艺标准 ────────


class TestProcessStandardSchema:
    def test_temperature_field_has_unit(self) -> None:
        temp_field = next(f for f in PROCESS_STANDARD_SCHEMA.fields
                          if f.key == "key_param_temp")
        assert temp_field.type == "numeric"
        assert temp_field.unit == "℃"
        assert temp_field.sensitive is True

    def test_owner_department_is_reference(self) -> None:
        owner = next(f for f in PROCESS_STANDARD_SCHEMA.fields
                     if f.key == "owner_department")
        assert owner.type == "reference"
        assert owner.ref_type == "Department"


# ──────── SOP ────────


class TestSOPSchema:
    def test_ppe_is_enum(self) -> None:
        ppe = next(f for f in SOP_SCHEMA.fields if f.key == "ppe_required")
        assert ppe.type == "enum"
        assert "安全帽" in ppe.enum_values
        assert "防护手套" in ppe.enum_values

    def test_approver_required_and_sensitive(self) -> None:
        ap = next(f for f in SOP_SCHEMA.fields if f.key == "approver")
        assert ap.required is True
        assert ap.sensitive is True


# ──────── 质量记录 ────────


class TestQualityRecordSchema:
    def test_judgment_enum_values(self) -> None:
        jud = next(f for f in QUALITY_RECORD_SCHEMA.fields if f.key == "judgment")
        assert jud.type == "enum"
        assert set(jud.enum_values) == {"合格", "不合格", "让步接收", "返工", "报废"}

    def test_actual_value_sensitive(self) -> None:
        av = next(f for f in QUALITY_RECORD_SCHEMA.fields if f.key == "actual_value")
        assert av.sensitive is True

    def test_primary_role_dg(self) -> None:
        """质量记录主审 DG（决策书 §5.2 W5 入库 R 主审）。"""
        assert QUALITY_RECORD_SCHEMA.primary_role == "DG"


# ──────── Industry registry 集成 ────────


class TestRegistryIntegration:
    def test_manufacturing_template_has_facets(self) -> None:
        tpl = get_template("manufacturing")
        assert tpl is not None
        assert len(tpl.facets) == 4

    def test_get_facet_schema_returns_correct_one(self) -> None:
        schema = get_facet_schema("manufacturing", "equipment_fault")
        assert schema is not None
        assert schema.name == "设备故障"

    def test_get_facet_schema_unknown_industry_returns_none(self) -> None:
        assert get_facet_schema("nonexistent", "equipment_fault") is None

    def test_get_facet_schema_unknown_doc_type_returns_none(self) -> None:
        assert get_facet_schema("manufacturing", "unknown_type") is None


# ──────── validate_facet_metadata ────────


class TestValidateFacetMetadata:
    def test_all_required_passes(self) -> None:
        metadata = {
            "equipment_name": "汽轮机1号",
            "fault_phenomenon": "异响",
            "resolution": "更换轴承",
            "occurred_at": "2026-04-29",
        }
        missing = validate_facet_metadata(EQUIPMENT_FAULT_SCHEMA, metadata)
        assert missing == []

    def test_missing_required_returned(self) -> None:
        metadata = {"equipment_name": "汽轮机1号"}
        missing = validate_facet_metadata(EQUIPMENT_FAULT_SCHEMA, metadata)
        assert "fault_phenomenon" in missing
        assert "resolution" in missing
        assert "occurred_at" in missing

    def test_empty_string_counted_as_missing(self) -> None:
        metadata = {
            "equipment_name": "",
            "fault_phenomenon": "x",
            "resolution": "y",
            "occurred_at": "2026-04-29",
        }
        missing = validate_facet_metadata(EQUIPMENT_FAULT_SCHEMA, metadata)
        assert "equipment_name" in missing


# ──────── 与脱敏管线联动 ────────


class TestFacetSensitiveIntegration:
    def test_sensitive_keys_are_typical_redact_targets(self) -> None:
        """敏感字段命中脱敏管线的三类语义（人名 / 数值 / 客户）。"""
        for schema in MANUFACTURING_FACETS.values():
            for key in schema.sensitive_keys():
                field = next(f for f in schema.fields if f.key == key)
                # 至少是 str / numeric 之一（脱敏管线主要处理这两类）
                assert field.type in ("str", "numeric"), (
                    f"敏感字段 {key} 类型 {field.type} 不在脱敏管线支持范围"
                )
