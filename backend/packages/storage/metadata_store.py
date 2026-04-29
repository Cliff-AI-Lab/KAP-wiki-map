"""PostgreSQL 元数据存储 — 文档记录、管线状态、审核队列。

PoC 阶段使用内存字典作为 fallback，无需强依赖 PostgreSQL。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from packages.common import get_logger, settings
from packages.common.types import Decision, DocStatus

# 延迟导入避免循环
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from packages.common.audit import AuditEntry

log = get_logger("storage.metadata")

# 低于此置信度的 Judge 决策需要人工审核（从配置读取）
REVIEW_CONFIDENCE_THRESHOLD: float = settings.review_confidence_threshold


class MetadataStore:
    """元数据存储，支持 PostgreSQL 和内存模式。"""

    def __init__(self, use_memory: bool = False):
        self._use_memory = use_memory
        self._memory: dict[str, dict] = {}
        self._review_queue: list[dict] = []  # 内存模式审核队列
        self._audit_buffer: list[dict] = []  # 内存模式审计日志
        self._conn = None
        # V14: 分析暂存区 — batch_id → {results, raw_docs, project_id, created_at}
        self._staging: dict[str, dict] = {}

    async def initialize(self) -> None:
        if self._use_memory:
            log.info("metadata_store_memory_mode")
            return

        try:
            import psycopg

            self._conn = await psycopg.AsyncConnection.connect(settings.postgres_dsn)
            await self._create_tables()
            log.info("metadata_store_pg_connected")
        except Exception as e:
            log.warning("metadata_store_pg_fallback_to_memory", error=str(e))
            self._use_memory = True

    async def _create_tables(self) -> None:
        assert self._conn is not None
        async with self._conn.cursor() as cur:
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS documents (
                    id              VARCHAR(64) PRIMARY KEY,
                    title           VARCHAR(512) NOT NULL,
                    source_system   VARCHAR(32) NOT NULL,
                    doc_type        VARCHAR(64),
                    version_id      VARCHAR(32),
                    status          VARCHAR(16) DEFAULT 'ACTIVE',
                    decision        VARCHAR(16),
                    kpi_retain      DECIMAL(6,4),
                    summary         TEXT,
                    keywords        TEXT,
                    judge_reasoning JSONB,
                    department_id   VARCHAR(64),
                    dept_id         INT,
                    created_by      VARCHAR(64),
                    access_level    VARCHAR(16) DEFAULT 'INTERNAL',
                    category_path   VARCHAR(256),
                    org_id          VARCHAR(64) DEFAULT 'default',
                    created_at      TIMESTAMPTZ,
                    updated_at      TIMESTAMPTZ,
                    ingested_at     TIMESTAMPTZ DEFAULT NOW()
                )
            """)
            # M1 ISS DataScope 激活 — 给已存在的旧 documents 表补字段（idempotent）
            await cur.execute("ALTER TABLE documents ADD COLUMN IF NOT EXISTS dept_id INT")
            await cur.execute("ALTER TABLE documents ADD COLUMN IF NOT EXISTS created_by VARCHAR(64)")
            await cur.execute("""
                CREATE TABLE IF NOT EXISTS manual_review_queue (
                    id              SERIAL PRIMARY KEY,
                    doc_id          VARCHAR(64) NOT NULL REFERENCES documents(id),
                    proposed_decision VARCHAR(16) NOT NULL,
                    confidence      DECIMAL(4,3) NOT NULL,
                    kpi_retain      DECIMAL(6,4),
                    reason          TEXT,
                    status          VARCHAR(16) DEFAULT 'PENDING',
                    reviewer        VARCHAR(64),
                    reviewed_at     TIMESTAMPTZ,
                    final_decision  VARCHAR(16),
                    created_at      TIMESTAMPTZ DEFAULT NOW()
                )
            """)
            await self._conn.commit()

    async def upsert_document(self, doc_record: dict) -> None:
        doc_id = doc_record["id"]
        # 确保可选字段有默认值
        doc_record.setdefault("access_level", "INTERNAL")
        doc_record.setdefault("department_id", "")
        doc_record.setdefault("dept_id", None)        # M1 ISS DataScope int 部门
        doc_record.setdefault("created_by", "")        # M1 ISS DataScope SELF
        doc_record.setdefault("judge_reasoning", None)

        if self._use_memory:
            self._memory[doc_id] = doc_record
            return

        assert self._conn is not None
        import json as _json
        # JSONB 字段需要序列化
        jr = doc_record.get("judge_reasoning")
        pg_record = {**doc_record}
        pg_record["judge_reasoning"] = _json.dumps(jr, ensure_ascii=False, default=str) if jr else None

        async with self._conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO documents (id, title, source_system, doc_type, version_id,
                    status, decision, kpi_retain, summary, keywords, category_path,
                    org_id, created_at, updated_at, access_level, department_id,
                    dept_id, created_by, judge_reasoning)
                VALUES (%(id)s, %(title)s, %(source_system)s, %(doc_type)s, %(version_id)s,
                    %(status)s, %(decision)s, %(kpi_retain)s, %(summary)s, %(keywords)s,
                    %(category_path)s, %(org_id)s, %(created_at)s, %(updated_at)s,
                    %(access_level)s, %(department_id)s, %(dept_id)s, %(created_by)s,
                    %(judge_reasoning)s::jsonb)
                ON CONFLICT (id) DO UPDATE SET
                    status = EXCLUDED.status,
                    decision = EXCLUDED.decision,
                    kpi_retain = EXCLUDED.kpi_retain,
                    summary = EXCLUDED.summary,
                    keywords = EXCLUDED.keywords,
                    access_level = EXCLUDED.access_level,
                    department_id = EXCLUDED.department_id,
                    dept_id = EXCLUDED.dept_id,
                    created_by = EXCLUDED.created_by,
                    judge_reasoning = EXCLUDED.judge_reasoning
                """,
                pg_record,
            )
            await self._conn.commit()

    async def get_document(self, doc_id: str) -> Optional[dict]:
        if self._use_memory:
            return self._memory.get(doc_id)
        # PostgreSQL 实现
        assert self._conn is not None
        async with self._conn.cursor() as cur:
            await cur.execute("SELECT * FROM documents WHERE id = %s", (doc_id,))
            row = await cur.fetchone()
            if row and cur.description:
                return dict(zip([d.name for d in cur.description], row))
            return None

    async def list_documents(
        self,
        status: Optional[str] = None,
        decision: Optional[str] = None,
        org_id: Optional[str] = None,
    ) -> list[dict]:
        if self._use_memory:
            results = list(self._memory.values())
            if status:
                results = [r for r in results if r.get("status") == status]
            if decision:
                results = [r for r in results if r.get("decision") == decision]
            if org_id:
                results = [r for r in results if r.get("org_id", "default") == org_id]
            return results

        assert self._conn is not None
        async with self._conn.cursor() as cur:
            clauses = []
            params: list = []
            if status:
                clauses.append("status = %s")
                params.append(status)
            if decision:
                clauses.append("decision = %s")
                params.append(decision)
            if org_id:
                clauses.append("org_id = %s")
                params.append(org_id)
            where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
            await cur.execute(
                f"SELECT * FROM documents{where} ORDER BY ingested_at DESC",
                params,
            )
            rows = await cur.fetchall()
            if rows and cur.description:
                cols = [d.name for d in cur.description]
                return [dict(zip(cols, row)) for row in rows]
        return []

    # ── 审核队列 ──────────────────────────────────────────

    async def enqueue_review(
        self,
        doc_id: str,
        proposed_decision: str,
        confidence: float,
        kpi_retain: float | None = None,
        reason: str = "",
    ) -> None:
        """将低置信度决策加入人工审核队列。"""
        item = {
            "doc_id": doc_id,
            "proposed_decision": proposed_decision,
            "confidence": confidence,
            "kpi_retain": kpi_retain,
            "reason": reason,
            "status": "PENDING",
            "reviewer": None,
            "reviewed_at": None,
            "final_decision": None,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        if self._use_memory:
            self._review_queue.append(item)
            log.info("review_enqueued_memory", doc_id=doc_id, confidence=confidence)
            return

        assert self._conn is not None
        async with self._conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO manual_review_queue
                    (doc_id, proposed_decision, confidence, kpi_retain, reason)
                VALUES (%(doc_id)s, %(proposed_decision)s, %(confidence)s,
                        %(kpi_retain)s, %(reason)s)
                """,
                item,
            )
            await self._conn.commit()
        log.info("review_enqueued_pg", doc_id=doc_id, confidence=confidence)

    async def list_review_queue(
        self, status: str = "PENDING", project_id: str | None = None,
    ) -> list[dict]:
        """列出审核队列中的条目（支持按项目过滤）。"""
        if self._use_memory:
            items = [r for r in self._review_queue if r.get("status") == status]
            if project_id:
                # 通过关联文档的 org_id 过滤
                items = [
                    r for r in items
                    if self._memory.get(r["doc_id"], {}).get("org_id") == project_id
                ]
            return items

        assert self._conn is not None
        async with self._conn.cursor() as cur:
            if project_id:
                await cur.execute(
                    """SELECT r.* FROM manual_review_queue r
                       JOIN documents d ON r.doc_id = d.id
                       WHERE r.status = %s AND d.org_id = %s
                       ORDER BY r.created_at""",
                    (status, project_id),
                )
            else:
                await cur.execute(
                    "SELECT * FROM manual_review_queue WHERE status = %s ORDER BY created_at",
                    (status,),
                )
            rows = await cur.fetchall()
            if rows and cur.description:
                cols = [d.name for d in cur.description]
                return [dict(zip(cols, row)) for row in rows]
        return []

    async def resolve_review(
        self,
        doc_id: str,
        final_decision: str,
        reviewer: str = "system",
    ) -> bool:
        """审核员处理审核队列条目，确定最终决策。"""
        if self._use_memory:
            for item in self._review_queue:
                if item["doc_id"] == doc_id and item["status"] == "PENDING":
                    item["status"] = "RESOLVED"
                    item["final_decision"] = final_decision
                    item["reviewer"] = reviewer
                    item["reviewed_at"] = datetime.now(timezone.utc).isoformat()

                    # 更新文档主记录
                    doc = self._memory.get(doc_id)
                    if doc:
                        doc["decision"] = final_decision
                        if final_decision == "DISCARD":
                            doc["status"] = "DISCARDED"
                        elif final_decision == "ARCHIVE":
                            doc["status"] = "ARCHIVED"
                        else:
                            doc["status"] = "ACTIVE"
                    log.info(
                        "review_resolved",
                        doc_id=doc_id,
                        decision=final_decision,
                        reviewer=reviewer,
                    )
                    return True
            return False

        assert self._conn is not None
        async with self._conn.cursor() as cur:
            await cur.execute(
                """
                UPDATE manual_review_queue
                SET status = 'RESOLVED', final_decision = %s,
                    reviewer = %s, reviewed_at = NOW()
                WHERE doc_id = %s AND status = 'PENDING'
                """,
                (final_decision, reviewer, doc_id),
            )
            if cur.rowcount == 0:
                return False
            # 同步更新文档主记录
            new_status = "ACTIVE"
            if final_decision == "DISCARD":
                new_status = "DISCARDED"
            elif final_decision == "ARCHIVE":
                new_status = "ARCHIVED"
            await cur.execute(
                "UPDATE documents SET decision = %s, status = %s WHERE id = %s",
                (final_decision, new_status, doc_id),
            )
            await self._conn.commit()
        log.info(
            "review_resolved",
            doc_id=doc_id,
            decision=final_decision,
            reviewer=reviewer,
        )
        return True

    # ── 审计日志 ──────────────────────────────────────────

    async def insert_audit_log(self, entry: "AuditEntry") -> None:
        """写入审计日志。"""
        record = entry.model_dump(mode="json")
        if self._use_memory:
            self._audit_buffer.append(record)
            return

        assert self._conn is not None
        async with self._conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO audit_log
                    (timestamp, action, user_id, org_id, resource_type,
                     resource_id, details, duration_ms)
                VALUES (%(timestamp)s, %(action)s, %(user_id)s, %(org_id)s,
                        %(resource_type)s, %(resource_id)s,
                        %(details)s::jsonb, %(duration_ms)s)
                """,
                record,
            )
            await self._conn.commit()

    async def list_audit_logs(
        self,
        org_id: Optional[str] = None,
        action: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict]:
        """查询审计日志。"""
        if self._use_memory:
            results = list(self._audit_buffer)
            if org_id:
                results = [r for r in results if r.get("org_id") == org_id]
            if action:
                results = [r for r in results if r.get("action") == action]
            return results[-limit:]

        assert self._conn is not None
        async with self._conn.cursor() as cur:
            clauses = []
            params: list = []
            if org_id:
                clauses.append("org_id = %s")
                params.append(org_id)
            if action:
                clauses.append("action = %s")
                params.append(action)
            where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
            params.append(limit)
            await cur.execute(
                f"SELECT * FROM audit_log{where} ORDER BY timestamp DESC LIMIT %s",
                params,
            )
            rows = await cur.fetchall()
            if rows and cur.description:
                cols = [d.name for d in cur.description]
                return [dict(zip(cols, row)) for row in rows]
        return []

    async def clear_all(self) -> None:
        """清除所有文档和审核队列数据（仅用于测试/重灌）。"""
        if self._use_memory:
            self._memory.clear()
            self._review_queue.clear()
            self._audit_buffer.clear()
            log.info("metadata_store_cleared_memory")
            return

        assert self._conn is not None
        async with self._conn.cursor() as cur:
            await cur.execute("DELETE FROM manual_review_queue")
            await cur.execute("DELETE FROM documents")
            await self._conn.commit()
        log.info("metadata_store_cleared_pg")

    # ── V14: 分析暂存 API ──────────────────────────────

    def stage_batch(self, batch_id: str, data: dict) -> None:
        """暂存分析结果，等待用户确认后再入库。"""
        self._staging[batch_id] = data

    def get_staged_batch(self, batch_id: str) -> dict | None:
        """获取暂存的分析结果。"""
        return self._staging.get(batch_id)

    def clear_staged_batch(self, batch_id: str) -> None:
        """清理已处理的暂存数据。"""
        self._staging.pop(batch_id, None)

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()
