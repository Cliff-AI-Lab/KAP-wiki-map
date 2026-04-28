"""钉钉连接器 — 支持真实 API 模式和模拟数据模式。"""

from __future__ import annotations

from typing import AsyncIterator

import httpx

from packages.common import get_logger, settings
from packages.common.exceptions import ConnectorError
from packages.common.types import RawDocument, SourceSystem
from packages.connectors.base import ConnectorBase
from packages.connectors.dingtalk.mock_data import MOCK_DOCUMENTS

log = get_logger("connector.dingtalk")


class DingTalkConnector(ConnectorBase):
    source_system = SourceSystem.DINGTALK

    def __init__(self) -> None:
        self._mock_mode = settings.dingtalk_mock_mode
        self._access_token: str | None = None
        self._client: httpx.AsyncClient | None = None

    # ── 连接 / 授权 ─────────────────────────────────

    async def connect(self) -> None:
        if self._mock_mode:
            log.info("dingtalk_connector_mock_mode", doc_count=len(MOCK_DOCUMENTS))
            return

        self._client = httpx.AsyncClient(
            base_url="https://oapi.dingtalk.com",
            timeout=30.0,
        )
        await self._obtain_access_token()
        log.info("dingtalk_connector_connected")

    async def _obtain_access_token(self) -> None:
        """通过 appkey/appsecret 获取 access_token。"""
        assert self._client is not None
        resp = await self._client.get(
            "/gettoken",
            params={
                "appkey": settings.dingtalk_app_key,
                "appsecret": settings.dingtalk_app_secret,
            },
        )
        data = resp.json()
        if data.get("errcode") != 0:
            raise ConnectorError(f"钉钉授权失败: {data.get('errmsg')}")
        self._access_token = data["access_token"]

    # ── 拉取文档 ─────────────────────────────────────

    async def fetch_documents(self, incremental: bool = True) -> AsyncIterator[RawDocument]:
        if self._mock_mode:
            async for doc in self._fetch_mock():
                yield doc
        else:
            async for doc in self._fetch_real(incremental):
                yield doc

    async def _fetch_mock(self) -> AsyncIterator[RawDocument]:
        """从模拟数据生成 RawDocument 流。"""
        for item in MOCK_DOCUMENTS:
            doc = RawDocument(
                doc_id=item["doc_id"],
                title=item["title"],
                content=item["content"],
                source_system=SourceSystem.DINGTALK,
                source_id=item.get("source_id", ""),
                created_at=item.get("created_at"),
                updated_at=item.get("updated_at"),
                created_by=item.get("created_by", ""),
                last_modifier=item.get("last_modifier", ""),
                file_size=len(item["content"].encode("utf-8")),
            )
            log.info("dingtalk_mock_doc", doc_id=doc.doc_id, title=doc.title)
            yield doc

    async def _fetch_real(self, incremental: bool) -> AsyncIterator[RawDocument]:
        """通过钉钉开放 API 拉取文档（待完整实现）。"""
        assert self._client is not None and self._access_token is not None
        headers = {"x-acs-dingtalk-access-token": self._access_token}

        # 获取钉钉文档空间列表
        resp = await self._client.get(
            "/v1.0/doc/spaces",
            headers=headers,
        )
        data = resp.json()
        for space in data.get("spaces", []):
            space_id = space.get("spaceId", "")
            # 获取空间下的文档列表
            docs_resp = await self._client.get(
                f"/v1.0/doc/spaces/{space_id}/docs",
                headers=headers,
            )
            docs_data = docs_resp.json()
            for doc_item in docs_data.get("docs", []):
                yield RawDocument(
                    doc_id=f"dingtalk_{doc_item.get('docId', '')}",
                    title=doc_item.get("title", "无标题"),
                    content=doc_item.get("content", ""),
                    source_system=SourceSystem.DINGTALK,
                    source_id=doc_item.get("docId", ""),
                    file_size=len(doc_item.get("content", "").encode("utf-8")),
                )

    # ── 健康检查 ─────────────────────────────────────

    async def health_check(self) -> bool:
        if self._mock_mode:
            return True
        try:
            assert self._client is not None
            resp = await self._client.get(
                "/gettoken",
                params={
                    "appkey": settings.dingtalk_app_key,
                    "appsecret": settings.dingtalk_app_secret,
                },
            )
            return resp.status_code == 200
        except Exception:
            return False

    async def disconnect(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
