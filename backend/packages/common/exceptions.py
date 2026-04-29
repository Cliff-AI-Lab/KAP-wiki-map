"""自定义异常。"""


class BookwormError(Exception):
    """书虫智能体基础异常。"""


class ConnectorError(BookwormError):
    """连接器相关错误。"""


class DistillationError(BookwormError):
    """蒸馏管线错误。"""


class LLMCallError(DistillationError):
    """大模型调用失败。"""


class EmbeddingError(BookwormError):
    """Embedding 调用失败（M0-tech-debt 坑 6）。

    用法与 LLMCallError 平行：API 失败 / mock 被禁用 / 不支持的 provider 时抛出。
    """


class StorageError(BookwormError):
    """存储层错误。"""


class RetrievalError(BookwormError):
    """检索层错误。"""
