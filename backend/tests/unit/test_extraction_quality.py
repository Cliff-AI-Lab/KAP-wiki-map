"""M19 #2 · W4 抽取质量诊断（规则化，不调 LLM）。"""

from __future__ import annotations

import pytest

from packages.common.types import (
    ExtractedEntity, ExtractedRelation, ExtractionResult,
)
from packages.observability import (
    aggregate_extraction_metrics,
    list_extraction_metrics,
    record_extraction_metric,
    reset_extraction_quality_for_test,
)


@pytest.fixture(autouse=True)
def _reset():
    reset_extraction_quality_for_test()
    yield
    reset_extraction_quality_for_test()


def _make_entity(eid: str, conf: float, sensitive: bool = False, type_id: str = "device"):
    return ExtractedEntity(
        entity_id=eid, name=eid, type_id=type_id,
        confidence=conf, is_sensitive=sensitive,
    )


class TestRecordMetric:
    def test_healthy_extraction(self) -> None:
        result = ExtractionResult(
            doc_id="d1",
            entities=[
                _make_entity("e1", 0.9), _make_entity("e2", 0.85),
                _make_entity("e3", 0.8), _make_entity("e4", 0.95),
                _make_entity("e5", 0.9),
            ],
            relations=[
                ExtractedRelation(
                    source_entity_id="e1", target_entity_id="e2",
                    relation_type_id="r1", confidence=0.8,
                ),
                ExtractedRelation(
                    source_entity_id="e2", target_entity_id="e3",
                    relation_type_id="r1", confidence=0.7,
                ),
            ],
        )
        # 1000 字符 → 5 个实体 → density 5/k → 命中最优区间
        m = record_extraction_metric(
            result=result, project_id="p1", content_chars=1000,
        )
        assert m.entity_count == 5
        assert m.relation_count == 2
        assert 5.0 == m.entity_density_per_kchars
        assert m.score_entity_density == 1.0
        assert 0.85 < m.score_confidence_avg < 0.95
        assert m.overall > 0.7
        assert m.quality_alert is False

    def test_low_density_alerts(self) -> None:
        result = ExtractionResult(
            doc_id="d2",
            entities=[_make_entity("e1", 0.6)],
            relations=[],
        )
        # 5000 字符仅 1 实体 → density 0.2/k 严重过低
        m = record_extraction_metric(
            result=result, project_id="p1", content_chars=5000,
        )
        assert m.score_entity_density < 0.2
        assert m.overall < 0.5
        assert m.quality_alert is True

    def test_extraction_failure_records_alert(self) -> None:
        result = ExtractionResult(doc_id="d_fail", error="LLM down")
        m = record_extraction_metric(
            result=result, project_id="p1", content_chars=2000,
        )
        assert m.error == "LLM down"
        assert m.overall == 0.0
        assert m.quality_alert is True

    def test_sensitive_handled_high_score(self) -> None:
        result = ExtractionResult(
            doc_id="d_sens",
            entities=[
                _make_entity("e1", 0.9, sensitive=True),
                _make_entity("e2", 0.85),
                _make_entity("e3", 0.8),
                _make_entity("e4", 0.85),
                _make_entity("e5", 0.9),
            ],
            relations=[
                ExtractedRelation(
                    source_entity_id="e1", target_entity_id="e2",
                    relation_type_id="r1", confidence=0.8,
                ),
                ExtractedRelation(
                    source_entity_id="e2", target_entity_id="e3",
                    relation_type_id="r1", confidence=0.8,
                ),
            ],
        )
        m = record_extraction_metric(
            result=result, project_id="p1", content_chars=1000,
        )
        # 检出敏感词 → score_sensitive_handled = 1.0
        assert m.score_sensitive_handled == 1.0
        assert m.sensitive_count == 1


