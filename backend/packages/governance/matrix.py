"""M1 矩阵审核台 · 4 角色 × 6 工位 R/C/I 分工矩阵（决策书 §5.2 D6 表的代码化）。

来源即真相：本文件就是决策书 §5.2 那张表的可执行版本，改动需走变更评审。

| 工位     | DG       | SME           | SEC                | AIOps           |
|:--------:|:--------:|:-------------:|:------------------:|:---------------:|
| W1 解析  | R        | I             | C(脱敏标记)        | I               |
| W2 归类  | R        | C(跨域)       | C(密级)            | I               |
| W3 切块  | R        | I             | I                  | I               |
| W4 抽取  | I        | **R(必审)**   | C(敏感实体)        | I               |
| W5 入库  | R(合并)  | C(冲突)       | C(权限映射)        | I               |
| W6 监控  | I        | R(知识缺口)   | C(泄露排查)        | R(命中率)       |

D12 升级链（SLA 超时不允许 LLM 自动通过）：
  AIOps → SME → DG ↑ 顶级（继续超时触发"积压告警"）
  SME   → DG  ↑ 顶级
  SEC   → DG  ↑ 顶级
  DG    → DG  ↑ 顶级
"""

from __future__ import annotations

from packages.common.types import ReviewerInvolvement, ReviewerRole, Workstation


# ════════════════════════════════════════════════════════════════════════
#  4×6 R/C/I 矩阵（决策书 §5.2 表）
# ════════════════════════════════════════════════════════════════════════

ROLE_WORKSTATION_MATRIX: dict[tuple[Workstation, ReviewerRole], ReviewerInvolvement] = {
    # W1 解析 — DG 主审，SEC 协审脱敏标记
    ("W1", "DG"): "R",   ("W1", "SME"): "I",   ("W1", "SEC"): "C",   ("W1", "AIOps"): "I",
    # W2 归类 — DG 主审，SME 跨域协审、SEC 密级协审
    ("W2", "DG"): "R",   ("W2", "SME"): "C",   ("W2", "SEC"): "C",   ("W2", "AIOps"): "I",
    # W3 切块 — DG 主审
    ("W3", "DG"): "R",   ("W3", "SME"): "I",   ("W3", "SEC"): "I",   ("W3", "AIOps"): "I",
    # W4 实体抽取 — SME 必审（核心研发知识），SEC 敏感实体协审
    ("W4", "DG"): "I",   ("W4", "SME"): "R",   ("W4", "SEC"): "C",   ("W4", "AIOps"): "I",
    # W5 入库双写 — DG 合并主审，SME 冲突协审，SEC 权限映射协审
    ("W5", "DG"): "R",   ("W5", "SME"): "C",   ("W5", "SEC"): "C",   ("W5", "AIOps"): "I",
    # W6 消费监控 — SME 知识缺口主审 + AIOps 命中率主审（双 R），SEC 泄露排查协审
    ("W6", "DG"): "I",   ("W6", "SME"): "R",   ("W6", "SEC"): "C",   ("W6", "AIOps"): "R",
}


def involvement_for(workstation: Workstation, role: ReviewerRole) -> ReviewerInvolvement:
    """返回某个角色在某个工位的参与度 (R/C/I)。"""
    return ROLE_WORKSTATION_MATRIX[(workstation, role)]


def primary_role_for(workstation: Workstation) -> ReviewerRole:
    """返回该工位的主审角色（R）。

    W6 例外：SME 与 AIOps 都是 R（知识缺口 / 命中率分工）；
    本函数按"工单是 AI 自动产出"的默认策略，W6 优先返回 SME（知识缺口工单更常见）。
    工单产出方按需指定 assigned_role 覆盖。
    """
    if workstation == "W6":
        return "SME"
    primaries = [r for (w, r), inv in ROLE_WORKSTATION_MATRIX.items()
                 if w == workstation and inv == "R"]
    if not primaries:
        raise ValueError(f"工位 {workstation} 无 R 主审，矩阵定义错误")
    return primaries[0]


def co_review_roles(workstation: Workstation) -> list[ReviewerRole]:
    """返回该工位的协审角色列表（C）。"""
    return [r for (w, r), inv in ROLE_WORKSTATION_MATRIX.items()
            if w == workstation and inv == "C"]


# ════════════════════════════════════════════════════════════════════════
#  D12 升级链（SLA 超时不允许 LLM 自动通过）
# ════════════════════════════════════════════════════════════════════════

# 角色 → 上级角色（DG 是顶级，超时只能持续告警）
_ESCALATION_MAP: dict[ReviewerRole, ReviewerRole] = {
    "AIOps": "SME",
    "SEC": "DG",
    "SME": "DG",
    "DG": "DG",
}


def next_role_in_chain(role: ReviewerRole) -> ReviewerRole:
    """返回升级链上的下一个角色（DG 已顶级时仍返回 DG，调用方据此触发"积压告警"）。"""
    return _ESCALATION_MAP[role]


def escalation_chain(role: ReviewerRole) -> list[ReviewerRole]:
    """返回完整升级链（从当前到 DG）。"""
    chain: list[ReviewerRole] = [role]
    cur = role
    while True:
        nxt = next_role_in_chain(cur)
        if nxt == cur:
            break
        chain.append(nxt)
        cur = nxt
    return chain


def is_top_role(role: ReviewerRole) -> bool:
    """是否已升级到顶级（DG）。"""
    return next_role_in_chain(role) == role


# ════════════════════════════════════════════════════════════════════════
#  4×6 矩阵全枚举（用于矩阵看板 GET /governance/matrix）
# ════════════════════════════════════════════════════════════════════════

ALL_WORKSTATIONS: tuple[Workstation, ...] = ("W1", "W2", "W3", "W4", "W5", "W6")
ALL_ROLES: tuple[ReviewerRole, ...] = ("DG", "SME", "SEC", "AIOps")
