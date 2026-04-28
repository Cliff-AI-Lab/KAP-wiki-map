"""钉钉连接器单元测试。"""

import pytest
from packages.connectors.dingtalk import DingTalkConnector
from packages.common.types import SourceSystem


@pytest.mark.asyncio
class TestDingTalkConnector:
    """DingTalkConnector 测试（mock 模式）。"""

    async def test_mock_connect(self):
        connector = DingTalkConnector()
        await connector.connect()  # 不应抛出异常

    async def test_mock_fetch_documents_count(self):
        connector = DingTalkConnector()
        await connector.connect()
        documents = []
        async for doc in connector.fetch_documents():
            documents.append(doc)
        assert len(documents) == 8

    async def test_correct_source_system(self):
        connector = DingTalkConnector()
        await connector.connect()
        async for doc in connector.fetch_documents():
            assert doc.source_system == SourceSystem.DINGTALK
            break

    async def test_health_check_mock(self):
        connector = DingTalkConnector()
        await connector.connect()
        assert await connector.health_check() is True

    async def test_disconnect_mock(self):
        connector = DingTalkConnector()
        await connector.connect()
        await connector.disconnect()  # 不应抛出异常

    async def test_mock_documents_have_content(self):
        connector = DingTalkConnector()
        await connector.connect()
        async for doc in connector.fetch_documents():
            assert doc.doc_id.startswith("dingtalk_")
            assert len(doc.title) > 0
            assert len(doc.content) > 0
            assert doc.file_size > 0
