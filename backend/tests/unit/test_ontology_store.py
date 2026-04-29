"""M3 #1 双层本体 · 批 2 · OntologyStore 持久化 + 版本管理单测。"""

from __future__ import annotations

import pytest

from packages.common.types import (
    OntologyEntityType,
    OntologyRelationType,
    OntologyVersion,
)
from packages.ontology import (
    OntologyStore,
    OntologyRegistry,
    reset_registry_for_test,
    reset_store_for_test,
)
from packages.ontology.store import _bump_minor, _bump_patch


@pytest.fixture(autouse=True)
def _reset():
    reset_registry_for_test()
    reset_store_for_test()
    yield
    reset_registry_for_test()
    reset_store_for_test()


# ════════════════════════════════════════════════════════════════════════
#  版本号递增
# ════════════════════════════════════════════════════════════════════════


class TestVersionBump:
    def test_patch_bump(self) -> None:
        assert _bump_patch("ont-v1.0.0") == "ont-v1.0.1"
        assert _bump_patch("ont-v1.2.5") == "ont-v1.2.6"

    def test_minor_bump(self) -> None:
        assert _bump_minor("ont-v1.0.5") == "ont-v1.1.0"
        assert _bump_minor("ont-v2.3.7") == "ont-v2.4.0"

    def test_invalid_version_returns_suffix(self) -> None:
        assert "next" in _bump_patch("custom")
        assert "minor" in _bump_minor("custom")


# ════════════════════════════════════════════════════════════════════════
#  save_version / current_version / list_versions
# ════════════════════════════════════════════════════════════════════════


def _store_with_isolated_registry() -> OntologyStore:
    """构造独立 registry 的 store，避免 builtin L1 干扰。"""
    return OntologyStore(registry=OntologyRegistry())


class TestSaveAndQuery:
    def test_save_l2_first_version(self) -> None:
        store = _store_with_isolated_registry()
        v = OntologyVersion(
            version="ont-v1.0.0", layer="L2", project_id="p1",
            entity_types=[OntologyEntityType(type_id="custom", type_name="自定义")],
        )
        store.save_version(v)
        cur = store.current_version("L2", project_id="p1")
        assert cur is not None
        assert cur.version == "ont-v1.0.0"
        assert "custom" in cur.entity_type_ids()

    def test_current_returns_latest_after_multiple(self) -> None:
        store = _store_with_isolated_registry()
        v1 = OntologyVersion(version="ont-v1.0.0", layer="L2", project_id="p1")
        v2 = OntologyVersion(version="ont-v1.1.0", layer="L2", project_id="p1")
        store.save_version(v1)
        store.save_version(v2)
        assert store.current_version("L2", project_id="p1").version == "ont-v1.1.0"

    def test_list_versions_in_order(self) -> None:
        store = _store_with_isolated_registry()
        for v in ("ont-v1.0.0", "ont-v1.1.0", "ont-v1.2.0"):
            store.save_version(
                OntologyVersion(version=v, layer="L2", project_id="p1")
            )
        versions = store.list_versions("L2", project_id="p1")
        assert [v.version for v in versions] == [
            "ont-v1.0.0", "ont-v1.1.0", "ont-v1.2.0",
        ]

    def test_get_version_by_id(self) -> None:
        store = _store_with_isolated_registry()
        store.save_version(
            OntologyVersion(version="ont-v1.0.0", layer="L2", project_id="p1")
        )
        store.save_version(
            OntologyVersion(version="ont-v1.1.0", layer="L2", project_id="p1")
        )
        v = store.get_version("L2", "p1", "ont-v1.0.0")
        assert v is not None and v.version == "ont-v1.0.0"
        assert store.get_version("L2", "p1", "ghost") is None


# ════════════════════════════════════════════════════════════════════════
#  create_next_version
# ════════════════════════════════════════════════════════════════════════


