"""Wiki 编译引擎 (WikiCompiler) — Layer 1 知识编译层。

Karpathy LLM Wiki 模式的核心实现：
  "用LLM的正确方式不是问答，而是编译。"

三层 Wiki 编译体系 (V11.2):
  1. source_summary — 每篇源文档一个独立 Wiki 页（知识卡片）
  2. domain_overview — 每个知识域一个概览页（聚合该域所有 source 页）
  3. index — 项目级全局索引页（目录 + 统计 + 交叉引用图）

编译流程: 文档→compile_source()→compile_domain()→compile_index()
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from packages.common import get_logger
from packages.common.types import WikiPage, RefinedResult
from packages.distillation.llm_client import call_llm
from packages.observability.wiki_quality import score_wiki_page

if TYPE_CHECKING:
    from packages.storage.domain_store import DomainStore
    from packages.storage.raw_store import RawStore
    from packages.storage.wiki_store import WikiStore

log = get_logger("distillation.wiki_compiler")

# ── Source-level Prompt (每篇文档→知识卡片) ──

SOURCE_COMPILE_SYSTEM = """你是知识图鉴(Wiki-Map)的知识编译引擎。
你的任务是将单篇文档的蒸馏产物编译为一个结构化的知识Wiki页面（知识卡片）。

输出格式要求（严格使用Markdown）：

# {文档标题}

> 文档类型: xxx | 知识域: xxx | 编译自 1 篇源文档

## 核心摘要
（150-300字精炼总结该文档的核心内容和价值）

## 关键知识点
1. **知识点标题**
   详细说明（2-3句话）
2. **知识点标题**
   详细说明

## 关键实体
| 实体 | 类型 | 说明 |
|------|------|------|
| 实体名 | 类型 | 简要说明 |

## 标准与法规引用
- 标准编号 标准名称（如有）

## 关键要素清单
- 要素1
- 要素2

## 交叉引用
- → [[相关域ID]] 相关域名称 （关联原因）

规则：
- 实体类型从: 人物/部门/设备装置/制度法规/流程工艺/物料化学品/标准规范/位置区域 中选择
- 交叉引用使用 [[domain_id]] 格式
- 尽量提取所有关键知识点，但避免过于琐碎
- 语言使用中文，专业术语保留原文"""

SOURCE_COMPILE_USER = """请为以下文档编译知识Wiki页面（知识卡片）。

文档ID: {doc_id}
文档标题: {doc_title}
所属知识域: {domain_name} [{domain_id}]

蒸馏产物：
摘要: {summary}
关键词: {keywords}
实体: {entities}
关系: {relations}
关键要素: {key_elements}
文档描述: {doc_description}

相关域（可生成交叉引用）：
{related_domains}

请生成完整的 Markdown 知识卡片。"""

# ── Domain-level Prompt (域概览→聚合) ──

DOMAIN_COMPILE_SYSTEM = """你是知识图鉴(Wiki-Map)的知识编译引擎。
你的任务是将多篇文档的知识卡片编译为一个域级知识概览页面。

输出格式要求（严格使用Markdown）：

# {域名} 知识概览

> 编译自 N 篇源文档 | 知识域: {域ID}

## 概述
（300-500字综述该知识域的核心内容，覆盖所有文档的关键信息）

## 核心知识点
1. **知识点标题** [← 来源文档ID]
   详细说明（2-3句话）
2. **知识点标题** [← 来源文档ID]
   详细说明

## 关键实体
| 实体 | 类型 | 出现文档数 | 说明 |
|------|------|-----------|------|
| 实体名 | 类型 | N | 简要说明 |

## 标准与法规引用
- 标准编号 标准名称 [← 来源文档ID]

## 文档清单
| 序号 | 文档 | 核心价值 |
|------|------|----------|
| 1 | 文档标题 | 一句话概括 |

## 交叉引用
- → [[相关域ID]] 相关域名称 （关联原因）

规则：
- 每个知识点必须标注 [← doc_id] 溯源
- 交叉引用使用 [[domain_id]] 格式
- 实体去重，标注出现频率
- 文档清单列出该域下所有源文档
- 语言使用中文，专业术语保留原文
- 尽量多提取知识点（覆盖所有文档），但避免重复"""

DOMAIN_COMPILE_USER = """请编译以下知识域的概览Wiki页面。

知识域: {domain_name} [{domain_id}]
域描述: {domain_desc}

