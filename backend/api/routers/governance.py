"""治理 API — V15 Phase C.

端点:
  GET  /governance/queue     — 工单列表(按 project_id 过滤，可选 status / agent)
  POST /governance/queue/{id}/decide — 人工决策 (approve/reject/edit)
  POST /governance/seed      — 灌入 demo 工单
  GET  /governance/health    — 治理健康面板(Wiki 覆盖率 / 兜底率 / 溯源完整度 / 队列计数)
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from packages.common import get_logger
from packages.common.types import GovernanceDecision, GovernanceQueueItem
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


class HealthResponse(BaseModel):
    wiki_coverage: int       # 0-100
    rag_fallback_rate: int   # 0-100
    provenance_score: int    # 0-100
    queue_counts: dict[str, int]  # agent -> pending 数


@router.get("/queue", response_model=list[GovernanceQueueItem])
async def list_queue(
    project_id: str,
    status: str | None = None,
    agent: str | None = None,
    store: GovernanceQueueStore = Depends(get_governance_queue_store),
) -> list[GovernanceQueueItem]:
    return await store.list(project_id, status=status, agent=agent)


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
