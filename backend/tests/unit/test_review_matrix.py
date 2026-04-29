"""M1 矩阵审核台 · 批 1 · 4×6 R/C/I 矩阵 + 升级链规则单测。

来源即真相：本测试覆盖决策书 §5.2 D6 那张表的每一格 + §5.5 D12 升级链。
"""

from __future__ import annotations

import pytest

from packages.governance.matrix import (
    ALL_ROLES,
    ALL_WORKSTATIONS,
    ROLE_WORKSTATION_MATRIX,
    co_review_roles,
    escalation_chain,
    involvement_for,
    is_top_role,
    next_role_in_chain,
    primary_role_for,
)


# ──────── 24 格矩阵完整性 ────────


class TestMatrixCompleteness:
    def test_all_24_cells_defined(self) -> None:
        """6 工位 × 4 角色 = 24 格全部有定义。"""
        assert len(ROLE_WORKSTATION_MATRIX) == 24

    def test_every_cell_in_rci(self) -> None:
        """每格只能是 R / C / I 之一。"""
        for value in ROLE_WORKSTATION_MATRIX.values():
            assert value in ("R", "C", "I")

    @pytest.mark.parametrize("ws", ALL_WORKSTATIONS)
    def test_each_workstation_has_at_least_one_R(self, ws) -> None:
        """每个工位至少有 1 个主审角色（决策书原则）。"""
        primaries = [r for (w, r), v in ROLE_WORKSTATION_MATRIX.items()
                     if w == ws and v == "R"]
        assert len(primaries) >= 1, f"工位 {ws} 缺主审角色"


# ──────── 决策书 §5.2 24 格逐项验证 ────────


@pytest.mark.parametrize("ws,role,expected", [
    # W1 解析
    ("W1", "DG", "R"), ("W1", "SME", "I"), ("W1", "SEC", "C"), ("W1", "AIOps", "I"),
    # W2 归类
    ("W2", "DG", "R"), ("W2", "SME", "C"), ("W2", "SEC", "C"), ("W2", "AIOps", "I"),
    # W3 切块
    ("W3", "DG", "R"), ("W3", "SME", "I"), ("W3", "SEC", "I"), ("W3", "AIOps", "I"),
    # W4 抽取（SME 必审）
    ("W4", "DG", "I"), ("W4", "SME", "R"), ("W4", "SEC", "C"), ("W4", "AIOps", "I"),
    # W5 入库
    ("W5", "DG", "R"), ("W5", "SME", "C"), ("W5", "SEC", "C"), ("W5", "AIOps", "I"),
    # W6 监控（SME + AIOps 双 R）
    ("W6", "DG", "I"), ("W6", "SME", "R"), ("W6", "SEC", "C"), ("W6", "AIOps", "R"),
])
def test_matrix_cell_matches_decision_doc(ws, role, expected) -> None:
    assert involvement_for(ws, role) == expected


# ──────── primary_role_for ────────


class TestPrimaryRole:
    def test_w1_w3_w5_dg_main(self) -> None:
        assert primary_role_for("W1") == "DG"
        assert primary_role_for("W3") == "DG"
        assert primary_role_for("W5") == "DG"

    def test_w2_dg_main(self) -> None:
        assert primary_role_for("W2") == "DG"

    def test_w4_sme_must_review(self) -> None:
        """W4 必须 SME 主审（核心研发知识 D12 锁定）。"""
        assert primary_role_for("W4") == "SME"

    def test_w6_defaults_to_sme(self) -> None:
        """W6 双 R 默认返回 SME（知识缺口工单优先）。"""
        assert primary_role_for("W6") == "SME"


# ──────── co_review_roles ────────


class TestCoReviewRoles:
    def test_w1_only_sec_co(self) -> None:
        assert co_review_roles("W1") == ["SEC"]

    def test_w4_only_sec_co(self) -> None:
        assert co_review_roles("W4") == ["SEC"]

    def test_w5_sme_and_sec_co(self) -> None:
        assert set(co_review_roles("W5")) == {"SME", "SEC"}

    def test_w3_no_co_review(self) -> None:
        assert co_review_roles("W3") == []


# ──────── 升级链 ────────


class TestEscalationChain:
    def test_aiops_escalates_to_sme(self) -> None:
        assert next_role_in_chain("AIOps") == "SME"

    def test_sme_escalates_to_dg(self) -> None:
        assert next_role_in_chain("SME") == "DG"

    def test_sec_escalates_to_dg(self) -> None:
        assert next_role_in_chain("SEC") == "DG"

    def test_dg_is_top_self_loop(self) -> None:
        """DG 是顶级，升级返回自己（调用方据此触发积压告警）。"""
        assert next_role_in_chain("DG") == "DG"
        assert is_top_role("DG") is True
        assert is_top_role("SME") is False

    def test_full_chain_from_aiops(self) -> None:
        """AIOps → SME → DG 完整 3 级链。"""
        assert escalation_chain("AIOps") == ["AIOps", "SME", "DG"]

    def test_full_chain_from_sec(self) -> None:
        """SEC 直接升级到 DG，2 级链。"""
        assert escalation_chain("SEC") == ["SEC", "DG"]

    def test_full_chain_from_dg(self) -> None:
        """DG 顶级，链只有自己。"""
        assert escalation_chain("DG") == ["DG"]


# ──────── 全枚举常量 ────────


class TestEnumerations:
    def test_all_workstations_six(self) -> None:
        assert len(ALL_WORKSTATIONS) == 6

    def test_all_roles_four(self) -> None:
        assert len(ALL_ROLES) == 4
        assert set(ALL_ROLES) == {"DG", "SME", "SEC", "AIOps"}
