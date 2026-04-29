"""命名规范生成器（PRD F1.5 lite）。

决策书 §4.4 锁定的默认模板：

    [层级编码]-[业务域代码]-[文档类型]-[标题]-[版本]-[密级]-[Owner]-[生命周期态]

示例：``KB-CS-SOP-投诉处理-v2.3-内部-客服部-生效中``

设计原则（feedback memory · 轻量化）：
- 模板规则化（不调 LLM），客户可改字段顺序 / 必填性 / 分隔符
- ``preview_filename(convention, sample_values)`` 实时拼接预览（PRD F1.5.2）
- ``validate_filename(filename, convention)`` 批量校验（PRD F1.5.4）
- 不做命名规范变更日志（PRD F1.5.5 留 M4）
"""

from __future__ import annotations

import re

from packages.common import get_logger
from packages.common.types import NamingConvention, NamingField

log = get_logger("architect.naming_convention")


# ════════════════════════════════════════════════════════════════════════
#  默认模板（决策书 §4.4）
# ════════════════════════════════════════════════════════════════════════


def default_naming_convention(
    *,
    industry_code: str = "",
    project_id: str = "",
) -> NamingConvention:
    """生成决策书 §4.4 默认 8 字段模板。

    客户可在此基础上调整字段顺序 / 必填性。
    """
    return NamingConvention(
        industry_code=industry_code,
        project_id=project_id,
        separator="-",
        fields=[
            NamingField(
                key="hierarchy_code", name="层级编码", required=True,
                placeholder="KB", description="知识库层级前缀（如 KB / SOP / WIKI）",
            ),
            NamingField(
                key="domain_code", name="业务域代码", required=True,
                placeholder="CS", description="L2 部门 / 业务域代码（如 CS / RD / OPS）",
            ),
            NamingField(
                key="doc_type", name="文档类型", required=True,
                placeholder="SOP", description="Facet doc_type（SOP / 标准 / 报告 等）",
            ),
            NamingField(
                key="title", name="标题", required=True,
                placeholder="投诉处理", description="文档主体标题（10 字内推荐）",
            ),
            NamingField(
                key="version", name="版本", required=True,
                placeholder="v2.3", description="语义化版本号（vX.Y[.Z]）",
            ),
            NamingField(
                key="access_level", name="密级", required=True,
                placeholder="内部", description="公开 / 内部 / 秘密 / 机密",
            ),
            NamingField(
                key="owner", name="Owner", required=True,
                placeholder="客服部", description="主责部门或岗位",
            ),
            NamingField(
                key="lifecycle", name="生命周期态", required=False,
                placeholder="生效中", description="草稿 / 评审中 / 生效中 / 归档 / 作废",
            ),
        ],
        example="KB-CS-SOP-投诉处理-v2.3-内部-客服部-生效中",
        notes="决策书 §4.4 默认模板；客户可通过 architect 对话调整字段顺序与必填性",
    )


# ════════════════════════════════════════════════════════════════════════
#  preview_filename — 实时预览（PRD F1.5.2）
# ════════════════════════════════════════════════════════════════════════


def preview_filename(
    convention: NamingConvention,
    values: dict[str, str],
) -> str:
    """按规范 + 给定字段值拼接示例文件名。

    Args:
        convention: NamingConvention 实例
        values: 字段 key → 值映射；缺失字段用 placeholder 兜底

    Returns:
        拼接后的文件名字符串
    """
    parts: list[str] = []
    for f in convention.fields:
        v = values.get(f.key, "").strip()
        if not v:
            v = f.placeholder or f"<{f.key}>"
        parts.append(v)
    return convention.separator.join(parts)


# ════════════════════════════════════════════════════════════════════════
#  validate_filename — 批量校验（PRD F1.5.4）
# ════════════════════════════════════════════════════════════════════════


def validate_filename(
    filename: str,
    convention: NamingConvention,
) -> tuple[bool, list[str]]:
    """按规范校验文件名是否合规。

    Returns:
        (is_valid, missing_or_invalid_field_keys)
    """
    if not filename:
        return False, ["__empty__"]

    # 去掉扩展名再拆分
    name_without_ext = re.sub(r"\.[a-zA-Z0-9]{1,8}$", "", filename)
    parts = name_without_ext.split(convention.separator)

    issues: list[str] = []
    expected_count = len(convention.fields)

    if len(parts) < sum(1 for f in convention.fields if f.required):
        issues.append("__too_few_parts__")
        return False, issues

    # 长度对齐：缺少的尾部字段如果都是非 required 则可接受
    for i, field in enumerate(convention.fields):
        value = parts[i].strip() if i < len(parts) else ""
        if field.required and not value:
            issues.append(field.key)
        # 简单格式校验：版本字段要求 vX.Y 模式
        if field.key == "version" and value:
            if not re.match(r"^v?\d+(\.\d+){1,2}$", value):
                issues.append(field.key + ":format")
        # 密级枚举
        if field.key == "access_level" and value:
            if value not in ("公开", "内部", "秘密", "机密"):
                issues.append(field.key + ":enum")

    return (len(issues) == 0, issues)


# ════════════════════════════════════════════════════════════════════════
#  apply_user_changes — 调整字段顺序 / 必填性（PRD F1.5.1）
# ════════════════════════════════════════════════════════════════════════


def apply_user_changes(
    convention: NamingConvention,
    *,
    reorder: list[str] | None = None,
    set_required: dict[str, bool] | None = None,
    separator: str | None = None,
) -> NamingConvention:
    """对规范应用用户调整（非破坏性，返回新实例）。

    Args:
        reorder: 新字段 key 顺序（必须包含全部现有 key）；不传则保持原顺序
        set_required: key → required 覆盖
        separator: 新分隔符
    """
    fields = list(convention.fields)
    by_key = {f.key: f for f in fields}

    if reorder:
        # 严格校验：reorder 必须包含全部 key（避免误删）
        if set(reorder) != set(by_key.keys()):
            log.warning("naming_apply_reorder_mismatch_skipped",
                        given=reorder, existing=list(by_key.keys()))
        else:
            fields = [by_key[k] for k in reorder]

    if set_required:
        new_fields = []
        for f in fields:
            if f.key in set_required:
                new_fields.append(f.model_copy(update={"required": set_required[f.key]}))
            else:
                new_fields.append(f)
        fields = new_fields

    new_separator = separator if separator is not None else convention.separator

    new_conv = convention.model_copy(update={
        "fields": fields,
        "separator": new_separator,
    })

    # 重新生成 example
    if "lifecycle" in {f.key for f in new_conv.fields}:
        new_conv.example = preview_filename(new_conv, {
            "hierarchy_code": "KB", "domain_code": "CS", "doc_type": "SOP",
            "title": "投诉处理", "version": "v2.3",
            "access_level": "内部", "owner": "客服部", "lifecycle": "生效中",
        })
    return new_conv
