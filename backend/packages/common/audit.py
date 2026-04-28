"""审计日志 — 记录系统关键操作，支持内存和 PostgreSQL 模式。"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from packages.common import get_logger

log = get_logger("audit")


class AuditAction(str, Enum):
    DOCUMENT_INGESTED = "document_ingested"
    DOCUMENT_DISCARDED = "document_discarded"
    DOCUMENT_ARCHIVED = "document_archived"
    DOCUMENT_RESTORED = "document_restored"
    QA_QUERY = "qa_query"
    SEARCH_QUERY = "search_query"
    REVIEW_RESOLVED = "review_resolved"
    PERMISSION_DENIED = "permission_denied"


class AuditEntry(BaseModel):
    """审计日志条目。"""

    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    action: AuditAction
    user_id: str = ""
    org_id: str = "default"
    resource_type: str = ""
    resource_id: str = ""
    details: dict = Field(default_factory=dict)
    duration_ms: int = 0


class AuditLogger:
    """审计日志器，支持内存缓冲和 PostgreSQL 持久化。"""

    def __init__(self, metadata_store=None):
        self._store = metadata_store
        self._buffer: list[AuditEntry] = []

    async def log(self, entry: AuditEntry) -> None:
        """记录一条审计日志。"""
        self._buffer.append(entry)
        log.info(
            "audit_log",
            action=entry.action.value,
            user_id=entry.user_id,
            org_id=entry.org_id,
            resource_type=entry.resource_type,
            resource_id=entry.resource_id,
        )

        if self._store:
            try:
                await self._store.insert_audit_log(entry)
            except Exception as e:
                log.warning("audit_log_persist_failed", error=str(e))

    async def list_logs(
        self,
        org_id: Optional[str] = None,
        action: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict]:
        """查询审计日志。"""
        # 优先从持久化存储查询
        if self._store:
            try:
                return await self._store.list_audit_logs(
                    org_id=org_id, action=action, limit=limit
                )
            except Exception:
                pass

        # 回退到内存缓冲
        results = list(self._buffer)
        if org_id:
            results = [e for e in results if e.org_id == org_id]
        if action:
            results = [e for e in results if e.action.value == action]
        results = results[-limit:]
        return [e.model_dump(mode="json") for e in results]
