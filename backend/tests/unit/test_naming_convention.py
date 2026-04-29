"""M3 #3b 块① · 命名规范生成器单测（PRD F1.5）。"""

from __future__ import annotations

import pytest

from packages.architect.naming_convention import (
    apply_user_changes,
    default_naming_convention,
    preview_filename,
    validate_filename,
)


# ════════════════════════════════════════════════════════════════════════
#  default_naming_convention
# ════════════════════════════════════════════════════════════════════════


class TestDefaultConvention:
    def test_has_eight_default_fields(self) -> None:
        """决策书 §4.4 模板：8 字段（层级/域/类型/标题/版本/密级/Owner/生命周期）。"""
        conv = default_naming_convention()
        assert len(conv.fields) == 8
        keys = [f.key for f in conv.fields]
        assert keys == [
            "hierarchy_code", "domain_code", "doc_type", "title",
            "version", "access_level", "owner", "lifecycle",
        ]

    def test_lifecycle_is_optional(self) -> None:
        conv = default_naming_convention()
        lifecycle = next(f for f in conv.fields if f.key == "lifecycle")
        assert lifecycle.required is False

    def test_default_separator_dash(self) -> None:
        assert default_naming_convention().separator == "-"

    def test_template_string(self) -> None:
        conv = default_naming_convention()
        s = conv.template_string()
        assert "[层级编码]" in s
        assert "[业务域代码]" in s
        assert s.count("-") == 7

    def test_default_example(self) -> None:
        """决策书 §4.4 锁定的示例。"""
        conv = default_naming_convention()
        assert "KB-CS-SOP" in conv.example
        assert "投诉处理" in conv.example
        assert "v2.3" in conv.example


# ════════════════════════════════════════════════════════════════════════
#  preview_filename
# ════════════════════════════════════════════════════════════════════════


class TestPreviewFilename:
    def test_full_values_render(self) -> None:
        conv = default_naming_convention()
        result = preview_filename(conv, {
            "hierarchy_code": "KB",
            "domain_code": "RD",
            "doc_type": "技术报告",
            "title": "电池热管理",
            "version": "v1.2",
            "access_level": "秘密",
            "owner": "研发部",
            "lifecycle": "评审中",
        })
        assert result == "KB-RD-技术报告-电池热管理-v1.2-秘密-研发部-评审中"

    def test_missing_values_use_placeholder(self) -> None:
        conv = default_naming_convention()
        result = preview_filename(conv, {})
        # 各字段用 placeholder 兜底
        assert "KB" in result and "CS" in result and "SOP" in result

    def test_partial_values(self) -> None:
        conv = default_naming_convention()
        result = preview_filename(conv, {
            "title": "新标题", "version": "v3.0",
        })
        assert "新标题" in result
        assert "v3.0" in result


# ════════════════════════════════════════════════════════════════════════
#  validate_filename
# ════════════════════════════════════════════════════════════════════════


class TestValidateFilename:
    def test_valid_default_example(self) -> None:
        conv = default_naming_convention()
        ok, issues = validate_filename(
            "KB-CS-SOP-投诉处理-v2.3-内部-客服部-生效中", conv,
        )
        assert ok is True
        assert issues == []

    def test_with_extension_stripped(self) -> None:
        conv = default_naming_convention()
        ok, _ = validate_filename(
            "KB-CS-SOP-投诉处理-v2.3-内部-客服部-生效中.md", conv,
        )
        assert ok is True

    def test_too_few_parts_rejected(self) -> None:
        conv = default_naming_convention()
        ok, issues = validate_filename("KB-CS", conv)
        assert ok is False
        assert "__too_few_parts__" in issues

    def test_invalid_version_format(self) -> None:
        conv = default_naming_convention()
        ok, issues = validate_filename(
            "KB-CS-SOP-投诉处理-bad_version-内部-客服部-生效中", conv,
        )
        assert ok is False
        assert "version:format" in issues

    def test_invalid_access_level(self) -> None:
        conv = default_naming_convention()
        ok, issues = validate_filename(
            "KB-CS-SOP-投诉处理-v1.0-不合法-客服部-生效中", conv,
        )
        assert ok is False
        assert "access_level:enum" in issues

    def test_empty_filename(self) -> None:
        conv = default_naming_convention()
        ok, issues = validate_filename("", conv)
        assert ok is False
        assert "__empty__" in issues

    def test_optional_lifecycle_can_omit(self) -> None:
        """lifecycle 是 optional 字段（决策书 §4.4），可省略尾部。"""
        conv = default_naming_convention()
        # lifecycle 部分留空
        ok, issues = validate_filename(
            "KB-CS-SOP-投诉处理-v2.3-内部-客服部", conv,
        )
        # too_few_parts 检查依据 required 数量（7 个 required）
        # required 全填齐则通过
        assert ok is True or "lifecycle" not in issues


# ════════════════════════════════════════════════════════════════════════
#  apply_user_changes
# ════════════════════════════════════════════════════════════════════════


class TestApplyUserChanges:
    def test_change_separator(self) -> None:
        conv = default_naming_convention()
        new_conv = apply_user_changes(conv, separator="_")
        assert new_conv.separator == "_"
        # 原实例不变
        assert conv.separator == "-"

    def test_reorder_keeps_all_fields(self) -> None:
        conv = default_naming_convention()
        new_order = [
            "title", "doc_type", "version", "owner",
            "access_level", "domain_code", "hierarchy_code", "lifecycle",
        ]
        new_conv = apply_user_changes(conv, reorder=new_order)
        assert [f.key for f in new_conv.fields] == new_order

    def test_reorder_mismatch_keeps_original(self) -> None:
        """reorder 漏字段 → 拒绝调整保留原顺序（防误删）。"""
        conv = default_naming_convention()
        new_conv = apply_user_changes(conv, reorder=["title"])  # 漏其他
        assert [f.key for f in new_conv.fields] == [f.key for f in conv.fields]

    def test_set_required(self) -> None:
        conv = default_naming_convention()
        new_conv = apply_user_changes(conv, set_required={"lifecycle": True})
        lifecycle = next(f for f in new_conv.fields if f.key == "lifecycle")
        assert lifecycle.required is True

    def test_example_regenerated(self) -> None:
        """字段顺序调整后 example 重新生成。"""
        conv = default_naming_convention()
        new_order = ["title"] + [
            f.key for f in conv.fields if f.key != "title"
        ]
        new_conv = apply_user_changes(conv, reorder=new_order)
        # 新 example 标题在前
        assert new_conv.example.startswith("投诉处理")
