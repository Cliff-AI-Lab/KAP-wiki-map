"""M4 批 1 · ShadowGraphStore 单测（决策书 §5.3 影子库）。"""

from __future__ import annotations

import pytest

from packages.rebuild import (
    ShadowGraphStore,
    get_shadow_store,
    reset_shadow_store_for_test,
)


@pytest.fixture(autouse=True)
def _reset():
    reset_shadow_store_for_test()
    yield
    reset_shadow_store_for_test()


# ════════════════════════════════════════════════════════════════════════
#  begin_shadow / current_shadow_version
# ════════════════════════════════════════════════════════════════════════


class TestShadowLifecycle:
    def test_begin_marks_current(self) -> None:
        s = ShadowGraphStore()
        s.begin_shadow("p1", "ont-v1.0.1")
        assert s.current_shadow_version("p1") == "ont-v1.0.1"

    def test_no_shadow_returns_none(self) -> None:
        s = ShadowGraphStore()
        assert s.current_shadow_version("p1") is None

    def test_cancel_clears_shadow(self) -> None:
        s = ShadowGraphStore()
        s.begin_shadow("p1", "ont-v1.0.1")
        s.add_entity("p1", "ont-v1.0.1",
                     entity_name="X", type_id="equipment", doc_id="d1")
        s.cancel_shadow("p1")
        assert s.current_shadow_version("p1") is None
        assert s.entity_count("p1", "ont-v1.0.1") == 0


# ════════════════════════════════════════════════════════════════════════
#  add_entity / add_relation / 版本隔离
# ════════════════════════════════════════════════════════════════════════


class TestEntityAndRelation:
    def test_entity_dedup_by_name(self) -> None:
        s = ShadowGraphStore()
        s.begin_shadow("p1", "v1")
        s.add_entity("p1", "v1", entity_name="A", type_id="equipment", doc_id="d1")
        s.add_entity("p1", "v1", entity_name="A", type_id="equipment", doc_id="d2")
        # 同实体合并 doc_ids
        entities = s.list_entities("p1", "v1")
        assert len(entities) == 1
        assert set(entities[0]["doc_ids"]) == {"d1", "d2"}

    def test_relation_dedup(self) -> None:
        s = ShadowGraphStore()
        s.begin_shadow("p1", "v1")
        s.add_relation(
            "p1", "v1",
            source_name="A", target_name="B",
            relation_type_id="uses", doc_id="d1",
        )
        s.add_relation(
            "p1", "v1",
            source_name="A", target_name="B",
            relation_type_id="uses", doc_id="d2",
        )
        rels = s.list_relations("p1", "v1")
        assert len(rels) == 1

    def test_version_isolation(self) -> None:
        """不同 ontology_version 下的影子库是独立桶。"""
        s = ShadowGraphStore()
        s.add_entity("p1", "v1", entity_name="A", type_id="t", doc_id="d")
        s.add_entity("p1", "v2", entity_name="A", type_id="t", doc_id="d")
        assert s.entity_count("p1", "v1") == 1
        assert s.entity_count("p1", "v2") == 1
        # 不同 project 也隔离
        s.add_entity("p2", "v1", entity_name="A", type_id="t", doc_id="d")
        assert s.entity_count("p1", "v1") == 1  # 不变
        assert s.entity_count("p2", "v1") == 1


# ════════════════════════════════════════════════════════════════════════
#  entity_type_distribution
# ════════════════════════════════════════════════════════════════════════


class TestTypeDistribution:
    def test_distribution_counts_by_type(self) -> None:
        s = ShadowGraphStore()
        s.add_entity("p", "v", entity_name="E1", type_id="equipment", doc_id="d")
        s.add_entity("p", "v", entity_name="E2", type_id="equipment", doc_id="d")
        s.add_entity("p", "v", entity_name="P1", type_id="process", doc_id="d")

        dist = s.entity_type_distribution("p", "v")
        assert dist["equipment"] == 2
        assert dist["process"] == 1


# ════════════════════════════════════════════════════════════════════════
#  swap_shadow_to_main / rollback
# ════════════════════════════════════════════════════════════════════════


class TestSwapAndRollback:
    def test_swap_clears_current_records_previous(self) -> None:
        s = ShadowGraphStore()
        s.begin_shadow("p1", "ont-v1.0.1")
        s.add_entity("p1", "ont-v1.0.1",
                     entity_name="X", type_id="equipment", doc_id="d1")
        ok = s.swap_shadow_to_main("p1", "ont-v1.0.1")
        assert ok is True
        # current_shadow 已清空（M4 lite 不再认为它是"影子"）
        assert s.current_shadow_version("p1") is None

    def test_swap_unknown_version_returns_false(self) -> None:
        s = ShadowGraphStore()
        ok = s.swap_shadow_to_main("p1", "unknown")
        assert ok is False

    def test_rollback_returns_previous(self) -> None:
        s = ShadowGraphStore()
        s.begin_shadow("p1", "ont-v1.0.1")
        s.add_entity("p1", "ont-v1.0.1",
                     entity_name="X", type_id="t", doc_id="d")
        s.swap_shadow_to_main("p1", "ont-v1.0.1")

        # 模拟之前有 main = ont-v1.0.0（通过 begin + swap 的副作用）
        # 简化：直接在 _previous_main 注入
        s._previous_main["p1"] = "ont-v1.0.0"

        rolled = s.rollback_to_previous("p1")
        assert rolled == "ont-v1.0.0"

    def test_rollback_no_previous_returns_none(self) -> None:
        s = ShadowGraphStore()
        rolled = s.rollback_to_previous("p1")
        assert rolled is None


# ════════════════════════════════════════════════════════════════════════
#  Singleton
# ════════════════════════════════════════════════════════════════════════


class TestSingleton:
    def test_get_returns_same_instance(self) -> None:
        a = get_shadow_store()
        b = get_shadow_store()
        assert a is b

    def test_reset_creates_new(self) -> None:
        a = get_shadow_store()
        reset_shadow_store_for_test()
        b = get_shadow_store()
        assert a is not b
