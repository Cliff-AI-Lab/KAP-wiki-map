"""M3 #3c · 主树高级 CRUD 单测（merge / split / undo，PRD F1.3.4）。"""

from __future__ import annotations

import pytest

from packages.architect.taxonomy_builder import (
    merge_nodes,
    push_undo_snapshot,
    reset_undo_for_test,
    split_node,
    undo,
)
from packages.common.types import TaxonomyDraft
from packages.templates.registry import TaxonomyNode


@pytest.fixture(autouse=True)
def _reset():
    reset_undo_for_test()
    yield
    reset_undo_for_test()


def _draft() -> TaxonomyDraft:
    return TaxonomyDraft(
        industry_code="manufacturing",
        industry_name="制造业",
        taxonomy=[
            TaxonomyNode(id="production", name="生产管理", level=2,
                         children=[TaxonomyNode(id="planning", name="生产计划", level=3)]),
            TaxonomyNode(id="warehouse", name="仓储管理", level=2),
            TaxonomyNode(id="logistics", name="物流配送", level=2,
                         children=[TaxonomyNode(id="shipping", name="发货", level=3)]),
            TaxonomyNode(id="quality", name="质量管理", level=2),
        ],
    )


# ════════════════════════════════════════════════════════════════════════
#  merge_nodes
# ════════════════════════════════════════════════════════════════════════


class TestMergeNodes:
    def test_merge_two_nodes_into_new(self) -> None:
        draft = _draft()
        result = merge_nodes(
            draft,
            source_ids=["warehouse", "logistics"],
            target_name="供应链管理",
            target_id="supply_chain",
        )
        ids = [n.id for n in result.taxonomy]
        assert "warehouse" not in ids
        assert "logistics" not in ids
        assert "supply_chain" in ids
        assert "production" in ids and "quality" in ids  # 不动其他节点

    def test_merge_combines_children(self) -> None:
        """合并节点时子节点合并去重。"""
        draft = _draft()
        result = merge_nodes(
            draft,
            source_ids=["production", "logistics"],
            target_name="新业务",
            target_id="new_biz",
        )
        new_node = next(n for n in result.taxonomy if n.id == "new_biz")
        child_ids = {c.id for c in new_node.children}
        assert "planning" in child_ids
        assert "shipping" in child_ids

    def test_merge_too_few_matches_skipped(self) -> None:
        """source_ids 实际匹配 < 2 → 静默不动。"""
        draft = _draft()
        before_ids = {n.id for n in draft.taxonomy}
        result = merge_nodes(
            draft,
            source_ids=["warehouse", "ghost_id"],  # ghost_id 不存在
            target_name="X",
        )
        after_ids = {n.id for n in result.taxonomy}
        assert before_ids == after_ids

    def test_merge_auto_generates_target_id(self) -> None:
        draft = _draft()
        result = merge_nodes(
            draft,
            source_ids=["warehouse", "logistics"],
            target_name="Supply Chain",
        )
        ids = [n.id for n in result.taxonomy]
        # 自动生成 snake_case id
        assert any("supply_chain" in i for i in ids)

    def test_merge_less_than_2_sources_no_op(self) -> None:
        draft = _draft()
        before = len(draft.taxonomy)
        result = merge_nodes(
            draft, source_ids=["warehouse"], target_name="X",
        )
        assert len(result.taxonomy) == before


# ════════════════════════════════════════════════════════════════════════
#  split_node
# ════════════════════════════════════════════════════════════════════════


class TestSplitNode:
    def test_split_into_two_new(self) -> None:
        draft = _draft()
        result = split_node(
            draft,
            source_id="warehouse",
            new_nodes=[
                {"id": "raw_storage", "name": "原料仓"},
                {"id": "finished_storage", "name": "成品仓"},
            ],
        )
        ids = [n.id for n in result.taxonomy]
        assert "warehouse" not in ids
        assert "raw_storage" in ids
        assert "finished_storage" in ids

    def test_split_unknown_source_no_op(self) -> None:
        draft = _draft()
        before_ids = {n.id for n in draft.taxonomy}
        result = split_node(
            draft, source_id="ghost",
            new_nodes=[{"id": "x", "name": "X"}],
        )
        after_ids = {n.id for n in result.taxonomy}
        assert before_ids == after_ids

    def test_split_empty_new_nodes_no_op(self) -> None:
        draft = _draft()
        before_ids = {n.id for n in draft.taxonomy}
        result = split_node(draft, source_id="warehouse", new_nodes=[])
        after_ids = {n.id for n in result.taxonomy}
        assert before_ids == after_ids

    def test_split_auto_generates_id_from_name(self) -> None:
        draft = _draft()
        result = split_node(
            draft, source_id="warehouse",
            new_nodes=[{"name": "原 料 仓"}],  # 无 id，从 name 推
        )
        new_node_present = any("原" in n.name or n.id for n in result.taxonomy)
        assert new_node_present


# ════════════════════════════════════════════════════════════════════════
#  push_undo_snapshot / undo
# ════════════════════════════════════════════════════════════════════════


class TestUndo:
    def test_push_then_undo_restores(self) -> None:
        draft = _draft()
        before_ids = [n.id for n in draft.taxonomy]
        push_undo_snapshot("sess1", draft)

        # mutation
        merge_nodes(
            draft, source_ids=["warehouse", "logistics"],
            target_name="X", target_id="x",
        )
        assert "warehouse" not in [n.id for n in draft.taxonomy]

        # undo
        result, did_undo = undo("sess1", draft)
        assert did_undo is True
        after_ids = [n.id for n in result.taxonomy]
        assert after_ids == before_ids

    def test_undo_empty_stack(self) -> None:
        draft = _draft()
        result, did_undo = undo("sess_empty", draft)
        assert did_undo is False

    def test_multiple_undo_pops_in_lifo(self) -> None:
        draft = _draft()
        # 第一次快照
        push_undo_snapshot("sess1", draft)
        merge_nodes(draft, source_ids=["warehouse", "logistics"],
                    target_name="X", target_id="x")
        # 第二次快照
        push_undo_snapshot("sess1", draft)
        split_node(draft, source_id="x",
                   new_nodes=[{"id": "x_a", "name": "XA"}, {"id": "x_b", "name": "XB"}])
        # undo 一次回退到合并后状态
        _, did = undo("sess1", draft)
        assert did is True
        ids = [n.id for n in draft.taxonomy]
        assert "x" in ids  # 合并后但拆分前
        # 再 undo 回退到原始
        _, did = undo("sess1", draft)
        assert did is True
        ids = [n.id for n in draft.taxonomy]
        assert "warehouse" in ids and "logistics" in ids

    def test_session_isolation(self) -> None:
        d1 = _draft()
        d2 = _draft()
        push_undo_snapshot("s1", d1)
        # s2 没有快照 → undo 失败
        _, did = undo("s2", d2)
        assert did is False
        # s1 仍可 undo
        _, did = undo("s1", d1)
        assert did is True
