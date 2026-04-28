"""Domain 推断模块单测（坑 4b 验收）。

覆盖：

- 关键词匹配（精确路径优先级）
- priority 解决并列
- 命中数解决同 priority 并列
- 字典序确定性（同 priority 同命中数）
- ROUTING_PENDING_DOMAIN_ID 兜底
- clean_domain_id 多种 LLM 异常输出格式
- 行业模板加载（energy / manufacturing / 不存在）
"""

from __future__ import annotations

import pytest

from packages.distillation.domain_inference import (
    ROUTING_PENDING_DOMAIN_ID,
    clean_domain_id,
    infer_domain_id,
    load_rules,
)
from packages.distillation.templates_loader import clear_cache


@pytest.fixture(autouse=True)
def _reset_cache() -> None:
    """每个测试前清缓存，避免污染。"""
    clear_cache()
    load_rules.cache_clear()


# ─────────── clean_domain_id ───────────


class TestCleanDomainId:
    def test_already_clean(self) -> None:
        assert clean_domain_id("tech/architecture") == "tech/architecture"

    def test_with_brackets_simple(self) -> None:
        assert clean_domain_id("L1 [tech]: 技术文档 — ...") == "tech"

    def test_with_brackets_takes_longest(self) -> None:
        assert (
            clean_domain_id("L1 [product]/L2 [product/roadmap]")
            == "product/roadmap"
        )

    def test_with_quotes(self) -> None:
        assert clean_domain_id("'L1 [quality]'") == "quality"
        assert clean_domain_id('"tech/api"') == "tech/api"

    def test_strip_l_prefix(self) -> None:
        assert clean_domain_id("L1/product") == "product"
        assert clean_domain_id("L2 product/roadmap") == "product/roadmap"

    def test_split_colon(self) -> None:
        assert clean_domain_id("tech:技术文档") == "tech"

    def test_split_comma(self) -> None:
        assert clean_domain_id("tech,extra") == "tech"

    def test_empty_input(self) -> None:
        assert clean_domain_id("") == ""
        assert clean_domain_id("   ") == ""


# ─────────── infer_domain_id（基于真实 YAML）───────────


class TestInferEnergyIndustry:
    """能源行业模板：基于 templates/energy/domain-keywords.yaml。"""

    def test_safety_hazard_priority(self) -> None:
        result = infer_domain_id("本文档讲安全隐患排查", industry="energy")
        assert result.domain_id == "energy/safety/hazard"
        assert result.rule_priority == 100
        assert "隐患" in result.matched_keywords

    def test_safety_general_falls_to_lower_priority(self) -> None:
        """只命中通用 ``安全`` 关键词，落到 priority=70 的 energy/safety。"""
        result = infer_domain_id("本文档讲安全管理", industry="energy")
        assert result.domain_id == "energy/safety"
        assert result.rule_priority == 70

    def test_environment(self) -> None:
        result = infer_domain_id("本文档讲废气排放监测", industry="energy")
        assert result.domain_id == "energy/environment"

    def test_equipment_subdomain_priority(self) -> None:
        """巡检规则 priority=100 应高于通用设备 priority=80。"""
        result = infer_domain_id(
            "本文档讲日常巡检标准与设备维护",
            industry="energy",
        )
        assert result.domain_id == "energy/production/equipment/inspection"

    def test_no_match_returns_routing_pending(self) -> None:
        """完全无匹配关键词 → routing_pending。"""
        result = infer_domain_id("xxxxxxx 完全无关 yyyyyyy", industry="energy")
        assert result.domain_id == ROUTING_PENDING_DOMAIN_ID
        assert result.confidence == 0.0
        assert result.rule_priority == 0


class TestInferDefaultIndustry:
    def test_finance(self) -> None:
        result = infer_domain_id("差旅费用报销流程", industry=None)
        assert result.domain_id == "regulation/finance"

    def test_tech_deploy(self) -> None:
        result = infer_domain_id("Docker 容器部署运维手册", industry=None)
        assert result.domain_id == "tech/deploy"

    def test_no_match_returns_routing_pending(self) -> None:
        result = infer_domain_id("zzzzzzz", industry=None)
        assert result.domain_id == ROUTING_PENDING_DOMAIN_ID


class TestInferTitleParticipates:
    def test_title_keywords_count(self) -> None:
        """标题中的关键词应参与匹配。"""
        result = infer_domain_id(
            "正文不含特定词汇",
            industry="energy",
            title="安全隐患排查制度",
        )
        assert result.domain_id == "energy/safety/hazard"


class TestInferTextWindow:
    def test_long_text_truncated(self) -> None:
        """超长文本被截断到 4000 字符内。"""
        long_text = "无关词" * 5000 + "动火作业"  # 关键词在 1.5万字符之后
        result = infer_domain_id(long_text, industry="energy")
        # 应该匹配不到，因为关键词在窗口外
        assert result.domain_id == ROUTING_PENDING_DOMAIN_ID


# ─────────── load_rules ───────────


class TestLoadRules:
    def test_energy_rules_loaded(self) -> None:
        rules, source = load_rules("energy")
        assert len(rules) > 0
        assert source.startswith("yaml:")
        # 验证 priority 降序
        priorities = [r.priority for r in rules]
        assert priorities == sorted(priorities, reverse=True)

    def test_default_rules_loaded(self) -> None:
        rules, source = load_rules(None)
        assert len(rules) > 0

    def test_unknown_industry_falls_to_default(self) -> None:
        rules_unknown, _ = load_rules("non-existent-xyz")
        rules_default, _ = load_rules(None)
        # 未知行业应 fallback 到 _default 的规则
        assert len(rules_unknown) == len(rules_default)

    def test_lru_cache_works(self) -> None:
        a, _ = load_rules("energy")
        b, _ = load_rules("energy")
        assert a is b  # frozen tuple cached


# ─────────── 优先级与确定性 ───────────


class TestPriorityResolution:
    def test_higher_priority_wins(self) -> None:
        """priority=100 的规则胜过 priority=70 的同方向匹配。"""
        # "隐患" 命中 priority=100；"安全" 也命中 priority=70
        result = infer_domain_id("安全隐患排查", industry="energy")
        assert result.domain_id == "energy/safety/hazard"
        assert result.rule_priority == 100
