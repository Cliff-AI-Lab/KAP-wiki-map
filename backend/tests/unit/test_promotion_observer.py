"""M5 #2 · 7 天观察期 + 指标采集单测（决策书 §5.3）。

覆盖：
- collect_metrics：节点数 / 关系数 / 分布 / 自定义关系比例
- compute_drift：实体/关系变化比例 + 关键类型消失检测
- 观察期生命周期：start → tick → alert → expired / rolled_back
- promote_shadow / rollback_promotion 自动 wire 观察期
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from packages.rebuild import (
    OBSERVATION_DAYS,
    ShadowGraphStore,
    collect_metrics,
    compute_drift,
    get_current_observation,
    list_observations,
    mark_rolled_back,
    promote_shadow,
    reset_observations_for_test,
    reset_shadow_store_for_test,
    rollback_promotion,
    start_observation,
    tick_all_observations,
    tick_observation,
)
from packages.rebuild import promotion_observer as obs_mod


@pytest.fixture(autouse=True)
def _reset():
    reset_shadow_store_for_test()
    reset_observations_for_test()
    yield
    reset_shadow_store_for_test()
    reset_observations_for_test()


def _build_shadow(version: str = "v1.0.1") -> ShadowGraphStore:
    """构造一个 (project=p1, version) 含数据的 ShadowGraphStore。"""
    s = ShadowGraphStore()
    for i in range(8):
        s.add_entity("p1", version,
                     entity_name=f"E{i}", type_id="equipment", doc_id="d")
    for i in range(4):
        s.add_entity("p1", version,
                     entity_name=f"P{i}", type_id="process", doc_id="d")
    # 关系：3 governs（已注册）+ 1 maintained_by（自定义）
    s.add_relation("p1", version, source_name="GB-1", target_name="E0",
                   relation_type_id="governs", doc_id="d")
    s.add_relation("p1", version, source_name="GB-2", target_name="E1",
                   relation_type_id="governs", doc_id="d")
    s.add_relation("p1", version, source_name="GB-3", target_name="E2",
                   relation_type_id="governs", doc_id="d")
    s.add_relation("p1", version, source_name="李工", target_name="E0",
                   relation_type_id="maintained_by", doc_id="d")
    return s


# ════════════════════════════════════════════════════════════════════════
#  collect_metrics
# ════════════════════════════════════════════════════════════════════════


class TestCollectMetrics:
    def test_basic_counts(self) -> None:
        s = _build_shadow()
        m = collect_metrics("p1", "v1.0.1", shadow=s)
        assert m.entity_count == 12
        assert m.relation_count == 4
        assert m.entity_type_distribution == {"equipment": 8, "process": 4}

    def test_custom_relation_ratio(self) -> None:
        s = _build_shadow()
        # 已注册 governs；maintained_by 是自定义
        m = collect_metrics(
            "p1", "v1.0.1",
            known_relation_type_ids={"governs"}, shadow=s,
        )
        assert m.custom_relation_ratio == 0.25  # 1/4

    def test_no_known_types_skips_ratio(self) -> None:
        s = _build_shadow()
        m = collect_metrics("p1", "v1.0.1", shadow=s)
        assert m.custom_relation_ratio == 0.0

    def test_empty_version_returns_zeros(self) -> None:
        s = ShadowGraphStore()
        m = collect_metrics("p1", "empty", shadow=s)
        assert m.entity_count == 0
        assert m.relation_count == 0
        assert m.custom_relation_ratio == 0.0


# ════════════════════════════════════════════════════════════════════════
#  compute_drift
# ════════════════════════════════════════════════════════════════════════


class TestComputeDrift:
    def test_no_change_zero_delta(self) -> None:
        s = _build_shadow()
        m1 = collect_metrics("p1", "v1.0.1", shadow=s)
        m2 = collect_metrics("p1", "v1.0.1", shadow=s)
        drift = compute_drift(m1, m2)
        assert drift["entity_count_delta_pct"] == 0.0
        assert drift["relation_count_delta_pct"] == 0.0
        assert drift["lost_key_types"] == []

    def test_lost_key_type_detected(self) -> None:
        s1 = _build_shadow("base")
        baseline = collect_metrics("p1", "base", shadow=s1)
        # current 中没有 process 类型
        s2 = ShadowGraphStore()
        for i in range(8):
            s2.add_entity("p1", "cur",
                          entity_name=f"E{i}", type_id="equipment", doc_id="d")
        current = collect_metrics("p1", "cur", shadow=s2)
        drift = compute_drift(baseline, current)
        assert "process" in drift["lost_key_types"]

    def test_entity_growth_pct(self) -> None:
        s1 = _build_shadow("a")  # 12 entities
        s2 = ShadowGraphStore()
        for i in range(18):
            s2.add_entity("p1", "b", entity_name=f"E{i}",
                          type_id="equipment", doc_id="d")
        b = collect_metrics("p1", "a", shadow=s1)
        c = collect_metrics("p1", "b", shadow=s2)
        drift = compute_drift(b, c)
        assert drift["entity_count_delta_pct"] == pytest.approx(0.5, abs=0.01)


# ════════════════════════════════════════════════════════════════════════
#  观察期生命周期
# ════════════════════════════════════════════════════════════════════════


class TestObservationLifecycle:
    def test_start_creates_baseline_and_expiry(self) -> None:
        s = _build_shadow()
        obs = start_observation("p1", "v1.0.1", shadow=s)
        assert obs.status == "watching"
        assert obs.baseline.entity_count == 12
        assert obs.expires_at - obs.promoted_at == timedelta(days=OBSERVATION_DAYS)
        assert get_current_observation("p1") is obs

    def test_tick_records_snapshot_no_alert(self) -> None:
        s = _build_shadow()
        start_observation("p1", "v1.0.1", shadow=s)
        # 数据不变 → 不应告警
        obs = tick_observation("p1", shadow=s)
        assert obs is not None
        assert obs.status == "watching"
        assert len(obs.snapshots) == 1
        assert obs.alerts == []

    def test_tick_alerts_on_entity_growth_50pct(self) -> None:
        s = _build_shadow()  # 12 entities
        start_observation("p1", "v1.0.1", shadow=s)
        # 灌入新数据使其暴增
        for i in range(20, 50):
            s.add_entity("p1", "v1.0.1",
                         entity_name=f"NEW{i}", type_id="equipment", doc_id="d")
        obs = tick_observation("p1", shadow=s)
        assert obs.status == "alert"
        assert any("实体数变化" in a for a in obs.alerts)

    def test_tick_alerts_on_lost_key_type(self) -> None:
        s = _build_shadow()
        start_observation("p1", "v1.0.1", shadow=s)
        # 删除所有 process 实体（直接操作内部 bucket，模拟 SME 大批量清理）
        bucket = s._nodes[("p1", "v1.0.1")]
        for name in [n for n, info in bucket.items()
                     if info.get("type_id") == "process"]:
            del bucket[name]
        obs = tick_observation("p1", shadow=s)
        assert obs.status == "alert"
        assert any("关键实体类型消失" in a and "process" in a for a in obs.alerts)

    def test_tick_returns_none_when_no_active(self) -> None:
        assert tick_observation("p_no_observation") is None

    def test_tick_marks_expired_after_7_days(self, monkeypatch) -> None:
        s = _build_shadow()
        obs = start_observation("p1", "v1.0.1", shadow=s)
        # 调到 expires 之后
        future = obs.expires_at + timedelta(hours=1)

        class _FakeDt:
            @staticmethod
            def now(tz=None):
                return future

        monkeypatch.setattr(obs_mod, "datetime", _FakeDt)
        result = tick_observation("p1", shadow=s)
        assert result.status == "expired"

    def test_mark_rolled_back(self) -> None:
        s = _build_shadow()
        start_observation("p1", "v1.0.1", shadow=s)
        assert mark_rolled_back("p1") is True
        obs = get_current_observation("p1")
        assert obs.status == "rolled_back"

    def test_start_supersedes_old_watching(self) -> None:
        s = _build_shadow()
        first = start_observation("p1", "v1.0.0", shadow=s)
        second = start_observation("p1", "v1.0.1", shadow=s)
        assert second.observation_id != first.observation_id
        all_obs = list_observations("p1")
        assert len(all_obs) == 2
        # 旧观察期被 supersede 标 expired
        old = next(o for o in all_obs if o.observation_id == first.observation_id)
        assert old.status == "expired"
        # 当前是新的
        cur = get_current_observation("p1")
        assert cur.observation_id == second.observation_id


# ════════════════════════════════════════════════════════════════════════
#  promote / rollback wire
# ════════════════════════════════════════════════════════════════════════


class TestPromoteRollbackWiring:
    def test_promote_starts_observation(self) -> None:
        s = _build_shadow()
        # build source = empty, target = full （满足启发式 src=0 时跳过节点变化检查）
        src_empty = ShadowGraphStore()
        # 用 _build_shadow 已有的 s 作为 target；为合并 source，复用同一 store
        for i in range(8):
            s.add_entity("p1", "v1.0.0", entity_name=f"E{i}",
                         type_id="equipment", doc_id="d")
        for i in range(4):
            s.add_entity("p1", "v1.0.0", entity_name=f"P{i}",
                         type_id="process", doc_id="d")
        promote_shadow("p1", "v1.0.0", "v1.0.1", shadow=s, force=True)
        obs = get_current_observation("p1")
        assert obs is not None
        assert obs.version == "v1.0.1"
        assert obs.baseline.entity_count == 12

    def test_rollback_marks_observation(self) -> None:
        s = _build_shadow()
        for i in range(8):
            s.add_entity("p1", "v1.0.0", entity_name=f"E{i}",
                         type_id="equipment", doc_id="d")
        for i in range(4):
            s.add_entity("p1", "v1.0.0", entity_name=f"P{i}",
                         type_id="process", doc_id="d")
        # 先 begin_shadow 让 swap 知道 current_shadow，rollback 才有 previous
        s.begin_shadow("p1", "v1.0.0")
        promote_shadow("p1", "v1.0.0", "v1.0.1", shadow=s, force=True)
        rollback_promotion("p1", shadow=s)
        obs = get_current_observation("p1")
        assert obs is not None
        assert obs.status == "rolled_back"


# ════════════════════════════════════════════════════════════════════════
#  M6 #2 · tick_all_observations
# ════════════════════════════════════════════════════════════════════════


class TestTickAll:
    def test_tick_all_empty_returns_empty(self) -> None:
        assert tick_all_observations() == []

    def test_tick_all_processes_multiple_projects(self) -> None:
        s = _build_shadow("v1")
        s2 = ShadowGraphStore()
        for i in range(5):
            s2.add_entity("p2", "v1", entity_name=f"E{i}",
                          type_id="equipment", doc_id="d")

        start_observation("p1", "v1", shadow=s)
        start_observation("p2", "v1", shadow=s2)
        # 用 p1 的 shadow 作为通用 shadow 不正确（数据隔离），逐项目调
        # 这里关键测：tick_all 把两个观察期都 tick 一次
        results = tick_all_observations(shadow=s)
        # 至少返回 2 个观察期更新（p1 的 snapshot 应有数据，p2 的可能为空但 obs 仍返回）
        assert len(results) == 2
        assert {o.project_id for o in results} == {"p1", "p2"}

    def test_tick_all_skips_rolled_back(self) -> None:
        s = _build_shadow("v1")
        start_observation("p1", "v1", shadow=s)
        mark_rolled_back("p1")

        results = tick_all_observations(shadow=s)
        # rolled_back 状态仍被返回（保持状态可见）
        assert len(results) == 1
        assert results[0].status == "rolled_back"

    def test_tick_all_handles_per_project_failure(self, monkeypatch) -> None:
        """单 project 异常不阻断其他项目。"""
        s = _build_shadow("v1")
        start_observation("p1", "v1", shadow=s)
        start_observation("p2", "v1", shadow=s)

        from packages.rebuild import promotion_observer as po
        original = po.tick_observation
        call_count = {"n": 0}

        def flaky(project_id, **kwargs):
            call_count["n"] += 1
            if project_id == "p1":
                raise RuntimeError("boom")
            return original(project_id, **kwargs)

        monkeypatch.setattr(po, "tick_observation", flaky)
        results = po.tick_all_observations(shadow=s)
        # p2 仍成功；p1 被吞掉
        assert any(o.project_id == "p2" for o in results)
        assert call_count["n"] == 2
