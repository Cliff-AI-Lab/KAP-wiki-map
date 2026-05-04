"""咨询中心 dev 启动（M21 #1 · :8011）。

使用：
    python run_architect.py

可与知识中心 / 消费中心连用：
    KAP_STORAGE_BASE=http://localhost:8012 python run_architect.py
"""
import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "api.main_architect:app",
        host="127.0.0.1",
        port=8011,
        reload=False,
        loop="asyncio",
        log_level="info",
    )
