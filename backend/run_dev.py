"""KAP 开发模式启动脚本.

关键: 在 import uvicorn **之前** 设置 SelectorEventLoopPolicy,
否则 uvicorn 默认使用 Proactor → psycopg async 失败 → fallback memory → 重启丢数据.

使用: python run_dev.py
"""
import asyncio
import os
import sys

# dev 默认允许 Milvus / 各存储失败时回退内存模式
# 本机 Docker Desktop 上 Milvus standalone 经常因 etcd lease 失效而崩溃,
# 没有这条 demo 一插向量就 500
os.environ.setdefault("KAP_ALLOW_MEMORY_FALLBACK", "true")

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "api.main:app",
        host="127.0.0.1",
        port=8001,
        reload=False,    # 关 reload, 数据持久化期间不要随便重启
        loop="asyncio",  # 显式 asyncio loop, 避免 uvicorn 自动选 Proactor
        log_level="info",
    )
