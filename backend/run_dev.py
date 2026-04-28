"""V15 开发模式启动脚本.

关键: 在 import uvicorn **之前** 设置 SelectorEventLoopPolicy,
否则 uvicorn 默认使用 Proactor → psycopg async 失败 → fallback memory → 重启丢数据.

使用: python run_dev.py
"""
import asyncio
import sys

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
