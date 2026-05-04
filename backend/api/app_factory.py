"""KAP 三块松耦合 App 工厂（M21 #1）。

把 KAP 拆成 3 个独立可部署的 FastAPI 应用，每块都能单独使用：

- ``architect``  块① 知识咨询智能体（对话式建知识体系）
- ``storage``    块② 知识管理 + 存储中心（治理 / 本体 / Wiki / 图谱）
- ``portal``     块③ 渐进式消费门户（Wiki / RAG / 图谱三路召回）

设计原则：
- 三块共享 ``packages/auth`` + ``packages/common`` + ``packages/storage`` 库代码
  （lib 级共享，不破坏松耦合 — 跟 docker 层共享 base image 等价）
- 三块各自独立的 router 集 + lifespan 钩子（按需启用 PG 持久化）
- 服务间通讯走 HTTP API（不直接 import 对方 router 内部）
- 单体部署：``main.py`` 用 blocks=["all"] 装载全部
- 拆分部署：3 个 ``main_<block>.py`` 各自只装一块

每块端口约定（dev/prod）：
- architect → :8011
- storage   → :8012
- portal    → :8013
- 单体     → :8001（兼容）
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Iterable, Literal

# Windows: psycopg 需要 SelectorEventLoop（提早设置）
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from api.deps import init_stores, shutdown_stores
from api.middleware.auth import AuthMiddleware
from api.routers import (
    analysis, architect, audit, governance, health, iss_job, knowledge,
    observability, ontology, platform, projects, qa, rebuild, recall_test,
    sensitive, settings as settings_router, system, v15, wiki,
)
from packages.common.config import settings as app_settings

log = structlog.get_logger(__name__)


Block = Literal["architect", "storage", "portal", "all"]


# 各块路由映射
_BLOCK_ROUTERS = {
    "architect": [
        # 块① 知识咨询智能体：对话式建本体
        ("architect", architect.router, "/api/v1"),
    ],
    "storage": [
        # 块② 治理 + 存储中心：6 工位 + 4×6 矩阵 + 双层本体 + Wiki 编译
        ("projects",   projects.router,   "/api/v1"),
        ("knowledge",  knowledge.router,  "/api/v1"),
        ("wiki",       wiki.router,       "/api/v1"),
        ("governance", governance.router, "/api/v1"),
        ("ontology",   ontology.router,   "/api/v1"),
        ("rebuild",    rebuild.router,    "/api/v1"),    # 全量重抽影子库
        ("sensitive",  sensitive.router,  "/api/v1"),    # 敏感映射
        ("audit",      audit.router,      "/api/v1"),    # 审计日志
        ("analysis",   analysis.router,   "/api/v1"),    # 数据分析
    ],
    "portal": [
        # 块③ 消费门户：Wiki/RAG/图谱三路召回 + 运营观察
        ("qa",            qa.router,           "/api/v1"),    # 三路召回入口
        ("recall_test",   recall_test.router,  "/api/v1"),    # 召回测试
        ("observability", observability.router, "/api/v1"),    # 运营观察
        ("iss_job",       iss_job.router,       "/api/v1"),    # ISS-Job 协调
    ],
}


# 各块 PG 持久化开关（仅相关 block 启用）
_BLOCK_PG_INITS = {
    "architect": [],   # block ① 暂无独立 PG 持久化
    "storage": [
        ("KAP_DECISION_LOG_PG", "initialize_pg_decision_log", "shutdown_pg_decision_log"),
        ("KAP_PROMPT_VER_PG",   "initialize_pg_prompt_versions", "shutdown_pg_prompt_versions"),
        ("KAP_WIKI_QUALITY_PG", "initialize_pg_wiki_quality", "shutdown_pg_wiki_quality"),
        ("KAP_EXTRACTION_QUALITY_PG", "initialize_pg_extraction_quality", "shutdown_pg_extraction_quality"),
    ],
    "portal": [
        ("KAP_QUERY_LOG_PG",   "initialize_pg_query_log", "shutdown_pg_query_log"),
        ("KAP_RECALL_EVAL_PG", "initialize_pg_recall_eval", "shutdown_pg_recall_eval"),
    ],
}


_STARTED_AT: float = 0.0


def _check_dependencies() -> None:
    results = app_settings.validate_dependencies()
    critical = {"postgresql"}
    for name, info in results.items():
        if info["status"] == "ok":
            log.info("dependency_ok", component=name, addr=info["addr"])
        elif name in critical:
            log.error("dependency_critical_unavailable", component=name,
                      error=info.get("error"))
        else:
            log.warning("dependency_unavailable", component=name,
                        error=info.get("error"))


def _build_lifespan(blocks: list[str]):
    """按 blocks 生成 lifespan：只 init 该块需要的 PG sink。"""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        global _STARTED_AT
        _check_dependencies()
        await init_stores()

        # 收集需要启用的 PG init/shutdown
        actives: list[tuple[str, str]] = []  # (init_fn_name, shutdown_fn_name)
        for blk in blocks:
            for env_key, init_name, shutdown_name in _BLOCK_PG_INITS.get(blk, []):
                if os.environ.get(env_key) == "1":
                    actives.append((init_name, shutdown_name))

        from packages import observability as obs_pkg
        for init_name, _ in actives:
            init_fn = getattr(obs_pkg, init_name)
            await init_fn(app_settings.postgres_dsn)

        _STARTED_AT = time.time()
        log.info("app_started",
                 blocks=blocks, version="v1.0.0-m0",
                 pg_inits=[n for n, _ in actives])
        yield

        for _, shutdown_name in actives:
            shutdown_fn = getattr(obs_pkg, shutdown_name)
            await shutdown_fn()
        await shutdown_stores()
        log.info("app_shutdown", blocks=blocks)

    return lifespan


def create_app(
    *,
    blocks: Iterable[Block] = ("all",),
    title: str | None = None,
    serve_spa: bool = True,
) -> FastAPI:
    """工厂：按 blocks 装载子集，每块可单独启动。

    Args:
        blocks: 装载哪些块。``["all"]`` 等同于全部三块。
        title: 自定义 OpenAPI 标题（拆分部署时区分日志）。
        serve_spa: 生产模式 ``frontend/dist`` 存在时挂载前端 SPA。
    """
    blk_list = list(blocks)
    if "all" in blk_list:
        blk_list = ["architect", "storage", "portal"]

    app = FastAPI(
        title=title or f"KAP API ({'+'.join(blk_list)})",
        description="KAP 知识智能体平台 · 三块松耦合可拆分部署（M21 #1）",
        version="v1.0.0-m0",
        lifespan=_build_lifespan(blk_list),
    )

    # 中间件
    cors_origins = [
        o.strip()
        for o in (
            app_settings.cors_origins
            or "http://localhost:3000,http://localhost:5173"
        ).split(",")
        if o.strip()
    ]
    app.add_middleware(AuthMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 健康检查 + 系统配置（所有块都装；运维必需）
    app.include_router(health.router)
    app.include_router(system.router, prefix="/api/v1")
    app.include_router(platform.router)
    app.include_router(settings_router.router)

    # block 路由按需装载
    loaded_routes: list[str] = []
    for blk in blk_list:
        for name, router, prefix in _BLOCK_ROUTERS.get(blk, []):
            app.include_router(router, prefix=prefix)
            loaded_routes.append(f"{blk}.{name}")

    # block ② / 全装时挂 v15 专属路由（兼容老前端）
    if "storage" in blk_list or "all" in blk_list:
        app.include_router(v15.router, prefix="/api/v1")

    # 生产 SPA fallback（拆分部署时只 storage block 主面板需要）
    frontend_dist = Path(__file__).resolve().parent.parent / "frontend" / "dist"
    if serve_spa and frontend_dist.is_dir():
        app.mount("/assets", StaticFiles(directory=frontend_dist / "assets"),
                  name="static-assets")

        @app.get("/{full_path:path}")
        async def serve_spa(full_path: str):
            if full_path.startswith("api/") or full_path == "api":
                return JSONResponse(
                    status_code=404,
                    content={"detail": f"API endpoint /{full_path} not found"},
                )
            file_path = (frontend_dist / full_path).resolve()
            if file_path.is_file() and file_path.is_relative_to(
                frontend_dist.resolve()
            ):
                return FileResponse(file_path)
            return FileResponse(frontend_dist / "index.html")

    log.info("app_factory_built",
             blocks=blk_list, routes=loaded_routes,
             cors=cors_origins)
    return app
