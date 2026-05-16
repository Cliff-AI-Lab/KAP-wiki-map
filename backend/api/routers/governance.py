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
from pydantic import BaseModel

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
    """SME 对实体合并候选对的决策。"""
    project_id: str
    candidate_id: str = ""  # entity_a_id::entity_b_id 形式; 也可为 governance queue item_id
    entity_a_id: str
    entity_b_id: str
    decision: str  # approve / reject
    actor: str = "admin"
    note: str = ""


class EntityMergeDecisionResponse(BaseModel):
    status: str = "ok"
    decision_type: str
    target_id: str
    project_id: str
    actor: str


@router.post("/entity-merge-decision", response_model=EntityMergeDecisionResponse)
async def entity_merge_decision(body: EntityMergeDecisionBody) -> EntityMergeDecisionResponse:
    """M22 #5 · SME 对实体合并候选对的最终仲裁。

    工作流:
      1. extraction.entity_resolver.find_merge_candidates 产出 MergeCandidate 列表
      2. caller 把候选对入 4×6 矩阵审核台（W6 / SME 队列）
      3. SME 经 UI 审核, 点 "同意合并" 或 "拒绝合并", 前端调本端点
      4. 本端点写决策日志（entity_merge_approved / entity_merge_rejected）
      5. 实际图谱合并由后置任务读决策日志执行（M22 #5 lite 不动图）
    """
    from packages.observability.decision_log import arecord_decision

    decision = (body.decision or "").lower()
    if decision not in ("approve", "reject"):
        raise HTTPException(
            status_code=400,
            detail="decision 必须为 approve 或 reject",
        )

    decision_type = (
        "entity_merge_approved" if decision == "approve"
        else "entity_merge_rejected"
    )
    target_id = body.candidate_id or f"{body.entity_a_id}::{body.entity_b_id}"

    note_parts = [f"a={body.entity_a_id}", f"b={body.entity_b_id}"]
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

    log.info(
        "entity_merge_decision_recorded",
        project=body.project_id,
        decision=decision_type,
        target=target_id,
        actor=body.actor,
    )

    return EntityMergeDecisionResponse(
        status="ok",
        decision_type=decision_type,
        target_id=target_id,
        project_id=body.project_id,
        actor=event.actor,
    )
