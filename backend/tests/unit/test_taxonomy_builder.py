"""M2 #4 块① · 批 3 · taxonomy_builder + exporter 单测（PRD F1.3 / F1.7）。"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from packages.architect.exporter import (
    export_to_industry_template,
    to_json,
    to_yaml,
    write_to_file,
)
from packages.architect.taxonomy_builder import (
    apply_user_command,
    propose_taxonomy,
)
from packages.common.types import TaxonomyDraft
from packages.templates.registry import (
    INDUSTRY_REGISTRY,
    IndustryTemplate,
    TaxonomyNode,
    get_template,
)


# ════════════════════════════════════════════════════════════════════════
#  propose_taxonomy
# ════════════════════════════════════════════════════════════════════════


class TestProposeTaxonomy:
    async def test_unknown_industry_returns_empty(self) -> None:
        result = await propose_taxonomy("nonexistent", ["sample"])
        assert result == []

    async def test_no_samples_keeps_full_template(self) -> None:
        result = await propose_taxonomy("manufacturing", [])
        manufacturing = get_template("manufacturing")
        assert len(result) == len(manufacturing.taxonomy)

    async def test_llm_drop_decisions_applied(self) -> None:
        async def fake_llm(system, user):
            return {
                "decisions": [
                    {"node_id": "warehouse", "action": "drop"},
                    {"node_id": "rnd", "action": "highlight"},
                ],
            }

        with patch(
            "packages.architect.taxonomy_builder.acall_llm_json",
            side_effect=fake_llm,
        ):
            result = await propose_taxonomy("manufacturing", ["sample text"])

        ids = [n.id for n in result]
        assert "warehouse" not in ids       # 被 drop
        assert "rnd" in ids                  # highlight 后保留
        rnd_node = next(n for n in result if n.id == "rnd")
        assert "[推荐]" in rnd_node.description

    async def test_llm_failure_falls_back_to_full_template(self) -> None:
        with patch(
            "packages.architect.taxonomy_builder.acall_llm_json",
            side_effect=Exception("LLM down"),
        ):
            result = await propose_taxonomy("manufacturing", ["sample"])
        manufacturing = get_template("manufacturing")
        assert len(result) == len(manufacturing.taxonomy)

    async def test_llm_drops_all_falls_back(self) -> None:
        """LLM 把所有节点都 drop → 退化保全（避免 UI 出空树）。"""
        async def fake_llm(system, user):
            return {
                "decisions": [
                    {"node_id": nid, "action": "drop"}
                    for nid in ("production", "quality", "equipment", "warehouse",
                                "rnd", "safety")
                ],
            }
        with patch(
            "packages.architect.taxonomy_builder.acall_llm_json",
            side_effect=fake_llm,
        ):
            result = await propose_taxonomy("manufacturing", ["sample"])
        # 兜底：返回完整 base
        assert len(result) >= 6


# ════════════════════════════════════════════════════════════════════════
#  apply_user_command
# ════════════════════════════════════════════════════════════════════════


def _make_draft() -> TaxonomyDraft:
    return TaxonomyDraft(
        industry_code="manufacturing",
        industry_name="制造业",
        confidence=0.85,
        taxonomy=[
            TaxonomyNode(id="production", name="生产管理", level=2),
            TaxonomyNode(id="warehouse", name="仓储管理", level=2),
            TaxonomyNode(id="quality", name="质量管理", level=2),
        ],
    )


class TestApplyUserCommand:
    def test_remove_command_drops_node(self) -> None:
        draft = _make_draft()
        result = apply_user_command(draft, "删除 仓储管理")
        ids = [n.id for n in result.taxonomy]
        assert "warehouse" not in ids
        assert "production" in ids

    def test_rename_command_updates_name(self) -> None:
        draft = _make_draft()
        result = apply_user_command(draft, "把仓储管理重命名为物流管理")
        names = [n.name for n in result.taxonomy]
        assert "物流管理" in names
        assert "仓储管理" not in names

    def test_add_command_appends_new_node(self) -> None:
        draft = _make_draft()
        result = apply_user_command(draft, "新增 海外业务")
        names = [n.name for n in result.taxonomy]
        assert "海外业务" in names
        assert len(result.taxonomy) == 4

    def test_add_dedup_doesnt_duplicate(self) -> None:
        draft = _make_draft()
        # 已有"生产管理"
        result = apply_user_command(draft, "新增 生产管理")
        names = [n.name for n in result.taxonomy]
        assert names.count("生产管理") == 1

    def test_unrecognized_command_unchanged(self) -> None:
        draft = _make_draft()
        before = len(draft.taxonomy)
        result = apply_user_command(draft, "这条命令我看不懂")
        assert len(result.taxonomy) == before


# ════════════════════════════════════════════════════════════════════════
#  exporter — export_to_industry_template
# ════════════════════════════════════════════════════════════════════════


class TestExportTemplate:
    def test_export_creates_template(self) -> None:
        draft = _make_draft()
        before_codes = set(INDUSTRY_REGISTRY.keys())
        tpl = export_to_industry_template(draft, register_globally=True)
        after_codes = set(INDUSTRY_REGISTRY.keys())
        # 注册了新 code
        assert len(after_codes - before_codes) == 1
        assert tpl.name == "制造业"
        # 节点数对齐
        assert len(tpl.taxonomy) == 3

    def test_export_avoid_overwrite_base_code(self) -> None:
        """basa_code 已存在 → 加 -custom-{uuid} 后缀。"""
        draft = _make_draft()
        tpl = export_to_industry_template(draft, register_globally=False)
        assert tpl.code != "manufacturing"
        assert tpl.code.startswith("manufacturing-custom-")

    def test_export_with_explicit_suffix(self) -> None:
        draft = _make_draft()
        tpl = export_to_industry_template(
            draft, register_globally=False, custom_code_suffix="acme",
        )
        assert tpl.code == "manufacturing-acme"

    def test_export_empty_draft_raises(self) -> None:
        empty = TaxonomyDraft(industry_code="manufacturing", taxonomy=[])
        with pytest.raises(ValueError, match="taxonomy 不能为空"):
            export_to_industry_template(empty, register_globally=False)

    def test_export_no_industry_code_raises(self) -> None:
        empty = TaxonomyDraft(taxonomy=[TaxonomyNode(id="x", name="X", level=2)])
        with pytest.raises(ValueError, match="industry_code"):
            export_to_industry_template(empty, register_globally=False)


# ════════════════════════════════════════════════════════════════════════
#  exporter — YAML / JSON 序列化
# ════════════════════════════════════════════════════════════════════════


class TestSerialization:
    def test_to_yaml_round_trip(self) -> None:
        draft = _make_draft()
        tpl = export_to_industry_template(draft, register_globally=False)
        yaml_str = to_yaml(tpl)
        parsed = yaml.safe_load(yaml_str)
        assert parsed["code"] == tpl.code
        assert parsed["name"] == "制造业"
        assert len(parsed["taxonomy"]) == 3

    def test_to_json_valid(self) -> None:
        draft = _make_draft()
        tpl = export_to_industry_template(draft, register_globally=False)
        import json
        parsed = json.loads(to_json(tpl))
        assert parsed["code"] == tpl.code

    def test_write_to_file_creates_both(self, tmp_path: Path) -> None:
        draft = _make_draft()
        tpl = export_to_industry_template(draft, register_globally=False)
        paths = write_to_file(tpl, tmp_path)
        assert paths["yaml"].exists()
        assert paths["json"].exists()
        # YAML 内容可读
        content = paths["yaml"].read_text(encoding="utf-8")
        assert tpl.code in content
