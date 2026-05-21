"""治理 API — V15 Phase C + M1 4×6 矩阵审核台扩展。

端点:
  GET  /governance/queue            — 工单列表（M1 加 workstation / assigned_role 过滤）
  POST /governance/queue/{id}/decide   — 人工决策 (approve/reject/edit)
  POST /governance/queue/{id}/claim    — 角色认领 (M1 矩阵审核台)
  POST /governance/queue/{id}/escalate — 主动升级 (M1 D12)
  POST /governance/seed             — 灌入 demo 工单
  GET  /governance/health           — 治理健康面板
  GET  /governance/matrix           — 4×6 矩阵看板（M1 新增）
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from packages.common import get_logger
from packages.common.types import (
    GovernanceDecision,
    GovernanceQueueItem,
    ReviewerRole,
    Workstation,
)
from packages.governance.matrix import (
    ALL_ROLES,
    ALL_WORKSTATIONS,
    next_role_in_chain,
)
from packages.storage.domain_store import DomainStore
from packages.storage.governance_queue_store import GovernanceQueueStore
from packages.storage.wiki_store import WikiStore

from api.deps import (
    get_domain_store,
    get_governance_queue_store,
    get_graph_store,
    get_raw_store,
    get_wiki_store,
)
from packages.governance import get_agent
from packages.storage.graph_store import GraphStore
from packages.storage.raw_store import RawStore

log = get_logger("api.governance")

router = APIRouter(prefix="/governance", tags=["治理"])


class DecideBody(BaseModel):
    decision: GovernanceDecision
    resolver: str = "admin"


class ClaimBody(BaseModel):
    """M1 矩阵审核台 · 角色认领工单。"""
    claimer: str  # 认领人 user_id（前端从 UserContext 拿）


class EscalateBody(BaseModel):
    """M1 D12 SLA 主动升级。"""
    reason: str  # 升级原因（必填，回流训练 + 审计）


class HealthResponse(BaseModel):
    wiki_coverage: int       # 0-100
    rag_fallback_rate: int   # 0-100
    provenance_score: int    # 0-100
    queue_counts: dict[str, int]  # agent -> pending 数


class MatrixCell(BaseModel):
    """矩阵单格：(workstation, role) → 待办计数。"""
    workstation: str
    assigned_role: str
    count: int


class MatrixResponse(BaseModel):
    """4×6 矩阵看板响应。"""
    project_id: str
    cells: list[MatrixCell]                # 6 工位 × 4 角色 = 24 格 + uncategorized 桶
    total: int                              # 全部待办数（pending+reviewing+escalated）
    uncategorized: int                      # V15 既有 demo 不带工位的工单数


@router.get("/queue", response_model=list[GovernanceQueueItem])
async def list_queue(
    project_id: str,
    status: str | None = None,
    agent: str | None = None,
    workstation: str | None = None,
    assigned_role: str | None = None,
    store: GovernanceQueueStore = Depends(get_governance_queue_store),
) -> list[GovernanceQueueItem]:
    return await store.list(
        project_id, status=status, agent=agent,
        workstation=workstation, assigned_role=assigned_role,
    )


@router.post("/queue/{item_id}/decide", response_model=GovernanceQueueItem)
async def decide_queue_item(
    item_id: str,
    body: DecideBody,
    store: GovernanceQueueStore = Depends(get_governance_queue_store),
) -> GovernanceQueueItem:
    item = await store.decide(item_id, body.decision, body.resolver)
    if not item:
        raise HTTPException(status_code=404, detail="工单不存在")
    log.info("governance_item_decided", item_id=item_id, decision=body.decision, resolver=body.resolver)
    return item


@router.post("/queue/{item_id}/claim", response_model=GovernanceQueueItem)
async def claim_queue_item(
    item_id: str,
    body: ClaimBody,
    store: GovernanceQueueStore = Depends(get_governance_queue_store),
) -> GovernanceQueueItem:
    """M1 矩阵审核台 · 角色认领工单（pending → reviewing）。"""
    item = await store.claim(item_id, body.claimer)
    if not item:
        raise HTTPException(
            status_code=404,
            detail="工单不存在或已 resolved/escalated 不可认领",
        )
    log.info("governance_item_claimed", item_id=item_id, claimer=body.claimer)
    return item


@router.post("/queue/{item_id}/escalate", response_model=GovernanceQueueItem)
async def escalate_queue_item(
    item_id: str,
    body: EscalateBody,
    store: GovernanceQueueStore = Depends(get_governance_queue_store),
) -> GovernanceQueueItem:
    """M1 D12 主动升级（无 SLA 时长限制，由人工或 sla.sweep_overdue_tasks 触发）。"""
    item = await store.get(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="工单不存在")
    if item.assigned_role is None:
        raise HTTPException(status_code=400, detail="工单未指定 assigned_role，无法升级")

    target = next_role_in_chain(item.assigned_role)
    result = await store.escalate(item_id, body.reason, target)
    log.info(
        "governance_item_escalated",
        item_id=item_id, from_role=item.assigned_role, to_role=target,
    )
    return result


@router.get("/matrix", response_model=MatrixResponse)
async def matrix_view(
    project_id: str,
    store: GovernanceQueueStore = Depends(get_governance_queue_store),
) -> MatrixResponse:
    """M1 4×6 矩阵看板：返回每个 (工位, 角色) 格子的待办数。"""
    raw = await store.list_matrix(project_id)
    cells: list[MatrixCell] = []
    for ws in ALL_WORKSTATIONS:
        for role in ALL_ROLES:
            count = raw.get((ws, role), 0)
            if count > 0:
                cells.append(MatrixCell(workstation=ws, assigned_role=role, count=count))
    uncategorized = raw.get(("uncategorized", "uncategorized"), 0)
    total = sum(raw.values())
    return MatrixResponse(
        project_id=project_id,
        cells=cells,
        total=total,
        uncategorized=uncategorized,
    )


@router.post("/seed")
async def seed_queue(
    project_id: str,
    store: GovernanceQueueStore = Depends(get_governance_queue_store),
) -> dict[str, int]:
    n = await store.seed_demo(project_id)
    return {"seeded": n}


@router.get("/health", response_model=HealthResponse)
async def health(
    project_id: str,
    store: GovernanceQueueStore = Depends(get_governance_queue_store),
    wiki: WikiStore = Depends(get_wiki_store),
    domains: DomainStore = Depends(get_domain_store),
) -> HealthResponse:
    # Wiki 覆盖率: domain_overview 页数 / doc_count > 0 的域数
    try:
        pages = await wiki.list_pages(project_id, page_type="domain_overview")
        domain_list = domains.list_domains(project_id)
        denom = sum(1 for d in domain_list if getattr(d, "doc_count", 0) > 0) or 1
        wiki_coverage = min(100, int(len(pages) / denom * 100))
    except Exception as e:
        log.warning("health_wiki_coverage_failed", error=str(e))
        wiki_coverage = 0

    # 队列按 agent 计数（仅 pending）
    pending = await store.list(project_id, status="pending")
    queue_counts = {"curator": 0, "auditor": 0, "deduper": 0, "gardener": 0}
    for it in pending:
        queue_counts[it.agent] = queue_counts.get(it.agent, 0) + 1

    return HealthResponse(
        wiki_coverage=wiki_coverage,
        rag_fallback_rate=34,  # TODO Phase B+ 接查询日志
        provenance_score=91,   # TODO Auditor 实跑后接实数
        queue_counts=queue_counts,
    )


@router.post("/agents/{agent_name}/run")
async def run_agent(
    agent_name: str,
    project_id: str,
    store: GovernanceQueueStore = Depends(get_governance_queue_store),
    wiki: WikiStore = Depends(get_wiki_store),
    raw: RawStore = Depends(get_raw_store),
    graph: GraphStore = Depends(get_graph_store),
) -> dict:
    """V15 Phase I+K: 手动触发某个治理 Agent 执行，产出工单入 queue。"""
    try:
        agent = get_agent(agent_name)
    except ValueError as e:
        raise HTTPException(400, str(e))

    result = await agent.run(
        project_id=project_id,
        queue_store=store,
        wiki_store=wiki,
        raw_store=raw,
        graph_store=graph,
    )
    log.info("governance_agent_run_invoked",
             agent=agent_name, project=project_id,
             scanned=result.scanned, produced=result.produced,
             ok=result.ok, errors=len(result.errors))
    return result.to_dict()


# ── M22 #5 · 实体消歧合并决策 ──────────────────────────


class EntityMergeDecisionBody(BaseModel):
    """SME 对实体合并候选对的决策。

    M22 #9 修 codex HIGH #3: D12 闭环硬化, 必须绑定 governance queue item +
    SME 认领校验 + type_id 服务端复核, 不允许裸写决策日志。
    """
    project_id: str
    queue_item_id: str = Field(
        ..., min_length=1,
        description="必填: 4×6 矩阵 governance queue item id, 候选对必须先入队让 SME 认领",
    )
    entity_a_id: str = Field(..., min_length=1)
    entity_b_id: str = Field(..., min_length=1)
    # M22 #9: 服务端复核两侧 type_id 必须一致（防绕过 entity_resolver 的"不同 type 不合并"约束）
    entity_a_type_id: str = Field(..., min_length=1)
    entity_b_type_id: str = Field(..., min_length=1)
    decision: str = Field(..., description="approve / reject")
    actor: str = Field(..., min_length=1, description="SME user_id, 必须与 queue item.claimed_by 一致")
    note: str = ""


class EntityMergeDecisionResponse(BaseModel):
    status: str = "ok"
    decision_type: str
    target_id: str
    project_id: str
    actor: str
    queue_item_id: str
    queue_resolved: bool = False  # 决策同时把工单 resolve


@router.post("/entity-merge-decision", response_model=EntityMergeDecisionResponse)
async def entity_merge_decision(
    body: EntityMergeDecisionBody,
    store: GovernanceQueueStore = Depends(get_governance_queue_store),
) -> EntityMergeDecisionResponse:
    """M22 #5+#9 · SME 对实体合并候选对的最终仲裁（D12 闭环硬校验版）。

    工作流（决策书 D12 人工兜底）:
      1. entity_resolver.find_merge_candidates 产出 MergeCandidate 列表
      2. caller 把候选对入 4×6 矩阵审核台（W6 / SME 队列）→ 产生 queue_item_id
      3. SME 经 /governance/queue/{id}/claim 认领工单
      4. SME 经 UI 审核, 点 "同意合并" / "拒绝合并", 前端调本端点
      5. 本端点 5 层强校验后才写决策日志（entity_merge_approved/rejected）
      6. 实际图谱合并由后置任务消费**已校验过**的决策日志执行

    5 层强校验（M22 #9 加固, 绕过任一层都会 4xx）:
      L1 decision ∈ {approve, reject}
      L2 queue item 存在 + project_id 匹配
      L3 工单 assigned_role == SME（不允许其他角色仲裁）
      L4 工单 claimed_by == actor（认领人才能 decide, 防越权）
      L5 entity_a_type_id == entity_b_type_id（防绕过 resolver "不同 type 不合并"）
    """
    from packages.observability.decision_log import arecord_decision

    # L1: decision 取值
    decision = (body.decision or "").lower()
    if decision not in ("approve", "reject"):
        raise HTTPException(
            status_code=400,
            detail="decision 必须为 approve 或 reject",
        )

    # L5 先做（不依赖外部存储, 失败立刻拒）: type_id 一致
    if body.entity_a_type_id != body.entity_b_type_id:
        raise HTTPException(
            status_code=400,
            detail=f"entity_a/b type_id 不一致 ({body.entity_a_type_id} vs "
                   f"{body.entity_b_type_id}), 违反 resolver '不同 type 不合并' 约束",
        )

    # L2: queue item 存在
    item = await store.get(body.queue_item_id)
    if item is None:
        raise HTTPException(
            status_code=404,
            detail=f"queue item {body.queue_item_id} 不存在; "
                   f"实体合并候选对必须先入 4×6 矩阵审核台",
        )
    if item.project_id != body.project_id:
        raise HTTPException(
            status_code=400,
            detail=f"queue item.project_id={item.project_id} 与 body.project_id="
                   f"{body.project_id} 不匹配",
        )

    # L3: assigned_role == SME
    if item.assigned_role != "SME":
        raise HTTPException(
            status_code=403,
            detail=f"工单 assigned_role={item.assigned_role}, 实体合并仲裁仅限 SME 角色",
        )

    # L4: claimer 一致
    if not item.claimed_by:
        raise HTTPException(
            status_code=409,
            detail="工单未被认领, 请先 /governance/queue/{id}/claim 认领后再仲裁",
        )
    if item.claimed_by != body.actor:
        raise HTTPException(
            status_code=403,
            detail=f"工单认领人={item.claimed_by} 与 actor={body.actor} 不一致, "
                   f"仅认领人可仲裁",
        )

    # 工单已 resolved 则拒绝（防重放）
    if item.status not in ("pending", "reviewing", "claimed"):
        raise HTTPException(
            status_code=409,
            detail=f"工单 status={item.status} 已终态, 不允许重复仲裁",
        )

    # 全部校验过 → 写决策日志
    decision_type = (
        "entity_merge_approved" if decision == "approve"
        else "entity_merge_rejected"
    )
    target_id = f"{body.entity_a_id}::{body.entity_b_id}"

    note_parts = [
        f"queue={body.queue_item_id}",
        f"a={body.entity_a_id}",
        f"b={body.entity_b_id}",
        f"type={body.entity_a_type_id}",
    ]
    if body.note:
        note_parts.append(body.note[:200])
    note = " | ".join(note_parts)

    event = await arecord_decision(
        project_id=body.project_id,
        decision_type=decision_type,  # type: ignore[arg-type]
        actor=body.actor,
        target_id=target_id,
        note=note,
    )

    # 同步把工单标 resolve
    queue_resolved = False
    try:
        await store.decide(
            body.queue_item_id,
            "approve" if decision == "approve" else "reject",
            body.actor,
        )
        queue_resolved = True
    except Exception as e:
        log.warning("entity_merge_queue_resolve_failed",
                    item_id=body.queue_item_id, error=str(e))

    log.info(
        "entity_merge_decision_recorded",
        project=body.project_id,
        decision=decision_type,
        target=target_id,
        actor=body.actor,
        queue_item=body.queue_item_id,
        queue_resolved=queue_resolved,
    )

    return EntityMergeDecisionResponse(
        status="ok",
        decision_type=decision_type,
        target_id=target_id,
        project_id=body.project_id,
        actor=event.actor,
        queue_item_id=body.queue_item_id,
        queue_resolved=queue_resolved,
    )
