"""审计日志单元测试。"""

import pytest
from packages.common.audit import AuditAction, AuditEntry, AuditLogger


class TestAuditAction:
    """AuditAction 枚举测试。"""

    def test_all_actions_defined(self):
        actions = [a.value for a in AuditAction]
        assert "document_ingested" in actions
        assert "qa_query" in actions
        assert "permission_denied" in actions
        assert len(actions) == 8


@pytest.mark.asyncio
class TestAuditLogger:
    """AuditLogger 内存模式测试。"""

    async def test_log_and_list(self):
        logger = AuditLogger()
        entry = AuditEntry(
            action=AuditAction.DOCUMENT_INGESTED,
            user_id="user_001",
            org_id="org_a",
            resource_type="document",
            resource_id="doc_001",
        )
        await logger.log(entry)

        logs = await logger.list_logs()
        assert len(logs) == 1
        assert logs[0]["action"] == "document_ingested"
        assert logs[0]["user_id"] == "user_001"

    async def test_filter_by_action(self):
        logger = AuditLogger()

        await logger.log(AuditEntry(
            action=AuditAction.QA_QUERY, user_id="u1", org_id="org_a",
        ))
        await logger.log(AuditEntry(
            action=AuditAction.DOCUMENT_INGESTED, user_id="u2", org_id="org_a",
        ))
        await logger.log(AuditEntry(
            action=AuditAction.QA_QUERY, user_id="u3", org_id="org_a",
        ))

        qa_logs = await logger.list_logs(action="qa_query")
        assert len(qa_logs) == 2
        assert all(l["action"] == "qa_query" for l in qa_logs)

    async def test_filter_by_org_id(self):
        logger = AuditLogger()

        await logger.log(AuditEntry(
            action=AuditAction.SEARCH_QUERY, user_id="u1", org_id="org_a",
        ))
        await logger.log(AuditEntry(
            action=AuditAction.SEARCH_QUERY, user_id="u2", org_id="org_b",
        ))
        await logger.log(AuditEntry(
            action=AuditAction.QA_QUERY, user_id="u3", org_id="org_a",
        ))

        org_a_logs = await logger.list_logs(org_id="org_a")
        assert len(org_a_logs) == 2
        assert all(l["org_id"] == "org_a" for l in org_a_logs)

    async def test_limit(self):
        logger = AuditLogger()

        for i in range(10):
            await logger.log(AuditEntry(
                action=AuditAction.QA_QUERY,
                user_id=f"u{i}",
                org_id="org_a",
            ))

        limited = await logger.list_logs(limit=3)
        assert len(limited) == 3