class TestListAggregate:
    def test_list_orders_newest_first_and_filters(self) -> None:
        for i in range(3):
            record_extraction_metric(
                result=ExtractionResult(doc_id=f"d{i}",
                                        entities=[_make_entity("e", 0.9)]),
                project_id=f"p{i % 2}", content_chars=500,
            )
        all_metrics = list_extraction_metrics()
        assert len(all_metrics) == 3
        # 最新优先（d2 是最后插入）
        assert all_metrics[0].doc_id == "d2"
        # 过滤 project
        p0 = list_extraction_metrics(project_id="p0")
        assert all(m.project_id == "p0" for m in p0)

    def test_list_only_alerting(self) -> None:
        # 健康文档
        record_extraction_metric(
            result=ExtractionResult(
                doc_id="ok",
                entities=[_make_entity(f"e{i}", 0.9) for i in range(5)],
                relations=[
                    ExtractedRelation(
                        source_entity_id=f"e{i}", target_entity_id=f"e{(i+1)%5}",
                        relation_type_id="r1", confidence=0.8,
                    ) for i in range(2)
                ],
            ),
            project_id="p1", content_chars=1000,
        )
        # 抽取失败
        record_extraction_metric(
            result=ExtractionResult(doc_id="fail", error="x"),
            project_id="p1", content_chars=1000,
        )
        alerts = list_extraction_metrics(only_alerting=True)
        assert len(alerts) == 1
        assert alerts[0].doc_id == "fail"

    def test_aggregate_summary(self) -> None:
        # 一健康一失败
        record_extraction_metric(
            result=ExtractionResult(
                doc_id="ok",
                entities=[_make_entity(f"e{i}", 0.9) for i in range(5)],
                relations=[
                    ExtractedRelation(
                        source_entity_id="e0", target_entity_id="e1",
                        relation_type_id="r", confidence=0.7,
                    ),
                    ExtractedRelation(
                        source_entity_id="e1", target_entity_id="e2",
                        relation_type_id="r", confidence=0.7,
                    ),
                ],
            ),
            project_id="p1", content_chars=1000,
        )
        record_extraction_metric(
            result=ExtractionResult(doc_id="bad", error="x"),
            project_id="p1", content_chars=1000,
        )
        agg = aggregate_extraction_metrics(project_id="p1")
        assert agg["total"] == 2
        assert agg["alerting"] == 1
        assert agg["avg_overall"] > 0   # 健康那条把均值拉上来

    def test_empty_aggregate(self) -> None:
        agg = aggregate_extraction_metrics()
        assert agg["total"] == 0
        assert agg["alerting"] == 0
        assert agg["avg_overall"] == 0.0


class TestW4Integration:
    """W4 入口（entity_extractor）应在抽取末尾自动调 record_extraction_metric。"""

    async def test_w4_extract_records_metric(self, monkeypatch) -> None:
        from packages.extraction import entity_extractor as ee_mod
        from packages.common.types import (
            OntologyEntityType, OntologyRelationType,
        )

        monkeypatch.setattr(
            ee_mod, "_collect_ontology_types",
            lambda industry, project: (
                [OntologyEntityType(type_id="device", type_name="设备",
                                     description="")],
                [OntologyRelationType(type_id="r1", type_name="rel",
                                       description="",
                                       source_types=[], target_types=[])],
                {"device"}, {"r1"}, {},
            ),
        )

        async def fake_llm(_sys, _user):
            return {
                "entities": [
                    {"name": "燃机A", "type_id": "device", "confidence": 0.9,
                     "evidence": ""},
                ],
                "relations": [],
            }

        monkeypatch.setattr(ee_mod, "acall_llm_json", fake_llm)
        monkeypatch.setattr(ee_mod, "detect_sensitive_spans", lambda c: [])

        result = await ee_mod.extract_entities_and_relations(
            doc_id="d_int", content="x" * 800,
            industry_code="energy", project_id="p1",
        )
        assert len(result.entities) == 1

        metrics = list_extraction_metrics(project_id="p1")
        assert len(metrics) == 1
        assert metrics[0].doc_id == "d_int"
        assert metrics[0].entity_count == 1
