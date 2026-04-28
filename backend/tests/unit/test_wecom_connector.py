"""企微连接器单元测试。"""

import pytest
from packages.connectors.wecom import WeComConnector
from packages.common.types import SourceSystem


@pytest.mark.asyncio
class TestWeComConnector:
    """WeComConnector 测试（mock 模式）。"""

    async def test_mock_connect(self):
        connector = WeComConnector()
        await connector.connect()

    async def test_mock_fetch_documents_count(self):
        connector = WeComConnector()
        await connector.connect()
        documents = []
        async for doc in connector.fetch_documents():
            documents.append(doc)
        assert len(documents) == 6

    async def test_correct_source_system(self):
        connector = WeComConnector()
        await connector.connect()
        async for doc in connector.fetch_documents():
            assert doc.source_system == SourceSystem.WECOM
            break

    async def test_health_check_mock(self):
        connector = WeComConnector()
        await connector.connect()
        assert await connector.health_check() is True

    async def test_disconnect_mock(self):
        connector = WeComConnector()
        await connector.connect()
        await connector.disconnect()

    async def test_mock_documents_have_content(self):
        connector = WeComConnector()
        await connector.connect()
        async for doc in connector.fetch_documents():
            assert doc.doc_id.startswith("wecom_")
            assert len(doc.title) > 0
            assert len(doc.content) > 0
