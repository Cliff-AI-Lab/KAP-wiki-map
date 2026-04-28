"""连接器基类，所有数据源连接器继承此类。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncIterator

from packages.common.types import RawDocument, SourceSystem


class ConnectorBase(ABC):
    """数据源连接器的抽象基类。"""

    source_system: SourceSystem

    @abstractmethod
    async def connect(self) -> None:
        """建立与数据源的连接/授权。"""

    @abstractmethod
    async def fetch_documents(self, incremental: bool = True) -> AsyncIterator[RawDocument]:
        """
        拉取文档。
        incremental=True 时仅拉取自上次同步后的增量。
        """

    @abstractmethod
    async def health_check(self) -> bool:
        """检查连接器是否正常。"""

    async def disconnect(self) -> None:
        """断开连接（可选实现）。"""
