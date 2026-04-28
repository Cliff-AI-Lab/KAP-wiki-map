"""结构化日志模块 — 基于 structlog 提供全局统一的日志基础设施。

本模块在导入时即完成 structlog 的全局配置，所有业务模块通过
`get_logger(name)` 获取带命名空间的日志实例。

日志处理链路：
1. merge_contextvars — 合并上下文变量（如 request_id），实现跨函数的日志关联
2. add_log_level — 自动添加日志级别标签（info / warning / error 等）
3. TimeStamper — 添加 ISO 8601 格式时间戳
4. ConsoleRenderer — 开发环境下以彩色可读格式输出到控制台

使用示例：
    from packages.common import get_logger
    log = get_logger("my_module")
    log.info("event_name", key1="value1", key2=42)
"""

import structlog

# 全局 structlog 配置，模块导入时执行一次
structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,   # 合并线程/协程上下文变量
        structlog.processors.add_log_level,         # 添加日志级别字段
        structlog.processors.TimeStamper(fmt="iso"),# 添加 ISO 格式时间戳
        structlog.dev.ConsoleRenderer(),            # 开发模式彩色控制台输出
    ],
    wrapper_class=structlog.make_filtering_bound_logger(0),  # 最低级别 0 = 全部放行
    context_class=dict,                    # 使用普通字典存储上下文
    logger_factory=structlog.PrintLoggerFactory(),  # 底层使用 print 输出
    cache_logger_on_first_use=True,        # 首次使用后缓存 logger 实例，提升性能
)


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """获取指定命名空间的结构化日志实例。

    Args:
        name: 日志命名空间，通常为模块名（如 "retrieval.router"），
            会作为日志输出中的 logger 字段，便于过滤和定位

    Returns:
        绑定了命名空间的 structlog BoundLogger 实例
    """
    return structlog.get_logger(name)
