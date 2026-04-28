"""Skills 加载器 — 从 YAML 文件加载组织 Skills 定义。

Skills 文件定义了一个虚拟组织的完整能力体系：
- 角色（谁）
- 知识域（知道什么）
- 协作流程（怎么配合）

加载后生成：
1. KnowledgeDomain 列表 → 替代硬编码的 DEFAULT_TAXONOMY
2. 角色描述文本 → 嵌入 Refiner/Router 的 prompt
3. 知识域目录文本 → 给 LLM 路由时阅读
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from packages.common import get_logger
from packages.common.types import KnowledgeDomain

log = get_logger("skills.loader")

# 默认 Skills 文件路径
_DEFAULT_SKILLS_DIR = Path(__file__).resolve().parent.parent.parent / "skills"


class OrgSkills:
    """加载并持有一个组织的完整 Skills 定义。"""

    def __init__(self, data: dict[str, Any], source_path: str = ""):
        self._data = data
        self.source_path = source_path

        self.company = data.get("company", {})
        self.roles: dict[str, dict] = data.get("roles", {})
        self.domains_raw: dict[str, dict] = data.get("knowledge_domains", {})
        self.workflows: dict[str, dict] = data.get("workflows", {})

    @property
    def company_name(self) -> str:
        return self.company.get("name", "未知公司")

    @property
    def company_alias(self) -> str:
        return self.company.get("alias", self.company_name)

    # ── 生成 KnowledgeDomain 列表 ─────────────────────

    def to_taxonomy(self) -> list[KnowledgeDomain]:
        """从 Skills 的 knowledge_domains 生成 KnowledgeDomain 列表。"""
        result: list[KnowledgeDomain] = []

        for domain_id, domain_cfg in self.domains_raw.items():
            # 一级域
            result.append(KnowledgeDomain(
                domain_id=domain_id,
                name=domain_cfg.get("name", domain_id),
                parent_id="",
                description=domain_cfg.get("description", "").strip(),
                is_system=True,
            ))

            # 二级域
            children = domain_cfg.get("children", {})
            for child_id, child_cfg in children.items():
                result.append(KnowledgeDomain(
                    domain_id=child_id,
                    name=child_cfg.get("name", child_id),
                    parent_id=domain_id,
                    description=child_cfg.get("description", "").strip(),
                    is_system=True,
                ))

        log.info("skills_taxonomy_generated", company=self.company_alias, domain_count=len(result))
        return result

    # ── 生成 Refiner prompt 中的知识域列表 ─────────────

    def to_refiner_domain_list(self) -> str:
        """生成 Refiner Agent prompt 中「可用知识域」部分的文本。"""
        lines: list[str] = []
        for domain_id, domain_cfg in self.domains_raw.items():
            owner = domain_cfg.get("owner")
            owner_label = ""
            if owner and owner in self.roles:
                owner_label = f"（{self.roles[owner]['name']}负责）"

            name = domain_cfg.get("name", domain_id)
            desc = domain_cfg.get("description", "").strip().split("\n")[0]  # 取第一行
            lines.append(f"- {domain_id}: {name}{owner_label} — {desc}")

            children = domain_cfg.get("children", {})
            for child_id, child_cfg in children.items():
                child_name = child_cfg.get("name", child_id)
                child_desc = child_cfg.get("description", "").strip().split("\n")[0]
                lines.append(f"  - {child_id}: {child_name} — {child_desc}")

        return "\n".join(lines)

    # ── 生成角色说明文本（给 prompt 用） ───────────────

    def to_roles_text(self) -> str:
        """生成角色能力描述文本（可嵌入 system prompt）。"""
        lines: list[str] = [f"## {self.company_alias} 组织角色\n"]
        for role_id, role_cfg in self.roles.items():
            name = role_cfg.get("name", role_id)
            rep = role_cfg.get("representative", "")
            title = role_cfg.get("title", "")
            desc = role_cfg.get("description", "").strip()
            lines.append(f"### {name}（{rep}，{title}）")
            lines.append(desc)

            produces = role_cfg.get("produces", [])
            if produces:
                lines.append("**产出知识：**" + "、".join(produces))

            consumes = role_cfg.get("consumes", [])
            if consumes:
                lines.append("**消费知识：**" + "、".join(consumes))

            questions = role_cfg.get("questions", [])
            if questions:
                lines.append("**典型问题：**")
                for q in questions[:3]:
                    lines.append(f"  - {q}")

            lines.append("")
        return "\n".join(lines)

    # ── 生成角色-问题路由映射 ──────────────────────────

    def get_role_question_map(self) -> dict[str, list[str]]:
        """返回 {role_name: [typical_questions]} 映射。"""
        result = {}
        for role_id, role_cfg in self.roles.items():
            name = role_cfg.get("name", role_id)
            result[name] = role_cfg.get("questions", [])
        return result

    # ── 根据角色查找关联的知识域 ──────────────────────

    def get_domains_for_role(self, role_id: str) -> list[str]:
        """返回某个角色拥有的知识域 ID 列表。"""
        result = []
        for domain_id, domain_cfg in self.domains_raw.items():
            if domain_cfg.get("owner") == role_id:
                result.append(domain_id)
                for child_id in domain_cfg.get("children", {}):
                    result.append(child_id)
        return result


def load_skills(path: str | Path | None = None) -> OrgSkills:
    """加载 Skills YAML 文件。

    如果不指定路径，自动扫描 skills/ 目录下第一个 .yaml 文件。
    """
    if path is None:
        # 自动发现
        yaml_files = sorted(_DEFAULT_SKILLS_DIR.glob("*.yaml"))
        if not yaml_files:
            log.warning("no_skills_file_found", dir=str(_DEFAULT_SKILLS_DIR))
            return OrgSkills({}, source_path="")
        path = yaml_files[0]

    path = Path(path)
    if not path.exists():
        log.warning("skills_file_not_found", path=str(path))
        return OrgSkills({}, source_path=str(path))

    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    skills = OrgSkills(data, source_path=str(path))
    log.info(
        "skills_loaded",
        company=skills.company_alias,
        roles=len(skills.roles),
        domains=len(skills.domains_raw),
        path=str(path),
    )
    return skills
