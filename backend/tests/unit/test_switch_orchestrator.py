"""M4 批 3 · 灰度切换 + 回滚单测（决策书 §5.3）。"""

from __future__ import annotations

import pytest

from packages.rebuild import (
    PromoteRefused,
    ShadowGraphStore,
    compare_versions,
    promote_shadow,
    reset_shadow_store_for_test,
    rollback_promotion,
)


@pytest.fixture(autouse=True)
def _reset():
    reset_shadow_store_for_test()
    yield
    reset_shadow_store_for_test()


def _build_shadow_with_data() -> ShadowGraphStore:
    """构造一个含 source / target 数据的 ShadowGraphStore。"""
    s = ShadowGraphStore()
    # source 版本：5 个 equipment + 5 个 process + 1 个 standard
    for i in range(5):
        s.add_entity("p1", "v1.0.0",
                     entity_name=f"E{i}", type_id="equipment", doc_id="d")
    for i in range(5):
        s.add_entity("p1", "v1.0.0",
                     entity_name=f"P{i}", type_id="process", doc_id="d")
    s.add_entity("p1", "v1.0.0",
                 entity_name="S1", type_id="standard", doc_id="d")
    # target 版本：相同结构 + 加 1 个 control_loop 类型
    for i in range(5):
        s.add_entity("p1", "v1.0.1",
                     entity_name=f"E{i}", type_id="equipment", doc_id="d")
    for i in range(5):
        s.add_entity("p1", "v1.0.1",
                     entity_name=f"P{i}", type_id="process", doc_id="d")
    s.add_entity("p1", "v1.0.1",
                 entity_name="S1", type_id="standard", doc_id="d")
    s.add_entity("p1", "v1.0.1",
                 entity_name="CL1", type_id="control_loop", doc_id="d")
    return s


# ════════════════════════════════════════════════════════════════════════
#  compare_versions
# ════════════════════════════════════════════════════════════════════════


class TestCompareVersions:
    def test_basic_diff(self) -> None:
        s = _build_shadow_with_data()
        report = compare_versions("p1", "v1.0.0", "v1.0.1", shadow=s)
        assert report.source_node_count == 11
        assert report.target_node_count == 12
        assert "control_loop" in report.added_entity_types
        assert report.removed_entity_types == []

    def test_safe_for_minor_change(self) -> None:
        """节点数变化 < 30% + 关键类型保留 → safe。"""
        s = _build_shadow_with_data()
        report = compare_versions("p1", "v1.0.0", "v1.0.1", shadow=s)
        assert report.safe_to_promote is True

    def test_unsafe_for_huge_node_change(self) -> None:
        s = ShadowGraphStore()
        # source 100 → target 30 (变化 70%)
        for i in range(100):
            s.add_entity("p1", "v1", entity_name=f"E{i}",
                         type_id="equipment", doc_id="d")
        for i in range(30):
            s.add_entity("p1", "v2", entity_name=f"E{i}",
                         type_id="equipment", doc_id="d")
        report = compare_versions("p1", "v1", "v2", shadow=s)
        assert report.safe_to_promote is False
        assert any("节点数变化" in r for r in report.safety_reasons)

    def test_unsafe_when_key_type_disappears(self) -> None:
        """关键类型在新版本消失 → unsafe。"""
        s = ShadowGraphStore()
        # source 含 equipment + process（各 5 个）
        for i in range(5):
            s.add_entity("p1", "v1", entity_name=f"E{i}",
                         type_id="equipment", doc_id="d")
            s.add_entity("p1", "v1", entity_name=f"P{i}",
                         type_id="process", doc_id="d")
        # target 没有 equipment（消失）
        for i in range(5):
            s.add_entity("p1", "v2", entity_name=f"P{i}",
                         type_id="process", doc_id="d")
        report = compare_versions("p1", "v1", "v2", shadow=s)
        # 节点数变化 50% + 关键类型 equipment 消失
        assert report.safe_to_promote is False
        assert any("equipment" in r for r in report.safety_reasons)

    def test_empty_versions(self) -> None:
        s = ShadowGraphStore()
        report = compare_versions("p_empty", "v1", "v2", shadow=s)
        assert report.source_node_count == 0
        assert report.target_node_count == 0
        assert report.safe_to_promote is True


# ════════════════════════════════════════════════════════════════════════
#  promote_shadow
# ════════════════════════════════════════════════════════════════════════


class TestPromoteShadow:
    def test_safe_promote_succeeds(self) -> None:
        s = _build_shadow_with_data()
        report = promote_shadow("p1", "v1.0.0", "v1.0.1", shadow=s)
        assert report.safe_to_promote is True

    def test_unsafe_without_force_raises(self) -> None:
        s = ShadowGraphStore()
        # 巨大变化（节点数 100 → 30，70% 变化）
        for i in range(100):
            s.add_entity("p1", "v1", entity_name=f"E{i}",
                         type_id="equipment", doc_id="d")
        for i in range(30):
            s.add_entity("p1", "v2", entity_name=f"E{i}",
                         type_id="equipment", doc_id="d")
        with pytest.raises(PromoteRefused):
            promote_shadow("p1", "v1", "v2", shadow=s)

    def test_unsafe_with_force_succeeds(self) -> None:
        s = ShadowGraphStore()
        for i in range(100):
            s.add_entity("p1", "v1", entity_name=f"E{i}",
                         type_id="equipment", doc_id="d")
        for i in range(30):
            s.add_entity("p1", "v2", entity_name=f"E{i}",
                         type_id="equipment", doc_id="d")
        # force=True 跳过启发式
        report = promote_shadow(
            "p1", "v1", "v2", force=True, shadow=s,
        )
        assert report.safe_to_promote is False  # 报告还是 unsafe，但允许切换


# ════════════════════════════════════════════════════════════════════════
#  rollback_promotion
# ════════════════════════════════════════════════════════════════════════


class TestRollback:
    def test_rollback_to_previous(self) -> None:
        s = _build_shadow_with_data()
        # 模拟先 promote 一次
        s._previous_main["p1"] = "v1.0.0"
        rolled = rollback_promotion("p1", shadow=s)
        assert rolled == "v1.0.0"

    def test_rollback_no_previous(self) -> None:
        s = ShadowGraphStore()
        rolled = rollback_promotion("p_nope", shadow=s)
        assert rolled is None
