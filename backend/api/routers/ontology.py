"""M3 #1 双层本体 API（决策书 §5.3 D8/D9）。

端点：
  GET  /ontology/{layer}                查询当前生效版本（L1/L2）
  GET  /ontology/versions               列出版本历史
  GET  /ontology/diff                   对比两版本
  POST /ontology/proposals/scan         手动触发演化扫描
  GET  /ontology/proposals              列出提议
  POST /ontology/proposals/{id}/approve SME 批准 → 写入 L2 新版本
  POST /ontology/proposals/{id}/reject  SME 驳回

权限：
  GET 端点 RequireRole(DG/SME/AIOps/READER)（只读，开放）
  POST scan/approve/reject RequireRole(SME)（决策书 §5.3 SME 主导本体演化）
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from packages.common import get_logger
from packages.common.auth import UserContext
from packages.common.roles import ROLE_SME, RequireRole
from packages.observability import arecord_decision
from packages.common.types import (
    GovernanceQueueItem,
    OntologyDiff,
    OntologyEntityType,
    OntologyEvolutionProposal,
    OntologyLayer,
    OntologyVersion,
)
from packages.ontology import get_current_l1, get_current_l2, get_ontology_store
from packages.ontology.evolution_proposer import (
    collect_unmatched_entities,
    propose_new_entity_type,
)

log = get_logger("api.ontology")

router = APIRouter(prefix="/ontology", tags=["双层本体"])


# ════════════════════════════════════════════════════════════════════════
#  内存提议存储（M3 lite；M4 落 PG）
# ════════════════════════════════════════════════════════════════════════


_proposal_store: dict[str, OntologyEvolutionProposal] = {}


def reset_proposal_store_for_test() -> None:
    _proposal_store.clear()


# ════════════════════════════════════════════════════════════════════════
#  Schemas
# ════════════════════════════════════════════════════════════════════════


class ScanBody(BaseModel):
    industry_code: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    candidate_entity_names: list[str] = Field(default_factory=list)
    threshold: int = 50


class ResolveBody(BaseModel):
    reason: str = Field(default="", max_length=500)


# ════════════════════════════════════════════════════════════════════════
#  GET /ontology/versions/list （路由顺序：放在 /{layer} 之前避免 path param 拦截）
# ════════════════════════════════════════════════════════════════════════


@router.get("/versions/list")
async def list_versions(
    layer: Literal["L1", "L2"],
    industry_code: str = Query(default=""),
    project_id: str = Query(default=""),
) -> list[dict]:
    store = get_ontology_store()
    versions = store.list_versions(
        layer, industry_code=industry_code, project_id=project_id,
    )
    return [v.model_dump() for v in versions]


# ════════════════════════════════════════════════════════════════════════
#  GET /ontology/diff
# ════════════════════════════════════════════════════════════════════════


@router.get("/diff/compare", response_model=OntologyDiff)
async def diff_versions(
    layer: Literal["L1", "L2"],
    from_version: str = Query(..., alias="from"),
    to_version: str = Query(..., alias="to"),
    industry_code: str = Query(default=""),
    project_id: str = Query(default=""),
) -> OntologyDiff:
    store = get_ontology_store()
    key = industry_code if layer == "L1" else project_id
    if not key:
        raise HTTPException(400, f"{layer} diff 需要 industry_code 或 project_id")
    before = store.get_version(layer, key, from_version)
    after = store.get_version(layer, key, to_version)
    if before is None or after is None:
        raise HTTPException(404, "版本不存在")
    return store.diff(before, after)


# ════════════════════════════════════════════════════════════════════════
#  GET /ontology/{layer} （放在 /proposals 等具体路由之后）
#  注意：/{layer} 必须放在 /proposals 等子路由之后，否则会拦截
# ════════════════════════════════════════════════════════════════════════


# 占位：实际定义见文件末尾


# ════════════════════════════════════════════════════════════════════════
#  POST /ontology/proposals/scan
# ════════════════════════════════════════════════════════════════════════


@router.post("/proposals/scan")
async def trigger_scan(
    body: ScanBody,
    user=Depends(RequireRole(ROLE_SME)),
) -> dict:
    """手动触发演化扫描（决策书 §5.3 SME 主导）。

    候选实体名由调用方传入（M3 lite；M4 后端从 graph_store 自动采集）。
    """
    batch = collect_unmatched_entities(
        industry_code=body.industry_code,
        project_id=body.project_id,
        candidate_entity_names=body.candidate_entity_names,
        threshold=body.threshold,
    )
    if batch is None:
        return {"triggered": False, "reason": "未达阈值或无候选"}

    proposal = await propose_new_entity_type(batch)
    if proposal is None:
        return {
            "triggered": True,
            "proposal_created": False,
            "reason": "LLM 失败 / 置信度过低，不入审核台",
        }

    _proposal_store[proposal.proposal_id] = proposal

    # 写入 4×6 矩阵审核台（W4-SME 格子）
    queue_item_id = ""
    try:
        from api.deps import get_governance_queue_store
        from packages.governance.matrix import primary_role_for
        gq = get_governance_queue_store()
        et = proposal.proposed_entity_type
        item = GovernanceQueueItem(
            id=f"gq_{uuid.uuid4().hex[:10]}",
            project_id=body.project_id,
            agent="ontology_evolution",  # type: ignore[arg-type]
            kind="ontology_proposal",  # type: ignore[arg-type]
            title=f"[本体演化] 提议新实体类型: {et.type_name if et else '?'}",
            description=(
                f"证据 {batch.total_count} 个未匹配实体；"
                f"理由: {proposal.reasoning[:120]}；"
                f"样本: {', '.join(batch.sample_names[:5])}"
            ),
            target_ref=f"ontology/{proposal.proposal_id}",
            priority=70,
            status="pending",
            created_at=datetime.now(timezone.utc),
            workstation="W4",
            assigned_role=primary_role_for("W4"),  # SME
        )
        await gq.upsert(item)
        queue_item_id = item.id
    except Exception as e:
        log.warning("ontology_proposal_queue_failed", error=str(e))

    log.info("ontology_proposal_created",
             proposal_id=proposal.proposal_id,
             user=getattr(user, "user_id", "?"),
             queue_item=queue_item_id)
    return {
        "triggered": True,
        "proposal_created": True,
        "proposal_id": proposal.proposal_id,
        "evidence_count": batch.total_count,
        "queue_item_id": queue_item_id,
    }


# ════════════════════════════════════════════════════════════════════════
#  GET /ontology/proposals
# ════════════════════════════════════════════════════════════════════════


@router.get("/proposals")
async def list_proposals(
    project_id: str = Query(...),
    status: str | None = Query(default=None),
) -> list[dict]:
    out = [
        p.model_dump() for p in _proposal_store.values()
        if p.project_id == project_id
        and (status is None or p.status == status)
    ]
    out.sort(key=lambda p: p["created_at"], reverse=True)
    return out


# ════════════════════════════════════════════════════════════════════════
#  POST /ontology/proposals/{id}/approve
# ════════════════════════════════════════════════════════════════════════


@router.post("/proposals/{proposal_id}/approve")
async def approve_proposal(
    proposal_id: str,
    body: ResolveBody = Body(default_factory=ResolveBody),
    user=Depends(RequireRole(ROLE_SME)),
) -> dict:
    """SME 批准 → 把新实体类型加入 L2 当前版本（patch bump）。"""
    proposal = _proposal_store.get(proposal_id)
    if proposal is None:
        raise HTTPException(404, "proposal 不存在")
    if proposal.status != "pending":
        raise HTTPException(400, f"proposal 已 {proposal.status}，不可重复批准")
    if proposal.proposed_entity_type is None:
        raise HTTPException(400, "proposal 无可应用内容")

    store = get_ontology_store()
    next_v = store.create_next_version(
        "L2",
        project_id=proposal.project_id,
        bump="patch",
        notes=f"批准本体演化提议 {proposal_id}：{body.reason or proposal.reasoning[:80]}",
        created_by=getattr(user, "user_id", ""),
    )
    next_v.entity_types.append(proposal.proposed_entity_type)
    store.save_version(next_v)

    proposal.status = "approved"
    proposal.resolver = getattr(user, "user_id", "")
    proposal.resolved_at = datetime.now(timezone.utc)

    log.info(
        "ontology_proposal_approved",
        proposal_id=proposal_id, new_version=next_v.version,
        user=getattr(user, "user_id", "?"),
    )
    await arecord_decision(
        project_id=proposal.project_id,
        decision_type="approve_proposal",
        actor=getattr(user, "user_id", ""),
        target_id=proposal_id,
        note=f"new_version={next_v.version}",
    )
    return {
        "proposal_id": proposal_id,
        "status": "approved",
        "new_version": next_v.version,
    }


# ════════════════════════════════════════════════════════════════════════
#  POST /ontology/proposals/{id}/reject
# ════════════════════════════════════════════════════════════════════════


@router.post("/proposals/{proposal_id}/reject")
async def reject_proposal(
    proposal_id: str,
    body: ResolveBody = Body(default_factory=ResolveBody),
    user=Depends(RequireRole(ROLE_SME)),
) -> dict:
    proposal = _proposal_store.get(proposal_id)
    if proposal is None:
        raise HTTPException(404, "proposal 不存在")
    if proposal.status != "pending":
        raise HTTPException(400, f"proposal 已 {proposal.status}")

    proposal.status = "rejected"
    proposal.resolver = getattr(user, "user_id", "")
    proposal.resolved_at = datetime.now(timezone.utc)
    proposal.reasoning = f"{proposal.reasoning} | SME 驳回: {body.reason or '无理由'}"
    log.info(
        "ontology_proposal_rejected",
        proposal_id=proposal_id, user=getattr(user, "user_id", "?"),
    )
    await arecord_decision(
        project_id=proposal.project_id,
        decision_type="reject_proposal",
        actor=getattr(user, "user_id", ""),
        target_id=proposal_id,
        note=body.reason or "",
    )
    return {"proposal_id": proposal_id, "status": "rejected"}


# ════════════════════════════════════════════════════════════════════════
#  GET /ontology/{layer}（放最后，避免 path param 拦截 /proposals 等）
# ════════════════════════════════════════════════════════════════════════


@router.get("/{layer}")
async def get_current_ontology(
    layer: Literal["L1", "L2"],
    industry_code: str = Query(default=""),
    project_id: str = Query(default=""),
) -> dict:
    """查询当前生效版本（L1 by industry / L2 by project）。"""
    if layer == "L1":
        if not industry_code:
            raise HTTPException(400, "L1 查询需 industry_code")
        v = get_current_l1(industry_code)
    else:
        if not project_id:
            raise HTTPException(400, "L2 查询需 project_id")
        v = get_current_l2(project_id)
    if v is None:
        raise HTTPException(404, f"{layer} 本体未注册")
    return v.model_dump()
