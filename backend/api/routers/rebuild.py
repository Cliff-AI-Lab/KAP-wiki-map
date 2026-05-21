"""M4 全量重抽影子库 API（决策书 §5.3）。

端点：
  POST /api/v1/rebuild/jobs            启动重抽（target_ontology_version + 可选 chunks）
  GET  /api/v1/rebuild/jobs            列出 RebuildJob
  GET  /api/v1/rebuild/jobs/{id}       查询状态 + 进度
  GET  /api/v1/rebuild/diff            对比两版本（query: source/target/project）
  POST /api/v1/rebuild/promote         SME 灰度切换
  POST /api/v1/rebuild/rollback        一键回滚

权限（决策书 §5.3 SME 主导）：
- GET 端点：开放查询
- POST 端点：RequireRole(SME)
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from packages.common import get_logger
from packages.common.roles import ROLE_SME, RequireRole
from packages.observability import arecord_decision
from packages.common.types import (
    PromotionObservation,
    RebuildDiffReport,
    RebuildJob,
)
from packages.rebuild import (
    PromoteRefused,
    arun_rebuild,
    compare_versions,
    get_current_observation,
    get_job,
    list_jobs,
    list_observations,
    promote_shadow,
    rollback_promotion,
    start_rebuild,
    tick_all_observations,
    tick_observation,
)

log = get_logger("api.rebuild")

router = APIRouter(prefix="/rebuild", tags=["全量重抽影子库"])


# ════════════════════════════════════════════════════════════════════════
#  Schemas
# ════════════════════════════════════════════════════════════════════════


class StartRebuildBody(BaseModel):
    project_id: str = Field(min_length=1)
    source_version: str = Field(min_length=1)
    target_version: str = Field(min_length=1)
    industry_code: str = Field(min_length=1)
    chunks: list[dict] = Field(default_factory=list)
    """每项 {chunk_id, doc_id, content}。M4 lite 由调用方传入；
    M5 后端自动从 vector_store 拉取。"""


class PromoteBody(BaseModel):
    project_id: str = Field(min_length=1)
    source_version: str = Field(min_length=1)
    target_version: str = Field(min_length=1)
    force: bool = False


class RollbackBody(BaseModel):
    project_id: str = Field(min_length=1)


# ════════════════════════════════════════════════════════════════════════
#  POST /rebuild/jobs — 启动重抽
# ════════════════════════════════════════════════════════════════════════


@router.post("/jobs", response_model=RebuildJob)
async def start_job(
    body: StartRebuildBody,
    user=Depends(RequireRole(ROLE_SME)),
) -> RebuildJob:
    """启动重抽任务（同步执行，M4 lite；M5 接 iss-job 后台调度）。"""
    job = start_rebuild(body.project_id, body.source_version, body.target_version)
    # M4 lite 同步跑（小批量场景 OK）；M5 改后台 task
    try:
        await arun_rebuild(
            job, chunks=body.chunks, industry_code=body.industry_code,
        )
    except Exception as e:
        log.error("rebuild_job_aborted", job_id=job.job_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"重抽失败: {e}") from e
    log.info("rebuild_job_completed",
             job_id=job.job_id, user=getattr(user, "user_id", "?"),
             extracted=job.chunks_extracted, hash_hit=job.chunks_hash_hit)
    return job


# ════════════════════════════════════════════════════════════════════════
#  GET /rebuild/jobs — 列出
# ════════════════════════════════════════════════════════════════════════


@router.get("/jobs", response_model=list[RebuildJob])
async def list_rebuild_jobs(
    project_id: str | None = Query(default=None),
) -> list[RebuildJob]:
    return list_jobs(project_id)


# ════════════════════════════════════════════════════════════════════════
#  GET /rebuild/jobs/{id} — 单条
# ════════════════════════════════════════════════════════════════════════


@router.get("/jobs/{job_id}", response_model=RebuildJob)
async def get_rebuild_job(job_id: str) -> RebuildJob:
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job 不存在")
    return job


# ════════════════════════════════════════════════════════════════════════
#  GET /rebuild/diff — 对比两版本
# ════════════════════════════════════════════════════════════════════════


@router.get("/diff", response_model=RebuildDiffReport)
async def diff_rebuild(
    project_id: str = Query(...),
    source_version: str = Query(..., alias="source"),
    target_version: str = Query(..., alias="target"),
) -> RebuildDiffReport:
    return compare_versions(project_id, source_version, target_version)


# ════════════════════════════════════════════════════════════════════════
#  POST /rebuild/promote — 灰度切换
# ════════════════════════════════════════════════════════════════════════


@router.post("/promote", response_model=RebuildDiffReport)
async def promote(
    body: PromoteBody,
    user=Depends(RequireRole(ROLE_SME)),
) -> RebuildDiffReport:
    """SME 切换影子库到主图谱（决策书 §5.3）。"""
    try:
        report = promote_shadow(
            body.project_id, body.source_version, body.target_version,
            force=body.force,
        )
    except PromoteRefused as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    log.info("rebuild_promoted",
             project_id=body.project_id, target=body.target_version,
             forced=body.force, user=getattr(user, "user_id", "?"))
    await arecord_decision(
        project_id=body.project_id,
        decision_type="promote",
        actor=getattr(user, "user_id", ""),
        target_id=body.target_version,
        note=f"force={body.force} safe={report.safe_to_promote}",
    )
    return report


# ════════════════════════════════════════════════════════════════════════
#  POST /rebuild/rollback — 一键回滚
# ════════════════════════════════════════════════════════════════════════


@router.post("/rollback")
async def rollback(
    body: RollbackBody,
    user=Depends(RequireRole(ROLE_SME)),
) -> dict[str, Any]:
    rolled = rollback_promotion(body.project_id)
    if rolled is None:
        raise HTTPException(status_code=400, detail="无可回滚版本")
    log.info("rebuild_rolled_back",
             project_id=body.project_id, version=rolled,
             user=getattr(user, "user_id", "?"))
    await arecord_decision(
        project_id=body.project_id,
        decision_type="rollback",
        actor=getattr(user, "user_id", ""),
        target_id=rolled,
    )
    return {"project_id": body.project_id, "rolled_back_to": rolled}


# ════════════════════════════════════════════════════════════════════════
#  M5 #2 · 观察期 (decision book §5.3 7 天)
# ════════════════════════════════════════════════════════════════════════


@router.get("/observations", response_model=list[PromotionObservation])
async def list_promotion_observations(
    project_id: str | None = Query(default=None),
) -> list[PromotionObservation]:
    """列出观察期记录（含 baseline / 历史快照 / 告警）。"""
    return list_observations(project_id)


@router.get("/observations/current", response_model=PromotionObservation)
async def get_current_observation_endpoint(
    project_id: str = Query(...),
) -> PromotionObservation:
    obs = get_current_observation(project_id)
    if obs is None:
        raise HTTPException(status_code=404, detail="该项目无活跃观察期")
    return obs


@router.post("/observations/tick-all", response_model=list[PromotionObservation])
async def tick_all_observations_endpoint(
    user=Depends(RequireRole(ROLE_SME)),
) -> list[PromotionObservation]:
    """批量 tick 所有活跃观察期（M6 #2 · 外部 cron / ISS-Job 入口）。

    给定时器 / Quartz 调度器一次性触发的端点，避免逐项目轮询。
    返回每个被 tick 的观察期最新状态（含 watching / alert / expired）。
    """
    out = tick_all_observations()
    log.info(
        "observations_ticked_all",
        count=len(out),
        alerts=sum(1 for o in out if o.status == "alert"),
        user=getattr(user, "user_id", "?"),
    )
    return out


@router.post("/observations/tick", response_model=PromotionObservation)
async def tick_observation_endpoint(
    body: RollbackBody,
    user=Depends(RequireRole(ROLE_SME)),
) -> PromotionObservation:
    """手动触发一次观察期采样 + 检查（M5 lite，M5 完整版接定时器）。"""
    obs = tick_observation(body.project_id)
    if obs is None:
        raise HTTPException(status_code=404, detail="该项目无活跃观察期")
    log.info("observation_ticked",
             project_id=body.project_id, status=obs.status,
             alerts=len(obs.alerts), user=getattr(user, "user_id", "?"))
    return obs


# ════════════════════════════════════════════════════════════════════════
#  M6 #1 · as_of 时光机查询（决策书 §5.3）
# ════════════════════════════════════════════════════════════════════════


@router.get("/as-of")
async def query_as_of(
    project_id: str = Query(...),
    version: str = Query(...),
    before: datetime = Query(...,
        description="ISO8601 时间点，返回该时刻之前已存在的实体/关系"),
) -> dict[str, Any]:
    """返回某 (project, version) 在指定时间点的图谱快照。

    用途：合规审计、`这个事实是什么时候记录的`、回放 promote 之前的状态。
    """
    from packages.rebuild import get_shadow_store
    s = get_shadow_store()
    return {
        "project_id": project_id,
        "version": version,
        "as_of": before.isoformat(),
        "entities": s.entities_as_of(project_id, version, before),
        "relations": s.relations_as_of(project_id, version, before),
    }


# ════════════════════════════════════════════════════════════════════════
#  M22 #7 · 增量重抽 lite — 影响面分析 + RebuildPlan dry-run
# ════════════════════════════════════════════════════════════════════════


class IncrementalRebuildBody(BaseModel):
    """增量重抽请求（M22 #9 codex HIGH #5 加固后）。

    diff 数据来源两种：
    1. caller 显式传入 added/removed/modified 字段（dev / 离线工具用）
    2. 留空时端点尝试从 OntologyRegistry 自动解析（M22 #7 lite 阶段未对接）
    """
    project_id: str = Field(..., min_length=1, max_length=64)
    version_from: str = Field(..., min_length=1, max_length=64)
    version_to: str = Field(..., min_length=1, max_length=64)
    l1_changed: bool = False
    dry_run: bool = True

    # M22 #9 codex HIGH #5: 显式 diff 字段（dev / CLI 用）
    added_entity_types: list[str] = Field(default_factory=list, max_length=200)
    removed_entity_types: list[str] = Field(default_factory=list, max_length=200)
    modified_entity_types: list[str] = Field(default_factory=list, max_length=200)
    added_relation_types: list[str] = Field(default_factory=list, max_length=200)
    removed_relation_types: list[str] = Field(default_factory=list, max_length=200)
    modified_relation_types: list[str] = Field(default_factory=list, max_length=200)

    # M22 #9 codex LOW: doc_to_types_override 加规模上限防 OOM
    doc_to_types_override: dict[str, list[str]] | None = Field(
        default=None,
        description="{doc_id → [entity_type_ids]}; 最多 10000 docs, 每 doc 最多 200 types",
    )
    doc_to_relations_override: dict[str, list[str]] | None = Field(
        default=None,
        description="{doc_id → [relation_type_ids]}; M22 #9 加, 让关系 diff 参与影响面",
    )


@router.post("/incremental")
async def incremental_rebuild(body: IncrementalRebuildBody) -> dict:
    """M22 #7+#9 · 增量重抽 lite — 基于本体 diff 输出 RebuildPlan。

    工作流:
      1. 取 OntologyDiff（caller 显式 diff 字段 / 留空走 lite 模式）
      2. 拉 doc → type_ids + doc → relation_ids 索引（M22 #9 加关系映射）
      3. analyze_impact → RebuildPlan(full / partial / skipped) + 成本估算
      4. dry_run=True 时仅返回 plan
      5. dry_run=False 时返回 **501 Not Implemented**（实际执行接 rebuild_orchestrator 留 M23）

    7 天观察期 + 灰度切换路径完全不变（D8 锁定）。
    """
    from packages.common.types import OntologyDiff
    from packages.rebuild.incremental import analyze_impact

    # M22 #9 codex HIGH #5: dry_run=False 返 501, 不再静默返回 200 误导调用方
    if not body.dry_run:
        raise HTTPException(
            status_code=501,
            detail="M22 #7 lite: incremental rebuild 实际执行未实现, "
                   "请用 dry_run=True 仅查看 plan; 真实执行接 rebuild_orchestrator 留 M23",
        )

    # 构造 diff: 优先用 caller 显式传入的字段
    diff = OntologyDiff(
        from_version=body.version_from, to_version=body.version_to,
        added_entity_types=body.added_entity_types,
        removed_entity_types=body.removed_entity_types,
        modified_entity_types=body.modified_entity_types,
        added_relation_types=body.added_relation_types,
        removed_relation_types=body.removed_relation_types,
        modified_relation_types=body.modified_relation_types,
    )

    if body.doc_to_types_override is None:
        raise HTTPException(
            status_code=400,
            detail="M22 #7 lite: 必须提供 doc_to_types_override (M23 接入"
                   " OntologyRegistry + graph_store 后可省)",
        )

    # M22 #9 codex LOW: 规模校验防 OOM
    if len(body.doc_to_types_override) > 10000:
        raise HTTPException(
            status_code=413,
            detail=f"doc_to_types_override 过大 ({len(body.doc_to_types_override)} > 10000); "
                   f"请分批调用",
        )

    doc_to_types = {k: set(v) for k, v in body.doc_to_types_override.items()}
    doc_to_relations = (
        {k: set(v) for k, v in body.doc_to_relations_override.items()}
        if body.doc_to_relations_override else None
    )

    plan = analyze_impact(
        diff=diff, doc_to_types=doc_to_types,
        doc_to_relations=doc_to_relations,
        project_id=body.project_id, l1_changed=body.l1_changed,
    )

    log.info("incremental_rebuild_invoked",
             project=body.project_id, dry_run=body.dry_run,
             full=len(plan.full_docs), partial=len(plan.partial_docs),
             skipped=len(plan.skipped_docs))
    return {"dry_run": body.dry_run, "plan": plan.to_dict()}
