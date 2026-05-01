"""M11 #4 · prompt 版本追踪 + AB 比较单测（决策书 §5.3）。"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from packages.common.types import (
    OntologyEntityType,
    OntologyEvolutionProposal,
    OntologyRelationType,
)
from packages.observability import (
    compute_prompt_ab_score,
    create_prompt_version,
    deactivate_prompt_version,
    get_active_version,
    get_version,
    list_prompt_versions,
    reset_prompt_versions_for_test,
    resolve_active_system_prompt,
)


@pytest.fixture(autouse=True)
def _reset():
    reset_prompt_versions_for_test()
    yield
    reset_prompt_versions_for_test()


def _proposal(
    *, condition: str, status: str, created_at: datetime,
) -> OntologyEvolutionProposal:
    if condition == "new_entity_type":
        et = OntologyEntityType(type_id="x", type_name="X")
        rt = None
        reasoning = ""
    elif condition == "standard_upgrade":
        et = OntologyEntityType(type_id="standard", type_name="标准")
        rt = None
        reasoning = ""
    elif condition == "relation_solidification":
        et = None
        rt = OntologyRelationType(type_id="r", type_name="R")
        reasoning = ""
    else:  # relation_split
        et = None
        rt = OntologyRelationType(type_id="r2", type_name="R2")
        reasoning = "拆分自 governs"
    return OntologyEvolutionProposal(
        proposal_id=f"p_{condition}_{status}_{created_at.isoformat()}",
        project_id="p1",
        proposed_entity_type=et,
        proposed_relation_type=rt,
        reasoning=reasoning,
        status=status,    # type: ignore[arg-type]
        created_at=created_at,
    )


# ════════════════════════════════════════════════════════════════════════
#  CRUD
# ════════════════════════════════════════════════════════════════════════


class TestCRUD:
    def test_create_first_version_active(self) -> None:
        v = create_prompt_version(
            condition_type="new_entity_type",
            prompt_text_excerpt="新版 prompt",
            created_by="sme01",
        )
        assert v.version_id.startswith("pver_")
        assert v.deactivated_at is None
        active = get_active_version("new_entity_type")
        assert active is v

    def test_create_second_auto_deactivates_first(self) -> None:
        v1 = create_prompt_version(
            condition_type="new_entity_type", prompt_text_excerpt="v1",
        )
        v2 = create_prompt_version(
            condition_type="new_entity_type", prompt_text_excerpt="v2",
        )
        # v1 自动停用
        v1_after = get_version(v1.version_id)
        assert v1_after is not None
        assert v1_after.deactivated_at is not None
        # 新 active 是 v2
        active = get_active_version("new_entity_type")
        assert active.version_id == v2.version_id

    def test_different_conditions_independent(self) -> None:
        v_entity = create_prompt_version(condition_type="new_entity_type")
        v_split = create_prompt_version(condition_type="relation_split")
        assert v_entity.deactivated_at is None
        assert v_split.deactivated_at is None

    def test_excerpt_truncated(self) -> None:
        v = create_prompt_version(
            condition_type="new_entity_type",
            prompt_text_excerpt="a" * 500,
        )
        assert len(v.prompt_text_excerpt) == 200

    def test_manual_deactivate(self) -> None:
        v = create_prompt_version(condition_type="standard_upgrade")
        assert deactivate_prompt_version(v.version_id) is True
        v_after = get_version(v.version_id)
        assert v_after.deactivated_at is not None
        # 二次停用 → False
        assert deactivate_prompt_version(v.version_id) is False

    def test_deactivate_unknown_returns_false(self) -> None:
        assert deactivate_prompt_version("pver_unknown") is False

    def test_list_filter_only_active(self) -> None:
        v1 = create_prompt_version(condition_type="new_entity_type")
        deactivate_prompt_version(v1.version_id)
        v2 = create_prompt_version(condition_type="new_entity_type")

        active_only = list_prompt_versions(only_active=True)
        assert len(active_only) == 1
        assert active_only[0].version_id == v2.version_id

        all_ver = list_prompt_versions()
        assert len(all_ver) == 2


# ════════════════════════════════════════════════════════════════════════
#  AB 比较
# ════════════════════════════════════════════════════════════════════════


class TestABScore:
    def test_empty_versions_returns_empty(self) -> None:
        scores = compute_prompt_ab_score([])
        assert scores == []

    def test_proposals_assigned_to_correct_version_window(self) -> None:
        # 模拟：v1 用了 5 分钟（10:00-10:05），v2 从 10:05 开始
        # proposal_a created 10:02 → v1 区间
        # proposal_b created 10:07 → v2 区间
        from packages.observability import prompt_versions as pv_mod

        # 直接构造（绕过 datetime.now()）
        t0 = datetime(2026, 4, 30, 10, 0, 0)
        t1 = datetime(2026, 4, 30, 10, 5, 0)
        t2 = datetime(2026, 4, 30, 10, 5, 0)

        v1 = create_prompt_version(condition_type="new_entity_type",
                                    prompt_text_excerpt="v1")
        v1.activated_at = t0
        v1.deactivated_at = t1

        v2 = create_prompt_version(condition_type="new_entity_type",
                                    prompt_text_excerpt="v2")
        v2.activated_at = t2
        v2.deactivated_at = None

        # proposals
        p_v1 = _proposal(condition="new_entity_type", status="approved",
                         created_at=datetime(2026, 4, 30, 10, 2, 0))
        p_v2_a = _proposal(condition="new_entity_type", status="rejected",
                           created_at=datetime(2026, 4, 30, 10, 7, 0))
        p_v2_b = _proposal(condition="new_entity_type", status="approved",
                           created_at=datetime(2026, 4, 30, 10, 8, 0))
        # 不同条件不应混入
        p_other = _proposal(condition="standard_upgrade", status="approved",
                            created_at=datetime(2026, 4, 30, 10, 7, 0))

        scores = compute_prompt_ab_score(
            [p_v1, p_v2_a, p_v2_b, p_other],
            condition_type="new_entity_type",
        )
        assert len(scores) == 2

        by_id = {s.version_id: s for s in scores}
        s_v1 = by_id[v1.version_id]
        assert s_v1.sample_size == 1
        assert s_v1.approve_rate == 1.0

        s_v2 = by_id[v2.version_id]
        assert s_v2.sample_size == 2
        assert s_v2.approve_rate == 0.5

    def test_filter_by_condition_type(self) -> None:
        v_a = create_prompt_version(condition_type="new_entity_type")
        v_b = create_prompt_version(condition_type="relation_split")
        scores = compute_prompt_ab_score(
            [], condition_type="new_entity_type",
        )
        ids = {s.version_id for s in scores}
        assert v_a.version_id in ids
        assert v_b.version_id not in ids

    def test_proposal_before_window_excluded(self) -> None:
        v = create_prompt_version(condition_type="new_entity_type")
        v.activated_at = datetime(2026, 4, 30, 10, 0, 0)
        # proposal 在激活前创建 → 不算
        early = _proposal(
            condition="new_entity_type", status="approved",
            created_at=datetime(2026, 4, 30, 9, 0, 0),
        )
        scores = compute_prompt_ab_score(
            [early], condition_type="new_entity_type",
        )
        assert scores[0].sample_size == 0

    def test_is_active_flag_active_versions(self) -> None:
        v_active = create_prompt_version(condition_type="new_entity_type")
        v_old = create_prompt_version(condition_type="standard_upgrade")
        deactivate_prompt_version(v_old.version_id)

        scores = compute_prompt_ab_score([])
        by_id = {s.version_id: s for s in scores}
        assert by_id[v_active.version_id].is_active is True
        assert by_id[v_old.version_id].is_active is False


# ════════════════════════════════════════════════════════════════════════
#  M12 #1 · resolve_active_system_prompt（动态 prompt 解析）
# ════════════════════════════════════════════════════════════════════════


class TestResolveActiveSystemPrompt:
    def test_no_active_returns_fallback(self) -> None:
        out = resolve_active_system_prompt(
            "new_entity_type", "FALLBACK_HARDCODED",
        )
        assert out == "FALLBACK_HARDCODED"

    def test_active_with_empty_system_prompt_returns_fallback(self) -> None:
        # M11 #4 兼容：旧版本无 system_prompt → 用 fallback
        create_prompt_version(
            condition_type="new_entity_type",
            prompt_text_excerpt="just a hint",
        )
        out = resolve_active_system_prompt(
            "new_entity_type", "FALLBACK_HARDCODED",
        )
        assert out == "FALLBACK_HARDCODED"

    def test_active_with_system_prompt_returns_override(self) -> None:
        create_prompt_version(
            condition_type="standard_upgrade",
            system_prompt="OVERRIDE_PROMPT",
        )
        out = resolve_active_system_prompt(
            "standard_upgrade", "FALLBACK_HARDCODED",
        )
        assert out == "OVERRIDE_PROMPT"

    def test_deactivated_version_falls_back(self) -> None:
        v = create_prompt_version(
            condition_type="relation_split",
            system_prompt="OLD_OVERRIDE",
        )
        deactivate_prompt_version(v.version_id)
        out = resolve_active_system_prompt(
            "relation_split", "FALLBACK_HARDCODED",
        )
        assert out == "FALLBACK_HARDCODED"

    def test_independent_per_condition(self) -> None:
        create_prompt_version(
            condition_type="new_entity_type",
            system_prompt="NEW_ENT_OVERRIDE",
        )
        create_prompt_version(
            condition_type="relation_solidification",
            system_prompt="REL_OVERRIDE",
        )
        assert resolve_active_system_prompt(
            "new_entity_type", "F1",
        ) == "NEW_ENT_OVERRIDE"
        assert resolve_active_system_prompt(
            "relation_solidification", "F2",
        ) == "REL_OVERRIDE"
        # 第三类无 active → fallback
        assert resolve_active_system_prompt(
            "standard_upgrade", "F3",
        ) == "F3"

    def test_create_with_system_prompt_persists(self) -> None:
        v = create_prompt_version(
            condition_type="new_entity_type",
            system_prompt="A" * 1000,    # 不截断 system_prompt
        )
        assert len(v.system_prompt) == 1000


# ════════════════════════════════════════════════════════════════════════
#  M15 #3 · 多语言 prompt
# ════════════════════════════════════════════════════════════════════════


class TestMultiLanguage:
    def test_default_language_is_zh(self) -> None:
        v = create_prompt_version(condition_type="new_entity_type")
        assert v.language == "zh"

    def test_zh_and_en_active_independently(self) -> None:
        v_zh = create_prompt_version(
            condition_type="new_entity_type",
            system_prompt="ZH_PROMPT",
            language="zh",
        )
        v_en = create_prompt_version(
            condition_type="new_entity_type",
            system_prompt="EN_PROMPT",
            language="en",
        )
        # 两者都 active（不同语言独立）
        assert v_zh.deactivated_at is None
        assert v_en.deactivated_at is None
        assert get_active_version("new_entity_type", "zh").version_id == v_zh.version_id
        assert get_active_version("new_entity_type", "en").version_id == v_en.version_id

    def test_create_zh_then_zh_deactivates_old_zh_only(self) -> None:
        v_zh1 = create_prompt_version(
            condition_type="new_entity_type", language="zh",
        )
        v_en = create_prompt_version(
            condition_type="new_entity_type", language="en",
        )
        v_zh2 = create_prompt_version(
            condition_type="new_entity_type", language="zh",
        )
        # 第一个 zh 被停用
        assert get_version(v_zh1.version_id).deactivated_at is not None
        # en 不受影响
        assert get_version(v_en.version_id).deactivated_at is None
        # 新 zh 是 active
        assert get_active_version("new_entity_type", "zh").version_id == v_zh2.version_id

    def test_resolve_picks_language_specific(self) -> None:
        create_prompt_version(
            condition_type="standard_upgrade",
            system_prompt="ZH_OVERRIDE", language="zh",
        )
        create_prompt_version(
            condition_type="standard_upgrade",
            system_prompt="EN_OVERRIDE", language="en",
        )
        assert resolve_active_system_prompt(
            "standard_upgrade", "FALLBACK", language="zh",
        ) == "ZH_OVERRIDE"
        assert resolve_active_system_prompt(
            "standard_upgrade", "FALLBACK", language="en",
        ) == "EN_OVERRIDE"

    def test_resolve_fallback_to_zh_when_lang_missing(self) -> None:
        create_prompt_version(
            condition_type="relation_split",
            system_prompt="ZH_ONLY", language="zh",
        )
        # 请求 en，但只有 zh active → 回退到 zh
        assert resolve_active_system_prompt(
            "relation_split", "FB", language="en",
        ) == "ZH_ONLY"

    def test_resolve_falls_back_to_default_when_no_active(self) -> None:
        # 没创建任何版本 → fallback
        assert resolve_active_system_prompt(
            "relation_solidification", "DEFAULT_PROMPT", language="ja",
        ) == "DEFAULT_PROMPT"

    def test_list_filter_by_language(self) -> None:
        create_prompt_version(
            condition_type="new_entity_type", language="zh",
        )
        create_prompt_version(
            condition_type="new_entity_type", language="en",
        )
        zh_only = list_prompt_versions(language="zh")
        en_only = list_prompt_versions(language="en")
        assert all(v.language == "zh" for v in zh_only)
        assert all(v.language == "en" for v in en_only)
        assert len(zh_only) == 1
        assert len(en_only) == 1
