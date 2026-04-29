"""导出 TaxonomyDraft → IndustryTemplate（PRD F1.7）。

M2 lite 范围：
- 转 Pydantic IndustryTemplate（复用 M1 模板系统）
- 自动注册到 INDUSTRY_REGISTRY（私有化部署后立即可用）
- YAML / JSON 序列化产物（pyyaml 已在依赖）

不做（M3+）：
- 体系版本化 + Git 化 tag（PRD F1.7.3）
- 体系生效触发块② 启用（PRD F1.7.4）
- 已入库文档影响评估（PRD F1.7.5）
- PG 持久化 IndustryTemplate（M3 加 industry_templates 表）
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

import yaml

from packages.common import get_logger
from packages.common.types import TaxonomyDraft
from packages.templates.registry import (
    INDUSTRY_REGISTRY,
    IndustryTemplate,
    TaxonomyNode,
    register,
)

log = get_logger("architect.exporter")


def export_to_industry_template(
    draft: TaxonomyDraft,
    *,
    register_globally: bool = True,
    custom_code_suffix: str = "",
) -> IndustryTemplate:
    """把 TaxonomyDraft 转换为 IndustryTemplate 并（可选）注册到 INDUSTRY_REGISTRY。

    Args:
        draft: 主树草稿（已完成 identify + propose + refine）
        register_globally: 是否自动注册到全局 INDUSTRY_REGISTRY
        custom_code_suffix: 客户定制后缀（如 "-acme"），避免与基础 5 行业冲突

    Returns:
        IndustryTemplate 实例（可被块② 直接消费）

    Raises:
        ValueError: draft 不完整（缺 industry_code 或 taxonomy）
    """
    if not draft.industry_code:
        raise ValueError("draft.industry_code 不能为空")
    if not draft.taxonomy:
        raise ValueError("draft.taxonomy 不能为空")

    # 生成最终 code（避免覆盖基础模板）
    base_code = draft.industry_code
    if custom_code_suffix:
        final_code = f"{base_code}-{custom_code_suffix}"
    elif base_code in INDUSTRY_REGISTRY:
        # 基础模板已存在 → 加 -custom-{8 位 uuid} 后缀
        final_code = f"{base_code}-custom-{uuid.uuid4().hex[:8]}"
    else:
        final_code = base_code

    # 保证 taxonomy 项是 TaxonomyNode 实例（支持 dict 输入）
    nodes: list[TaxonomyNode] = []
    for n in draft.taxonomy:
        if isinstance(n, TaxonomyNode):
            nodes.append(n)
        elif isinstance(n, dict):
            nodes.append(TaxonomyNode.model_validate(n))
        else:
            log.warning("exporter_skip_invalid_node", item=str(n)[:60])

    template = IndustryTemplate(
        code=final_code,
        name=draft.industry_name or final_code,
        name_en=base_code.replace("-", " ").title(),
        icon="Folder",
        description=f"由 KAP 块① 咨询智能体导出（基于 {base_code} 行业模板演化）",
        taxonomy=nodes,
        facets={},  # 客户 Facet 提议留 M3
    )

    if register_globally:
        register(template)
        log.info("template_registered", code=final_code, node_count=len(nodes))

    return template


def to_yaml(template: IndustryTemplate) -> str:
    """序列化为 YAML（PRD F1.7.2）。"""
    data = template.model_dump(exclude_none=False)
    return yaml.safe_dump(data, allow_unicode=True, sort_keys=False)


def to_json(template: IndustryTemplate, *, indent: int = 2) -> str:
    """序列化为 JSON（PRD F1.7.2）。"""
    return template.model_dump_json(indent=indent)


def write_to_file(template: IndustryTemplate, target_dir: Path | str) -> dict[str, Path]:
    """写到本地目录（YAML + JSON 两份）。

    返回 ``{"yaml": path, "json": path}`` 文件路径。
    """
    target = Path(target_dir)
    target.mkdir(parents=True, exist_ok=True)
    yaml_path = target / f"{template.code}.yaml"
    json_path = target / f"{template.code}.json"
    yaml_path.write_text(to_yaml(template), encoding="utf-8")
    json_path.write_text(to_json(template), encoding="utf-8")
    log.info("template_exported_files", code=template.code, dir=str(target))
    return {"yaml": yaml_path, "json": json_path}