以下是该域下 {doc_count} 篇文档的蒸馏产物：

{doc_summaries}

相关域（可生成交叉引用）：
{related_domains}

请生成完整的 Markdown 域概览页面。"""


def _format_doc_summary(doc_id: str, result: RefinedResult) -> str:
    """格式化单篇文档的蒸馏产物。"""
    entities_str = ", ".join(
        f"{e.name}({e.type})" for e in (result.entities or [])[:15]
    )
    relations_str = "; ".join(
        f"{r.source}→{r.relation}→{r.target}" for r in (result.relations or [])[:10]
    )
    keywords_str = ", ".join(result.keywords[:10]) if result.keywords else ""

    return f"""--- 文档: {doc_id} ---
摘要: {result.summary}
关键词: {keywords_str}
实体: {entities_str}
关系: {relations_str}
关键要素: {', '.join(result.key_elements[:5]) if result.key_elements else '无'}
"""


def _extract_summary(content: str, section: str = "## 概述", max_len: int = 200) -> str:
    """从 Markdown 内容提取摘要段落。"""
    lines = content.split("\n")
    for i, line in enumerate(lines):
        if line.startswith(section) or line.startswith("## 核心摘要"):
            para_lines = []
            for sl in lines[i + 1:]:
                if sl.startswith("##"):
                    break
                if sl.strip():
                    para_lines.append(sl.strip())
            return " ".join(para_lines)[:max_len]
    return content[:max_len].replace("\n", " ")


class WikiCompiler:
    """知识编译器 — Karpathy LLM Wiki 模式的核心实现。

    三层编译体系:
    - compile_source():  每篇文档 → 独立知识卡片 (source_summary)
    - compile_domain():  每个域 → 域级概览 (domain_overview)
    - compile_index():   全项目 → 索引页 (index)
    - compile_project(): 编排以上三步
    """

    def __init__(
        self,
        raw_store: RawStore,
        wiki_store: WikiStore,
        domain_store: DomainStore,
        auto_score: bool = True,
    ):
        self.raw_store = raw_store
        self.wiki_store = wiki_store
        self.domain_store = domain_store
        self.auto_score = auto_score

    async def _try_score_page(self, page: WikiPage, project_id: str) -> None:
        """M18 #1 · 编译完成后自动 6 维评分；失败不阻塞编译。"""
        if not self.auto_score:
            return
        try:
            score = await score_wiki_page(
                page_id=page.page_id,
                page_type=page.page_type,
                title=page.title,
                content=page.content,
                source_doc_count=len(page.source_doc_ids),
                cross_ref_count=len(page.cross_refs),
                version=1,
                project_id=project_id,
            )
            if score.quality_alert:
                log.warning(
                    "wiki_quality_alert",
                    page_id=page.page_id,
                    overall=score.overall,
                )
        except Exception as e:  # 兜底：评分失败不影响编译流程
            log.warning(
                "wiki_quality_score_failed",
                page_id=page.page_id, error=str(e),
            )

    # ── Per-Source Compilation ──

    async def compile_source(
        self,
        doc_id: str,
        doc_title: str,
        domain_id: str,
        domain_name: str,
        refined_result: RefinedResult,
        related_domains: list[tuple[str, str]] | None = None,
        project_id: str = "default",
    ) -> WikiPage:
        """编译单篇文档的知识卡片。

        Karpathy 模式核心: 每篇源文档生成独立的 Wiki 页。
        """
        entities_str = ", ".join(
            f"{e.name}({e.type})" for e in (refined_result.entities or [])[:20]
        )
        relations_str = "; ".join(
            f"{r.source}→{r.relation}→{r.target}" for r in (refined_result.relations or [])[:15]
        )
        keywords_str = ", ".join(refined_result.keywords[:10]) if refined_result.keywords else ""
        key_elements_str = ", ".join(refined_result.key_elements[:8]) if refined_result.key_elements else "无"
        related_str = "\n".join(
            f"- [[{did}]] {dname}" for did, dname in (related_domains or [])
        ) or "暂无相关域"

        user_prompt = SOURCE_COMPILE_USER.format(
            doc_id=doc_id,
            doc_title=doc_title or doc_id,
            domain_name=domain_name,
            domain_id=domain_id,
            summary=refined_result.summary or "",
            keywords=keywords_str,
            entities=entities_str,
            relations=relations_str,
            key_elements=key_elements_str,
            doc_description=refined_result.doc_description or "",
            related_domains=related_str,
        )

        log.info("wiki_compiling_source", doc_id=doc_id, domain_id=domain_id)
        content = call_llm(SOURCE_COMPILE_SYSTEM, user_prompt, max_tokens=2048)

        # sanitize doc_id: 只保留字母数字和安全字符
        safe_doc_id = "".join(c if c.isalnum() or c in "-_." else "_" for c in doc_id)
        page_id = f"src/{safe_doc_id}"
        summary = _extract_summary(content, "## 核心摘要")

        page = WikiPage(
            page_id=page_id,
            title=doc_title or doc_id,
            content=content,
            summary=summary,
            page_type="source_summary",
            parent_page_id=domain_id,
            source_doc_ids=[doc_id],
            cross_refs=[did for did, _ in (related_domains or [])],
            compiled_at=datetime.now(timezone.utc),
            status="published",
        )

        await self.wiki_store.upsert_page(page, project_id=project_id)
        log.info("wiki_source_compiled", page_id=page_id, content_len=len(content))
        await self._try_score_page(page, project_id)
        return page

    # ── Domain-level Compilation ──

    async def compile_domain(
        self,
        domain_id: str,
        domain_name: str,
        domain_desc: str,
        project_id: str,
        refined_results: list[tuple[str, RefinedResult]],
        related_domains: list[tuple[str, str]] | None = None,
    ) -> WikiPage:
        """编译域级概览 Wiki 页。"""
        if not refined_results:
            log.warning("wiki_compile_skip_empty_domain", domain_id=domain_id)
            return WikiPage(
                page_id=domain_id, title=domain_name, content="暂无文档",
                page_type="domain_overview", status="draft",
            )

        doc_summaries = "\n".join(
            _format_doc_summary(doc_id, result)
            for doc_id, result in refined_results
        )

        related_str = "\n".join(
            f"- [[{did}]] {dname}"
            for did, dname in (related_domains or [])
        ) or "暂无相关域"

        user_prompt = DOMAIN_COMPILE_USER.format(
            domain_name=domain_name,
            domain_id=domain_id,
            domain_desc=domain_desc or f"{domain_name}相关知识",
            doc_count=len(refined_results),
            doc_summaries=doc_summaries,
            related_domains=related_str,
        )

        log.info("wiki_compiling_domain", domain_id=domain_id, doc_count=len(refined_results))
        content = call_llm(DOMAIN_COMPILE_SYSTEM, user_prompt, max_tokens=4096)

        source_doc_ids = [doc_id for doc_id, _ in refined_results]
        cross_refs = [did for did, _ in (related_domains or [])]
        summary = _extract_summary(content)

        page = WikiPage(
            page_id=domain_id,
            title=domain_name,
            content=content,
            summary=summary,
            page_type="domain_overview",
            parent_page_id="index",
            source_doc_ids=source_doc_ids,
            cross_refs=cross_refs,
            compiled_at=datetime.now(timezone.utc),
            status="published",
        )

        await self.wiki_store.upsert_page(page, project_id=project_id)
        log.info("wiki_domain_compiled", domain_id=domain_id, content_len=len(content))
        await self._try_score_page(page, project_id)
        return page

    # ── Index Page Compilation ──

    async def compile_index(
        self,
        project_id: str,
        domain_pages: list[WikiPage],
        source_pages: list[WikiPage],
    ) -> WikiPage:
        """生成项目级索引页 — Karpathy 架构的 index.md。

        不需要 LLM，直接从已编译的页面元数据生成结构化目录。
        """
        lines = [
            "# 知识图鉴 Wiki 索引",
            "",
            f"> 共 {len(domain_pages)} 个知识域 · {len(source_pages)} 篇文档知识卡片",
            "",
            "## 知识域概览",
            "",
        ]

        # 按域分组 source pages
        domain_sources: dict[str, list[WikiPage]] = {}
        for sp in source_pages:
            pid = sp.parent_page_id or "未分类"
            domain_sources.setdefault(pid, []).append(sp)

        for dp in sorted(domain_pages, key=lambda p: p.page_id):
            src_count = len(domain_sources.get(dp.page_id, []))
            lines.append(f"### [[{dp.page_id}]] {dp.title}")
            if dp.summary:
                lines.append(f"> {dp.summary[:150]}")
            lines.append(f"- 文档数: {src_count}")
            if dp.cross_refs:
                refs = ", ".join(f"[[{ref}]]" for ref in dp.cross_refs[:5])
                lines.append(f"- 关联域: {refs}")
            lines.append("")

            # 列出该域下的源文档
            for sp in domain_sources.get(dp.page_id, []):
                lines.append(f"  - [[{sp.page_id}]] {sp.title}")
            lines.append("")

        # 未归类的源文档
        uncategorized = domain_sources.get("未分类", [])
        if uncategorized:
            lines.append("### 未归类文档")
            for sp in uncategorized:
                lines.append(f"  - [[{sp.page_id}]] {sp.title}")
            lines.append("")

        # 统计信息
        total_cross_refs = sum(len(p.cross_refs) for p in domain_pages)
        lines.extend([
            "## 统计",
            "",
            f"| 指标 | 数值 |",
            f"|------|------|",
            f"| 知识域 | {len(domain_pages)} |",
            f"| 文档知识卡片 | {len(source_pages)} |",
            f"| 交叉引用数 | {total_cross_refs} |",
            f"| 编译时间 | {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} |",
        ])

        content = "\n".join(lines)

        page = WikiPage(
            page_id="index",
            title="Wiki 索引",
            content=content,
            summary=f"共 {len(domain_pages)} 个知识域, {len(source_pages)} 篇文档知识卡片",
            page_type="index",
            parent_page_id="",
            source_doc_ids=[],
            cross_refs=[dp.page_id for dp in domain_pages],
            compiled_at=datetime.now(timezone.utc),
            status="published",
        )

        await self.wiki_store.upsert_page(page, project_id=project_id)
        log.info("wiki_index_compiled", domains=len(domain_pages), sources=len(source_pages))
        return page

    # ── Project-level Orchestration ──

    async def compile_project(
        self,
        project_id: str,
        domain_results: dict[str, list[tuple[str, RefinedResult]]] | None = None,
    ) -> list[WikiPage]:
        """编译整个项目: source → domain → index。

        Karpathy 模式: 每篇文档先生成独立知识卡片，
        再由域概览聚合，最后生成全局索引。
        """
        if not domain_results:
            log.warning("wiki_compile_project_no_results", project_id=project_id)
            return []

        domains = self.domain_store.list_domains(project_id=project_id)
        domain_map = {d.domain_id: d for d in domains}

        # 优先编译 L2+ 域，但也保留有文档的顶级域（不再静默跳过）
        compile_domains = {did: results for did, results in domain_results.items() if results}
        if not compile_domains:
            log.warning("wiki_compile_no_domains_with_results", project_id=project_id)
            return []

        all_domain_ids = list(compile_domains.keys())
        source_pages: list[WikiPage] = []
        domain_pages: list[WikiPage] = []

        # Phase 0: 仅标记本批次涉及的域的页面为 stale（增量安全：不影响未变更的域）
        try:
            existing_pages = await self.wiki_store.list_pages(project_id=project_id)
            stale_count = 0
            for ep in existing_pages:
                if ep.status != "published":
                    continue
                # 只标记: 本批次涉及的域页、对应的source页、以及index页(需重建)
                should_stale = (
                    ep.page_type == "index"
                    or ep.page_id in compile_domains
                    or (ep.page_type == "source_summary" and ep.parent_page_id in compile_domains)
                )
                if should_stale:
                    await self.wiki_store.mark_stale(ep.page_id, project_id=project_id)
                    stale_count += 1
            if stale_count:
                log.info("wiki_marked_stale", count=stale_count, total_existing=len(existing_pages))
        except Exception as e:
            log.warning("wiki_mark_stale_failed", error=str(e))

        # Phase 1: 编译每篇源文档的知识卡片
        log.info("wiki_phase1_source_compilation", total_docs=sum(len(v) for v in compile_domains.values()))
        for domain_id, results in compile_domains.items():
            domain_info = domain_map.get(domain_id)
            domain_name = domain_info.name if domain_info else domain_id.split("/")[-1]

            # 找相关域
            parts = domain_id.split("/")
            parent = "/".join(parts[:-1]) if len(parts) > 1 else ""
            related = []
            for did in all_domain_ids:
                if did == domain_id:
                    continue
                if parent and did.startswith(parent + "/"):
                    dname = domain_map[did].name if did in domain_map else did.split("/")[-1]
                    related.append((did, dname))
                elif not parent and did != domain_id:
                    dname = domain_map[did].name if did in domain_map else did.split("/")[-1]
                    related.append((did, dname))
                if len(related) >= 5:
                    break

            for doc_id, refined_result in results:
                try:
                    # 从 raw_store 获取文档标题
                    raw_doc = await self.raw_store.get_raw(doc_id, project_id=project_id)
                    doc_title = raw_doc.get("title", doc_id) if raw_doc else doc_id

                    page = await self.compile_source(
                        doc_id=doc_id,
                        doc_title=doc_title,
                        domain_id=domain_id,
                        domain_name=domain_name,
                        refined_result=refined_result,
                        related_domains=related,
                        project_id=project_id,
                    )
                    source_pages.append(page)
                except Exception as e:
                    log.error("wiki_compile_source_failed", doc_id=doc_id, error=str(e))

        # Phase 2: 编译每个域的概览页（仅包含 source 编译成功的文档）
        compiled_source_ids = {p.source_doc_ids[0] for p in source_pages if p.source_doc_ids}
        log.info("wiki_phase2_domain_compilation", domain_count=len(compile_domains),
                 source_compiled=len(compiled_source_ids))
        for domain_id, results in compile_domains.items():
            # 过滤掉 source 编译失败的文档，确保 domain 概览与 source 页一致
            results = [(did, r) for did, r in results if did in compiled_source_ids]
            if not results:
                log.warning("wiki_domain_skip_no_compiled_sources", domain_id=domain_id)
                continue
            domain_info = domain_map.get(domain_id)
            domain_name = domain_info.name if domain_info else domain_id.split("/")[-1]
            domain_desc = domain_info.description if domain_info else ""

            parts = domain_id.split("/")
            parent = "/".join(parts[:-1]) if len(parts) > 1 else ""
            related = []
            for did in all_domain_ids:
                if did == domain_id:
                    continue
                if parent and did.startswith(parent + "/"):
                    dname = domain_map[did].name if did in domain_map else did.split("/")[-1]
                    related.append((did, dname))
                elif not parent and did != domain_id:
                    dname = domain_map[did].name if did in domain_map else did.split("/")[-1]
                    related.append((did, dname))
                if len(related) >= 5:
                    break

            try:
                page = await self.compile_domain(
                    domain_id=domain_id,
                    domain_name=domain_name,
                    domain_desc=domain_desc,
                    project_id=project_id,
                    refined_results=results,
                    related_domains=related,
                )
                domain_pages.append(page)
            except Exception as e:
                log.error("wiki_compile_domain_failed", domain_id=domain_id, error=str(e))

        # Phase 3: 生成索引页（合并本批次 + 已有未变更的 published 域页，保证索引完整）
        log.info("wiki_phase3_index_compilation")
        try:
            # 收集已有的未被本批次覆盖的 published 域页和源页
            all_existing = await self.wiki_store.list_pages(project_id=project_id)
            compiled_page_ids = {p.page_id for p in domain_pages + source_pages}
            existing_domain_pages = [
                p for p in all_existing
                if p.page_type == "domain_overview" and p.status == "published" and p.page_id not in compiled_page_ids
            ]
            existing_source_pages = [
                p for p in all_existing
                if p.page_type == "source_summary" and p.status == "published" and p.page_id not in compiled_page_ids
            ]
            index_page = await self.compile_index(
                project_id,
                domain_pages + existing_domain_pages,
                source_pages + existing_source_pages,
            )
        except Exception as e:
            log.error("wiki_compile_index_failed", error=str(e))
            index_page = None

        all_pages = source_pages + domain_pages
        if index_page:
            all_pages.append(index_page)

        # V14: 恢复未被本批次重编译的 stale 页面为 published
        try:
            compiled_ids = {p.page_id for p in all_pages}
            still_stale = await self.wiki_store.list_pages(project_id=project_id, status="stale")
            for sp in still_stale:
                if sp.page_id not in compiled_ids:
                    await self.wiki_store.restore_published(sp.page_id, project_id=project_id)
            if still_stale:
                log.info("wiki_stale_restored", count=len([s for s in still_stale if s.page_id not in compiled_ids]))
        except Exception as e:
            log.warning("wiki_stale_restore_failed", error=str(e))

        log.info(
            "wiki_project_compiled", project_id=project_id,
            source_pages=len(source_pages), domain_pages=len(domain_pages),
            has_index=index_page is not None,
        )
        return all_pages
