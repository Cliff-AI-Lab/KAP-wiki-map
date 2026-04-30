"""ISS-Job 协调端点（M13 #4 · 决策书 §10.5）。

为外部 ISS-Job (Quartz) 调度器提供：
- 当前 KAP 状态摘要（活跃观察期、告警数、待审批 GT 候选数等）
- 推荐的下次触发间隔 + 建议的端点列表

设计原则（feedback memory · ISS 零侵入）：
- 不动 ISS Java 源码
- 不接 Quartz 框架
- 仅暴露 HTTP 接口让 ISS-Job 拉数据 + 推送 cron 决策

工作流：
  1. ISS-Job 定时（默认 5 分钟）调 GET /iss-job/cron-recommendations
  2. 根据返回的 should_run_observations / should_run_eval / interval_seconds
     在 Quartz 配置里调度调用：
       - POST /rebuild/observations/tick-all (M6 #2 已有)
       - POST /recall-eval/eval-all          (M9 #3 已有)
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from packages.common import get_logger
from packages.observability import (
    list_decisions,
    list_ground_truth,
    list_queries,
)
from packages.rebuild import list_observations

log = get_logger("api.iss_job")

router = APIRouter(prefix="/iss-job", tags=["ISS-Job 调度协调"])


# ── 推荐间隔（秒）启发式 ──
_DEFAULT_INTERVAL = 300            # 5 分钟基线
_MIN_INTERVAL = 60                 # 1 分钟下限（告警时密集）
_MAX_INTERVAL = 1800               # 30 分钟上限（无活跃时稀疏）


def _recommend_interval(
    *, alerting_obs: int, active_obs: int,
) -> int:
    """根据当前活跃观察期 + 告警数推荐下次触发间隔。

    - alerting_obs ≥ 1   → 60 秒（告警时密集监控）
    - active_obs ≥ 1     → 300 秒（默认 5 分钟）
    - 都没有              → 1800 秒（半小时一次轻探活）
    """
    if alerting_obs > 0:
        return _MIN_INTERVAL
    if active_obs > 0:
        return _DEFAULT_INTERVAL
    return _MAX_INTERVAL


@router.get("/cron-recommendations")
async def cron_recommendations() -> dict[str, Any]:
    """KAP 状态摘要 + 推荐 cron 配置（ISS-Job 拉取）。

    返回字段：
        kap_status: 当前 KAP 各源状态摘要
        recommended_jobs: 推荐 Quartz 配置的 jobs 列表
            - endpoint: KAP HTTP 端点
            - method: GET / POST
            - interval_seconds: 推荐间隔
            - reason: 推荐原因（启发式）
    """
    obs_list = list_observations()
    active_obs = sum(1 for o in obs_list if o.status == "watching")
    alerting_obs = sum(1 for o in obs_list if o.status == "alert")

    interval = _recommend_interval(
        alerting_obs=alerting_obs, active_obs=active_obs,
    )

    decisions_24h = len(list_decisions(limit=10000))
    queries_24h = len(list_queries(limit=10000))
    gt_count = len(list_ground_truth())

    eval_interval = (
        _DEFAULT_INTERVAL * 12 if gt_count > 0 else _MAX_INTERVAL * 6
    )  # 评估默认 1 小时；无 GT 时 3 小时一次

    log.info("cron_recommendations_served",
             active_obs=active_obs, alerting_obs=alerting_obs,
             gt_count=gt_count)

    return {
        "kap_status": {
            "active_observations": active_obs,
            "alerting_observations": alerting_obs,
            "total_observations": len(obs_list),
            "decisions_total": decisions_24h,
            "queries_total": queries_24h,
            "ground_truth_count": gt_count,
        },
        "recommended_jobs": [
            {
                "name": "tick_all_observations",
                "endpoint": "/api/v1/rebuild/observations/tick-all",
                "method": "POST",
                "body": {},
                "interval_seconds": interval,
                "reason": (
                    f"alerting={alerting_obs}, active={active_obs}; "
                    f"按启发式推荐 {interval}s"
                ),
            },
            {
                "name": "eval_all_recall",
                "endpoint": "/api/v1/observability/recall-eval/eval-all",
                "method": "POST",
                "body": {"k": 5, "version": ""},
                "interval_seconds": eval_interval,
                "reason": (
                    f"ground_truth={gt_count}; 推荐 {eval_interval}s"
                ),
            },
        ],
        "version": "1",
        "notes": (
            "ISS-Job 调用 KAP HTTP 端点时需带 SME role JWT；"
            "失败重试建议指数退避；详见 docs/integration/iss-job-config.md"
        ),
    }
