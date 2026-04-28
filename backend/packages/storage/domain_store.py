"""知识域与文档卡存储 — Skills 式知识体系的核心存储。

存储知识域定义（类似 Skill 描述）和文档索引卡（类似 Skill 的详细说明），
支持生成供 LLM 路由阅读的知识目录文本。
"""

from __future__ import annotations

import json
from typing import Optional

from packages.common import get_logger, settings
from packages.common.types import DocumentCard, KnowledgeDomain

log = get_logger("storage.domain")


class DomainStore:
    """知识域和文档卡存储，支持 PostgreSQL 和内存模式。

    V5: 支持按 project_id 隔离知识域和文档卡。
    V6: 联合主键 (domain_id, project_id) 彻底隔离项目间知识域。
    """

    def __init__(self, use_memory: bool = False):
        self._use_memory = use_memory
        # V6: key = (domain_id, project_id)
        self._domains: dict[tuple[str, str], KnowledgeDomain] = {}
        self._doc_cards: dict[str, DocumentCard] = {}     # doc_id -> card
        self._card_project: dict[str, str] = {}      # doc_id -> project_id
        self._pg_conn = None

    async def initialize(self, pg_conn=None) -> None:
        """初始化存储并加载预定义分类框架。"""
        self._pg_conn = pg_conn

        if not self._use_memory and self._pg_conn:
            try:
                await self._create_tables()
                await self._load_domains_from_pg()
            except Exception as e:
                log.warning("domain_store_pg_table_failed", error=str(e))
                self._use_memory = True

        log.info(
            "domain_store_initialized",
            mode="memory" if self._use_memory else "pg",
            domain_count=len(self._domains),
        )

    async def _create_tables(self) -> None:
        """确保表结构存在。已完成 V6 迁移后跳过 ALTER TABLE 避免锁竞争。"""
        assert self._pg_conn is not None
        async with self._pg_conn.cursor() as cur:
            # 检查两个表是否都存在
            await cur.execute("""
                SELECT table_name FROM information_schema.tables
                WHERE table_name IN ('knowledge_domains', 'document_cards')
            """)
            existing = {row[0] for row in await cur.fetchall()}

            if "knowledge_domains" not in existing:
                await cur.execute("""
                    CREATE TABLE knowledge_domains (
                        domain_id    VARCHAR(128) NOT NULL,
                        name         VARCHAR(128) NOT NULL,
                        parent_id    VARCHAR(128) DEFAULT '',
                        description  TEXT DEFAULT '',
                        doc_count    INT DEFAULT 0,
                        is_system    BOOLEAN DEFAULT TRUE,
                        project_id   VARCHAR(64) NOT NULL DEFAULT 'default',
                        created_at   TIMESTAMPTZ DEFAULT NOW(),
                        PRIMARY KEY (domain_id, project_id)
                    )
                """)
                await cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_knowledge_domains_project
                    ON knowledge_domains(project_id)
                """)

            if "document_cards" not in existing:
                await cur.execute("""
                    CREATE TABLE document_cards (
                        doc_id       VARCHAR(64) PRIMARY KEY,
                        title        VARCHAR(512),
                        domain_id    VARCHAR(128) DEFAULT '',
                        description  TEXT DEFAULT '',
                        key_elements JSONB DEFAULT '[]',
                        keywords     TEXT DEFAULT '',
                        project_id   VARCHAR(64) DEFAULT 'default',
                        created_at   TIMESTAMPTZ DEFAULT NOW()
                    )
                """)
                await cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_document_cards_project
                    ON document_cards(project_id)
                """)

            await self._pg_conn.commit()

    async def _load_domains_from_pg(self) -> None:
        """从 PG 加载已有知识域和文档卡到内存。"""
        assert self._pg_conn is not None
        # 确保读到最新已提交数据
        await self._pg_conn.commit()
        async with self._pg_conn.cursor() as cur:
            await cur.execute(
                "SELECT domain_id, name, parent_id, description, doc_count, is_system, project_id "
                "FROM knowledge_domains"
            )
            rows = await cur.fetchall()
            for row in rows:
                project_id = row[6] or "default"
                domain = KnowledgeDomain(
                    domain_id=row[0], name=row[1], parent_id=row[2] or "",
                    description=row[3] or "", doc_count=row[4] or 0, is_system=row[5],
                )
                self._domains[(domain.domain_id, project_id)] = domain

            await cur.execute(
                "SELECT doc_id, title, domain_id, description, key_elements, keywords, project_id "
                "FROM document_cards"
            )
            rows = await cur.fetchall()
            log.info("domain_store_cards_loaded_from_pg", count=len(rows))
            for row in rows:
                key_elements = row[4] if isinstance(row[4], list) else []
                kw = [k.strip() for k in (row[5] or "").split(",") if k.strip()]
                card = DocumentCard(
                    doc_id=row[0], title=row[1] or "", domain_id=row[2] or "",
                    description=row[3] or "", key_elements=key_elements, keywords=kw,
                )
                self._doc_cards[card.doc_id] = card
                self._card_project[card.doc_id] = row[6] or "default"

    # ── 知识域操作 ──────────────────────────────────────

    async def upsert_domain(self, domain: KnowledgeDomain, project_id: str = "default") -> None:
        """创建或更新知识域。"""
        self._domains[(domain.domain_id, project_id)] = domain

        if self._use_memory or not self._pg_conn:
            return

        async with self._pg_conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO knowledge_domains (domain_id, name, parent_id, description, doc_count, is_system, project_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (domain_id, project_id) DO UPDATE SET
                    name = EXCLUDED.name,
                    description = EXCLUDED.description,
                    doc_count = EXCLUDED.doc_count
                """,
                (domain.domain_id, domain.name, domain.parent_id,
                 domain.description, domain.doc_count, domain.is_system, project_id),
            )
            await self._pg_conn.commit()

    def list_domains(self, project_id: str | None = None) -> list[KnowledgeDomain]:
        """返回知识域列表（含文档计数）。project_id 为 None 时返回全部。"""
        # 更新文档计数（按项目过滤）
        domain_counts: dict[str, int] = {}
        for doc_id, card in self._doc_cards.items():
            if project_id and self._card_project.get(doc_id) != project_id:
                continue
            did = card.domain_id
            domain_counts[did] = domain_counts.get(did, 0) + 1
            if "/" in did:
                parent = did.rsplit("/", 1)[0]
                domain_counts[parent] = domain_counts.get(parent, 0) + 1

        result = []
        for (did, pid), d in self._domains.items():
            if project_id and pid != project_id:
                continue
            d.doc_count = domain_counts.get(d.domain_id, 0)
            result.append(d)
        return result

    def get_domain_catalog_text(self, project_id: str | None = None) -> str:
        """生成完整知识目录树文本（给 LLM 路由时读的）。

        这是整个 Skills 模式的核心 —— LLM 读这段文本后：
        1. 判断该查哪个知识域
        2. 直接定位到具体文档（通过文档描述）

        目录树结构：灵活层级，展开到文档描述级别。
        """
        domains = self.list_domains(project_id=project_id)

        # 按项目过滤文档卡
        project_cards = {
            doc_id: card for doc_id, card in self._doc_cards.items()
            if not project_id or self._card_project.get(doc_id) == project_id
        }

        # 构建树结构：parent_id -> children
        children_map: dict[str, list[KnowledgeDomain]] = {}
        for d in domains:
            children_map.setdefault(d.parent_id, []).append(d)

        lines: list[str] = ["# 企业知识库 · 知识体系目录\n"]
        lines.append("以下是知识库的完整目录，按 L1/L2/L3/L4 四级层级组织。")
        lines.append("每个层级标注了 [domain_id] 路径标识和文档数量。")
        lines.append("根据用户问题，选择最相关的层级路径和文档。\n")

        # 递归构建目录树
        top_level = children_map.get("", [])
        for domain in top_level:
            self._render_domain_tree(domain, children_map, lines, depth=0, cards=project_cards)

        return "\n".join(lines)

    def _render_domain_tree(
        self,
        domain: KnowledgeDomain,
        children_map: dict[str, list[KnowledgeDomain]],
        lines: list[str],
        depth: int,
        cards: dict[str, DocumentCard] | None = None,
    ) -> None:
        """递归渲染一个知识域节点及其子树。

        V8: 明确标注 L1/L2/L3/L4 层级前缀 + domain_id 方括号标记，
        让 LLM 和 SkillsRouter 能精确解析知识体系层级结构。
        零文档分支也展示，方便 LLM 了解体系全貌。
        """
        if cards is None:
            cards = self._doc_cards

        # V8: 明确层级标注
        level_label = f"L{depth + 1}"
        count_info = f"({domain.doc_count}篇)" if domain.doc_count > 0 else "(0篇)"

        if depth <= 2:
            # L1/L2/L3 用 Markdown 标题（## / ### / ####）
            prefix = "#" * (depth + 2)
            lines.append(f"{prefix} {level_label}: {domain.name} [{domain.domain_id}] {count_info}")
            if domain.description:
                lines.append(f"{domain.description}")
        else:
            # L4+ 用缩进加粗
            indent = "  " * (depth - 2)
            lines.append(f"{indent}**{level_label}: {domain.name}** [{domain.domain_id}] {count_info}")
            if domain.description:
                lines.append(f"{indent}{domain.description}")

        # 该域直接挂载的文档卡（不含子域的）
        direct_cards = [c for c in cards.values() if c.domain_id == domain.domain_id]
        indent = "  " * max(depth, 1)
        for card in direct_cards:
            desc_suffix = f" — {card.description[:100]}" if card.description else ""
            lines.append(f"{indent}- [{card.doc_id}] {card.title}{desc_suffix}")
            if card.key_elements:
                elements_str = "；".join(card.key_elements[:5])
                lines.append(f"{indent}  关键要素：{elements_str}")

        # 递归子域
        sub_domains = children_map.get(domain.domain_id, [])
        for sub in sub_domains:
            self._render_domain_tree(sub, children_map, lines, depth + 1, cards=cards)

        lines.append("")

    def _get_project_for_domain(self, domain_id: str) -> str | None:
        """查找某个 domain_id 属于哪个项目（多项目时返回第一个匹配）。"""
        for (did, pid) in self._domains:
            if did == domain_id:
                return pid
        return None

    def get_refiner_domain_list(self, project_id: str | None = None) -> str:
        """生成供 Refiner Agent 使用的知识域选项列表文本。

        V8: 使用 L1/L2/L3 层级标注，让 Refiner 精确选择 domain_id。
        """
        domains = self.list_domains(project_id=project_id)
        if not domains:
            return ""
        children_map: dict[str, list[KnowledgeDomain]] = {}
        for d in domains:
            children_map.setdefault(d.parent_id, []).append(d)

        lines: list[str] = []
        for d in children_map.get("", []):
            desc = f" — {d.description[:100]}" if d.description else ""
            lines.append(f"- L1 [{d.domain_id}]: {d.name}{desc}")
            for child in children_map.get(d.domain_id, []):
                desc = f" — {child.description[:80]}" if child.description else ""
                lines.append(f"  - L2 [{child.domain_id}]: {child.name}{desc}")
                for grandchild in children_map.get(child.domain_id, []):
                    desc = f" — {grandchild.description[:60]}" if grandchild.description else ""
                    lines.append(f"    - L3 [{grandchild.domain_id}]: {grandchild.name}{desc}")
                    for leaf in children_map.get(grandchild.domain_id, []):
                        desc = f" — {leaf.description[:40]}" if leaf.description else ""
                        lines.append(f"      - L4 [{leaf.domain_id}]: {leaf.name}{desc}")
        return "\n".join(lines)

    # ── 文档卡操作 ──────────────────────────────────────

    async def upsert_doc_card(self, card: DocumentCard, project_id: str = "default") -> None:
        """创建或更新文档索引卡。"""
        self._doc_cards[card.doc_id] = card
        self._card_project[card.doc_id] = project_id

        if self._use_memory or not self._pg_conn:
            return

        async with self._pg_conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO document_cards (doc_id, title, domain_id, description, key_elements, keywords, project_id)
                VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s)
                ON CONFLICT (doc_id) DO UPDATE SET
                    title = EXCLUDED.title,
                    domain_id = EXCLUDED.domain_id,
                    description = EXCLUDED.description,
                    key_elements = EXCLUDED.key_elements,
                    keywords = EXCLUDED.keywords,
                    project_id = EXCLUDED.project_id
                """,
                (
                    card.doc_id,
                    card.title,
                    card.domain_id,
                    card.description,
                    json.dumps(card.key_elements, ensure_ascii=False),
                    ",".join(card.keywords),
                    project_id,
                ),
            )
            await self._pg_conn.commit()

    def get_doc_cards_in_domain(self, domain_id: str) -> list[DocumentCard]:
        """获取某知识域下的所有文档卡（含子域）。"""
        return [
            c for c in self._doc_cards.values()
            if c.domain_id == domain_id or c.domain_id.startswith(domain_id + "/")
        ]

    def get_doc_card(self, doc_id: str) -> DocumentCard | None:
        return self._doc_cards.get(doc_id)

    @property
    def domain_count(self) -> int:
        return len(self._domains)

    @property
    def card_count(self) -> int:
        return len(self._doc_cards)

    async def clear_doc_cards(self) -> None:
        """清除所有文档卡（保留系统域定义）。"""
        self._doc_cards.clear()
        # 重置域的 doc_count
        for d in self._domains.values():
            d.doc_count = 0
        log.info("domain_store_cards_cleared")

    async def reload_from_pg(self) -> int:
        """从 PG 重新加载文档卡到内存（不清除域定义）。"""
        if self._use_memory or not self._pg_conn:
            return 0
        old_count = len(self._doc_cards)
        self._doc_cards.clear()
        self._card_project.clear()
        await self._load_domains_from_pg()
        log.info("domain_store_reloaded", old=old_count, new=len(self._doc_cards))
        return len(self._doc_cards)

    async def close(self) -> None:
        pass
