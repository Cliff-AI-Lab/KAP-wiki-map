"""M13 #4 · ISS-Job 调度协调端点单测（决策书 §10.5）。"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from starlette.middleware.base import BaseHTTPMiddleware

from api.routers.iss_job import router
from packages.common.auth import UserContext
from packages.observability import (
    add_ground_truth, record_decision, record_query,
    reset_decisions_for_test, reset_queries_for_test,
    reset_recall_eval_for_test,
)
from packages.rebuild import (
    ShadowGraphStore, reset_observations_for_test,
    reset_shadow_store_for_test, start_observation,
)


class _UserInjectMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request.state.user = UserContext(user_id="test", roles=[])
        return await call_next(request)


def _build_app() -> FastAPI:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.add_middleware(_UserInjectMiddleware)
    return app


@pytest.fixture(autouse=True)
def _reset():
    reset_decisions_for_test()
    reset_queries_for_test()
    reset_observations_for_test()
    reset_shadow_store_for_test()
    reset_recall_eval_for_test()
    yield
    reset_decisions_for_test()
    reset_queries_for_test()
    reset_observations_for_test()
    reset_shadow_store_for_test()
    reset_recall_eval_for_test()


@pytest.fixture
def client():
    return TestClient(_build_app())


class TestCronRecommendations:
    def test_empty_state_returns_max_interval(self, client) -> None:
        r = client.get("/api/v1/iss-job/cron-recommendations")
        assert r.status_code == 200
        body = r.json()
        assert body["kap_status"]["active_observations"] == 0
        assert body["kap_status"]["alerting_observations"] == 0
        # 无活跃 → 推荐最大间隔（1800s）
        tick_job = next(j for j in body["recommended_jobs"]
                        if j["name"] == "tick_all_observations")
        assert tick_job["interval_seconds"] == 1800

    def test_active_observation_recommends_default(self, client) -> None:
        s = ShadowGraphStore()
        for i in range(5):
            s.add_entity("p1", "v1", entity_name=f"E{i}",
                         type_id="equipment", doc_id="d")
        start_observation("p1", "v1", shadow=s)
        r = client.get("/api/v1/iss-job/cron-recommendations")
        body = r.json()
        assert body["kap_status"]["active_observations"] == 1
        tick_job = next(j for j in body["recommended_jobs"]
                        if j["name"] == "tick_all_observations")
        assert tick_job["interval_seconds"] == 300

    def test_alerting_observation_recommends_min_interval(self, client) -> None:
        s = ShadowGraphStore()
        for i in range(5):
            s.add_entity("p1", "v1", entity_name=f"E{i}",
                         type_id="equipment", doc_id="d")
        obs = start_observation("p1", "v1", shadow=s)
        # 直接设 alert
        obs.status = "alert"

        r = client.get("/api/v1/iss-job/cron-recommendations")
        body = r.json()
        assert body["kap_status"]["alerting_observations"] == 1
        tick_job = next(j for j in body["recommended_jobs"]
                        if j["name"] == "tick_all_observations")
        # alerting → 60s
        assert tick_job["interval_seconds"] == 60

    def test_eval_interval_depends_on_gt_count(self, client) -> None:
        # 无 GT
        r1 = client.get("/api/v1/iss-job/cron-recommendations")
        eval_job1 = next(j for j in r1.json()["recommended_jobs"]
                         if j["name"] == "eval_all_recall")
        # 加 GT 后
        add_ground_truth(project_id="p1", query_text="x",
                         expected_doc_ids=["d1"])
        r2 = client.get("/api/v1/iss-job/cron-recommendations")
        eval_job2 = next(j for j in r2.json()["recommended_jobs"]
                         if j["name"] == "eval_all_recall")
        # 有 GT → 间隔变短
        assert eval_job2["interval_seconds"] < eval_job1["interval_seconds"]

    def test_includes_decisions_and_queries_count(self, client) -> None:
        record_decision(project_id="p1", decision_type="approve_proposal")
        record_query(project_id="p1", query_text="x", source_count=1)

        r = client.get("/api/v1/iss-job/cron-recommendations")
        body = r.json()
        assert body["kap_status"]["decisions_total"] == 1
        assert body["kap_status"]["queries_total"] == 1

    # M17 #2 · auto-tune 推荐
    def test_no_auto_tune_when_below_sample_threshold(self, client) -> None:
        # < 50 decisions → 不推荐 auto-tune
        for _ in range(10):
            record_decision(project_id="p1", decision_type="approve_proposal")
        r = client.get("/api/v1/iss-job/cron-recommendations")
        body = r.json()
        names = [j["name"] for j in body["recommended_jobs"]]
        assert not any(n.startswith("auto_tune_prompt_") for n in names)

    def test_auto_tune_recommended_when_above_threshold(self, client) -> None:
        # ≥ 50 decisions → 推荐 4 个 auto-tune jobs（每条件一个）
        for _ in range(60):
            record_decision(project_id="p1", decision_type="approve_proposal")
        r = client.get("/api/v1/iss-job/cron-recommendations")
        body = r.json()
        auto_tune = [
            j for j in body["recommended_jobs"]
            if j["name"].startswith("auto_tune_prompt_")
        ]
        assert len(auto_tune) == 4
        # 全部周度间隔（604800s）
        for j in auto_tune:
            assert j["interval_seconds"] == 7 * 24 * 3600
            assert j["endpoint"] == "/api/v1/observability/prompt-versions/auto-tune"
            assert j["body"]["min_samples"] == 10
            assert j["body"]["language"] == "zh"
        # 4 condition_type 都覆盖
        condition_types = {j["body"]["condition_type"] for j in auto_tune}
        assert condition_types == {
            "new_entity_type", "relation_solidification",
            "relation_split", "standard_upgrade",
        }

    def test_response_version_bumped_to_2(self, client) -> None:
        r = client.get("/api/v1/iss-job/cron-recommendations")
        assert r.json()["version"] == "2"