class TestCreateNextVersion:
    def test_l2_initial_version_when_empty(self) -> None:
        store = _store_with_isolated_registry()
        next_v = store.create_next_version(
            "L2", project_id="p1", notes="initial",
        )
        assert next_v.version == "ont-v1.0.0"
        assert next_v.layer == "L2"
        assert next_v.project_id == "p1"

    def test_patch_bump_default(self) -> None:
        store = _store_with_isolated_registry()
        store.save_version(
            OntologyVersion(version="ont-v1.0.5", layer="L2", project_id="p1")
        )
        next_v = store.create_next_version("L2", project_id="p1")
        assert next_v.version == "ont-v1.0.6"

    def test_minor_bump(self) -> None:
        store = _store_with_isolated_registry()
        store.save_version(
            OntologyVersion(version="ont-v1.0.5", layer="L2", project_id="p1")
        )
        next_v = store.create_next_version("L2", project_id="p1", bump="minor")
        assert next_v.version == "ont-v1.1.0"

    def test_l1_initial_must_via_builtin(self) -> None:
        """L1 起步版本不能通过 create_next_version。"""
        store = _store_with_isolated_registry()
        with pytest.raises(ValueError, match="builtin"):
            store.create_next_version("L1", industry_code="newindustry")

    def test_deep_copy_entities(self) -> None:
        """next 版本修改不影响 prev。"""
        store = _store_with_isolated_registry()
        v0 = OntologyVersion(
            version="ont-v1.0.0", layer="L2", project_id="p1",
            entity_types=[OntologyEntityType(type_id="a", type_name="A")],
        )
        store.save_version(v0)
        v1 = store.create_next_version("L2", project_id="p1")
        v1.entity_types.append(OntologyEntityType(type_id="b", type_name="B"))
        # 原始 v0 不应被改
        assert len(v0.entity_types) == 1


# ════════════════════════════════════════════════════════════════════════
#  diff
# ════════════════════════════════════════════════════════════════════════


class TestDiff:
    def test_added_entity(self) -> None:
        store = _store_with_isolated_registry()
        before = OntologyVersion(
            version="v1", layer="L2", project_id="p1",
            entity_types=[OntologyEntityType(type_id="a", type_name="A")],
        )
        after = OntologyVersion(
            version="v2", layer="L2", project_id="p1",
            entity_types=[
                OntologyEntityType(type_id="a", type_name="A"),
                OntologyEntityType(type_id="b", type_name="B"),
            ],
        )
        diff = store.diff(before, after)
        assert diff.added_entity_types == ["b"]
        assert diff.removed_entity_types == []
        assert diff.modified_entity_types == []

    def test_removed_entity(self) -> None:
        store = _store_with_isolated_registry()
        before = OntologyVersion(
            version="v1", layer="L2", project_id="p1",
            entity_types=[
                OntologyEntityType(type_id="a", type_name="A"),
                OntologyEntityType(type_id="b", type_name="B"),
            ],
        )
        after = OntologyVersion(
            version="v2", layer="L2", project_id="p1",
            entity_types=[OntologyEntityType(type_id="a", type_name="A")],
        )
        diff = store.diff(before, after)
        assert diff.removed_entity_types == ["b"]

    def test_modified_entity(self) -> None:
        store = _store_with_isolated_registry()
        before = OntologyVersion(
            version="v1", layer="L2", project_id="p1",
            entity_types=[OntologyEntityType(type_id="a", type_name="A")],
        )
        after = OntologyVersion(
            version="v2", layer="L2", project_id="p1",
            entity_types=[OntologyEntityType(
                type_id="a", type_name="A 改名", description="新描述",
            )],
        )
        diff = store.diff(before, after)
        assert diff.modified_entity_types == ["a"]

    def test_relation_diff(self) -> None:
        store = _store_with_isolated_registry()
        before = OntologyVersion(
            version="v1", layer="L2", project_id="p1",
            relation_types=[OntologyRelationType(type_id="r1", type_name="R1")],
        )
        after = OntologyVersion(
            version="v2", layer="L2", project_id="p1",
            relation_types=[
                OntologyRelationType(type_id="r1", type_name="R1"),
                OntologyRelationType(type_id="r2", type_name="R2"),
            ],
        )
        diff = store.diff(before, after)
        assert diff.added_relation_types == ["r2"]

    def test_no_change_diff_empty(self) -> None:
        store = _store_with_isolated_registry()
        v = OntologyVersion(
            version="v1", layer="L2", project_id="p1",
            entity_types=[OntologyEntityType(type_id="a", type_name="A")],
        )
        diff = store.diff(v, v)
        assert diff.added_entity_types == []
        assert diff.removed_entity_types == []
        assert diff.modified_entity_types == []
