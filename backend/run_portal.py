"""消费中心 dev 启动（M21 #1 · :8013）。"""
import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "api.main_portal:app",
        host="127.0.0.1",
        port=8013,
        reload=False,
        loop="asyncio",
        log_level="info",
    )
