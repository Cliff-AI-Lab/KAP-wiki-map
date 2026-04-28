"""Auditor Agent — 纵向溯源审计.

扫所有 domain_overview 级 Wiki 页, LLM judge 内容是否有 source_doc_ids 支撑.
溯源分数低于阈值 → 产 unverified 工单.
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from packages.common import get_logger
from packages.common.types import GovernanceQueueItem
from packages.distillation.llm_client import call_llm_json
from packages.governance.agents.base import BaseGovernanceAgent, AgentRunResult
from packages.storage.governance_queue_store import GovernanceQueueStore
from packages.storage.raw_store import RawStore
from packages.storage.wiki_store import WikiStore

log = get_logger("governance.auditor")


AUDIT_PROMPT_SYSTEM = """你是知识图鉴的 Auditor — 专家级事实审计员。
你的任务: 给定一段 Wiki 内容 和 它声称所依据的 RAW 源文档摘要，
判断 Wiki 内容的每条关键断言是否能在源文档里找到支撑。

硬约束:
- 只基于提供的 RAW 文档判断，不依赖外部知识
- 返回 JSON，不要额外文字
- 断言不一定要逐字出现，但核心事实须可溯源
- Schema:
  {
    "provenance_score": 0-100 (整体溯源分),
    "missing_claims": ["断言1", "断言2", ...] (无法溯源的关键断言列表, 最多 5 条),
    "reason": "简要说明为什么分数是这个值 (1-2 句)"
  }
"""

AUDIT_PROMPT_USER_TEMPLATE = """Wiki 页内容:
---
{wiki_content}
---

RAW 源文档摘要:
---
{raw_snippets}
---

请做事实审计并返回 JSON。"""


# provenance_score < THRESHOLD 时产生工单
UNVERIFIED_THRESHOLD = 70
# 每页送进 LLM 的 content 上限 (避免超长)
WIKI_CONTENT_MAX_CHARS = 3500
# 每条 Raw snippet 上限
RAW_SNIPPET_MAX_CHARS = 500


class AuditorAgent(BaseGovernanceAgent):
    name = "auditor"

    async def run(
        self,
        project_id: str,
        queue_store: GovernanceQueueStore,
        wiki_store: WikiStore = None,
        raw_store: RawStore = None,
        **_: Any,
    ) -> AgentRunResult:
        result = AgentRunResult(agent=self.name, ok=True)

        if wiki_store is None or raw_store is None:
            result.ok = False
            result.errors.append("缺少 wiki_store / raw_store 依赖")
            return result

        try:
            pages = await wiki_store.list_pages(project_id, page_type="domain_overview")
        except Exception as e:
            result.ok = False
            result.errors.append(f"拉取 Wiki 页失败: {e}")
            return result

        for page in pages:
            result.scanned += 1

            # 拉 source_doc_ids 对应 Raw 文档摘要
            source_docs = page.source_doc_ids or []
            if not source_docs:
                # 无来源 → 直接低分
                await self._push(queue_store, self._make_item(
                    project_id=project_id,
                    page_id=page.page_id,
                    title=f"[审计] {page.title[:40]} 无任何 Raw 引用",
                    description="Auditor: 该 Wiki 页 source_doc_ids 为空",
                    priority=85,
                ))
                result.produced += 1
                continue

            # 拼 RAW snippets
            snippets: list[str] = []
            for doc_id in source_docs[:6]:
                try:
                    raw = await raw_store.get_raw(doc_id, project_id=project_id)
                    if raw:
                        content = (raw.get("full_content") or raw.get("content") or "")[:RAW_SNIPPET_MAX_CHARS]
                        snippets.append(f"[{doc_id}]\n{content}")
                except Exception as e:
                    log.warning("auditor_raw_fetch_failed", doc_id=doc_id, error=str(e))
            if not snippets:
                # Bug3 修复: 引用失效/原文丢失也产工单
                missing_ids = ", ".join(source_docs[:6])
                await self._push(queue_store, self._make_item(
                    project_id=project_id,
                    page_id=page.page_id,
                    title=f"[审计] {page.title[:40]} 引用失效",
                    description=f"Auditor: source_doc_ids 中 {len(source_docs)} 个 Raw 全部读取失败 — 可能已被删除或归档\n失效引用: {missing_ids}",
                    priority=80,
                ))
                result.produced += 1
                continue
            raw_text = "\n\n".join(snippets)

            wiki_content = (page.content or "")[:WIKI_CONTENT_MAX_CHARS]
            if not wiki_content.strip():
                result.skipped += 1
                continue

            # LLM judge
            try:
                judgment = call_llm_json(
                    system_prompt=AUDIT_PROMPT_SYSTEM,
                    user_prompt=AUDIT_PROMPT_USER_TEMPLATE.format(
                        wiki_content=wiki_content,
                        raw_snippets=raw_text,
                    ),
                    temperature=0.0,
                )
            except Exception as e:
                log.warning("auditor_llm_failed", page=page.page_id, error=str(e))
                result.errors.append(f"{page.page_id}: {e}")
                continue

            score = _safe_int(judgment.get("provenance_score"), default=100)
            missing = judgment.get("missing_claims") or []
            reason = str(judgment.get("reason") or "")[:200]

            if score < UNVERIFIED_THRESHOLD or missing:
                missing_str = ""
                if missing:
                    bullets = "\n".join(f"  • {c}" for c in missing[:5])
                    missing_str = f"\n\n缺源断言 ({len(missing)}):\n{bullets}"
                desc = f"Auditor: {reason}{missing_str}"
                await self._push(queue_store, self._make_item(
                    project_id=project_id,
                    page_id=page.page_id,
                    title=f"[审计] {page.title[:40]} 溯源不足 {score}%",
                    description=desc,
                    priority=_priority_from_score(score),
                ))
                result.produced += 1

        result.detail["threshold"] = UNVERIFIED_THRESHOLD
        log.info("auditor_run_done", project=project_id,
                 scanned=result.scanned, produced=result.produced,
                 skipped=result.skipped, errors=len(result.errors))
        return result

    def _make_item(
        self,
        project_id: str,
        page_id: str,
        title: str,
        description: str,
        priority: int,
    ) -> GovernanceQueueItem:
        return GovernanceQueueItem(
            id=f"gq_{uuid.uuid4().hex[:10]}",
            project_id=project_id,
            agent="auditor",
            kind="unverified",
            title=title,
            description=description,
            target_ref=f"page/{page_id}",
            priority=priority,
            status="pending",
            created_at=datetime.now(timezone.utc),
        )


def _safe_int(v, default: int = 0) -> int:
    try:
        return int(v)
    except Exception:
        if isinstance(v, str):
            m = re.search(r"\d+", v)
            if m:
                return int(m.group())
        return default


def _priority_from_score(score: int) -> int:
    """溯源分越低，工单优先级越高。"""
    if score < 30:
        return 90
    if score < 50:
        return 75
    if score < 70:
        return 60
    return 45
