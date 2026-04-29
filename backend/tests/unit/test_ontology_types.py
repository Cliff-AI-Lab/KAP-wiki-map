"""M3 #1 双层本体 · 批 1 · 类型 + L1 内置完整性单测。"""

from __future__ import annotations

import pytest

from packages.common.types import (
    OntologyEntityType,
    OntologyRelationType,
    OntologyVersion,
)
from packages.ontology import (
    get_current_l1,
    get_registry,
    register_l1,
    register_l2,
    reset_registry_for_test,
)
from packages.ontology.builtin.energy_l1 import ENERGY_L1_V1
from packages.ontology.builtin.manufacturing_l1 import MANUFACTURING_L1_V1


@pytest.fixture(autouse=True)
def _reset():
    reset_registry_for_test()
    yield
    reset_registry_for_test()


# ════════════════════════════════════════════════════════════════════════
#  Pydantic 模型基础
# ════════════════════════════════════════════════════════════════════════


class TestPydanticModels:
    def test_entity_type_default_layer_l2(self) -> None:
        e = OntologyEntityType(type_id="x", type_name="X")
        assert e.layer == "L2"
        assert e.required_properties == []

    def test_entity_type_l1_explicit(self) -> None:
        e = OntologyEntityType(type_id="x", type_name="X", layer="L1")
        assert e.layer == "L1"

    def test_relation_type_with_constraints(self) -> None:
        r = OntologyRelationType(
            type_id="produces", type_name="产出",
            source_types=["process"], target_types=["product"],
        )
        assert "process" in r.source_types
        assert "product" in r.target_types

    def test_version_helpers(self) -> None:
        v = OntologyVersion(
            version="v1", layer="L1", industry_code="manufacturing",
            entity_types=[
                OntologyEntityType(type_id="a", type_name="A"),
                OntologyEntityType(type_id="b", type_name="B"),
            ],
            relation_types=[
                OntologyRelationType(type_id="r1", type_name="R1"),
            ],
        )
        assert v.entity_type_ids() == {"a", "b"}
        assert v.relation_type_ids() == {"r1"}


# ════════════════════════════════════════════════════════════════════════
#  L1 内置 — 制造业完整性
# ════════════════════════════════════════════════════════════════════════


class TestManufacturingL1:
    def test_has_9_core_entity_types(self) -> None:
        """决策书 §5.3 锁定 9 类核心概念。"""
        ids = MANUFACTURING_L1_V1.entity_type_ids()
        expected = {
            "product", "process", "material", "equipment",
            "operation", "defect", "standard", "personnel", "organization",
        }
        assert expected.issubset(ids)

    def test_has_8_core_relations(self) -> None:
        ids = MANUFACTURING_L1_V1.relation_type_ids()
        expected = {
            "includes", "produces", "uses", "detected_in",
            "executed_by", "governs", "belongs_to", "referenced_by",
        }
        assert expected.issubset(ids)

    def test_all_entities_have_examples(self) -> None:
        for e in MANUFACTURING_L1_V1.entity_types:
            assert len(e.examples) >= 3, f"{e.type_id} 缺少示例（NER 需要）"

    def test_industry_code_set(self) -> None:
        assert MANUFACTURING_L1_V1.industry_code == "manufacturing"
        assert MANUFACTURING_L1_V1.layer == "L1"
        assert MANUFACTURING_L1_V1.version.startswith("ont-v")


# ════════════════════════════════════════════════════════════════════════
#  L1 内置 — 能源完整性
# ════════════════════════════════════════════════════════════════════════


class TestEnergyL1:
    def test_has_10_iec_cim_entity_types(self) -> None:
        ids = ENERGY_L1_V1.entity_type_ids()
        expected = {
            "power_plant", "generator", "boiler", "turbine", "breaker",
            "line", "substation", "hazard", "standard", "role",
        }
        assert expected.issubset(ids)

    def test_has_6_relations(self) -> None:
        ids = ENERGY_L1_V1.relation_type_ids()
        expected = {
            "connects_to", "supplies", "monitors",
            "regulated_by", "detected_at", "responds_to",
        }
        assert expected.issubset(ids)

    def test_industry_code_energy(self) -> None:
        assert ENERGY_L1_V1.industry_code == "energy"
        assert ENERGY_L1_V1.layer == "L1"


# ════════════════════════════════════════════════════════════════════════
#  Registry 注册 / 查询
# ════════════════════════════════════════════════════════════════════════


class TestRegistry:
    def test_autoload_builtin_l1(self) -> None:
        """get_registry() 首次调用时自动加载内置 L1。"""
        reg = get_registry()
        assert reg.get_current_l1("manufacturing") is not None
        assert reg.get_current_l1("energy") is not None

    def test_get_current_l1_returns_latest(self) -> None:
        from datetime import datetime
        reg = get_registry()
        v2 = OntologyVersion(
            version="ont-v1.1.0", layer="L1", industry_code="manufacturing",
            created_at=datetime(2026, 6, 1), notes="v2",
        )
        register_l1(v2)
        current = get_current_l1("manufacturing")
        assert current.version == "ont-v1.1.0"

    def test_register_l2_requires_project_id(self) -> None:
        reg = get_registry()
        bad = OntologyVersion(version="v1", layer="L2", project_id="")
        with pytest.raises(ValueError, match="project_id"):
            register_l2(bad)

    def test_register_l1_requires_industry_code(self) -> None:
        bad = OntologyVersion(version="v1", layer="L1", industry_code="")
        with pytest.raises(ValueError, match="industry_code"):
            register_l1(bad)

    def test_register_layer_mismatch_raises(self) -> None:
        bad_layer = OntologyVersion(
            version="v1", layer="L2", project_id="p1",
        )
        # 用 L2 实例调 register_l1 应报错
        with pytest.raises(ValueError, match="L1 注册收到 layer=L2"):
            register_l1(bad_layer)

    def test_l2_per_project_isolation(self) -> None:
        v_a = OntologyVersion(
            version="ont-v1.0.0", layer="L2", project_id="A",
            entity_types=[OntologyEntityType(type_id="x", type_name="X")],
        )
        v_b = OntologyVersion(
            version="ont-v1.0.0", layer="L2", project_id="B",
            entity_types=[OntologyEntityType(type_id="y", type_name="Y")],
        )
        register_l2(v_a)
        register_l2(v_b)
        from packages.ontology import get_current_l2
        assert get_current_l2("A").entity_type_ids() == {"x"}
        assert get_current_l2("B").entity_type_ids() == {"y"}
