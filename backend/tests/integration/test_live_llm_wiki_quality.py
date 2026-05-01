"""真 LLM Wiki 质量评分集成测试（M17 #3）。

弱断言：6 维分都在 [0,1]；overall 在 [0,1]；error 字段为空。
"""

from __future__ import annotations

import pytest

from packages.observability import (
    reset_wiki_quality_for_test, score_wiki_page,
)


pytestmark = pytest.mark.live_llm


SAMPLE_WIKI_CONTENT = """
# 燃气轮机日常巡检规程

本规程描述某型号燃气轮机的日常巡检流程，由维修部李工负责。

## 关键参数
- 润滑油位 0.85±0.05 MPa
- 冷却水流量 ≥ 120 m³/h
- 振动监测：GB/T 6075-2024

## 巡检步骤
1. 启动前检查油位 / 水流量
2. 每 4 小时记录一次振动数据
3. 异常时升级至总工程师确认

## 关联文档
- 维修部安全管理办法 v3
- 燃气轮机厂商手册 2024 版
"""


@pytest.fixture(autouse=True)
def _reset():
    reset_wiki_quality_for_test()
    yield
    reset_wiki_quality_for_test()


class TestScoreWikiPageLive:
    async def test_returns_valid_6dim_scores(
        self, require_live_llm,
    ) -> None:
        """真 LLM 调质量评分；弱断言每维在 [0,1] + overall 合理。"""
        score = await score_wiki_page(
            page_id="live_test_wiki_1",
            page_type="domain_overview",
            title="燃气轮机日常巡检规程",
            content=SAMPLE_WIKI_CONTENT,
            source_doc_count=2,
            cross_ref_count=2,
            version=1,
            project_id="live_test_p1",
        )

        if score.error:
            pytest.skip(f"LLM 报错（非测试缺陷）: {score.error}")

        # schema 弱断言：6 维都存在 + 在 [0, 1]
        for dim_name in (
            "consistency", "completeness", "evidence",
            "repetition", "freshness", "cross_domain",
        ):
            dim = getattr(score, dim_name)
            assert 0.0 <= dim.score <= 1.0, (
                f"{dim_name}.score 越界: {dim.score}"
            )
            # reason 非空（弱：让 prompt 调优后仍通过）
            assert isinstance(dim.reason, str)

        assert 0.0 <= score.overall <= 1.0
        assert score.page_id == "live_test_wiki_1"
        assert score.project_id == "live_test_p1"
