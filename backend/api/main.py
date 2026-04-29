"""
KAP（Knowledge Agent Platform · 知识智能体平台）API 主入口模块。

本模块负责：
- 创建并配置 FastAPI 应用实例
- 注册所有子路由（问答、知识管理、审计、健康检查等）
- 配置 CORS 跨域中间件和认证中间件
- 应用生命周期管理（启动时初始化存储、关闭时释放连接）
- 生产模式下托管前端 SPA 静态文件

基于 Wiki-map V15 演进；当前版本 v1.0.0-m0（M0 KAP-Lite 阶段）。
"""

import asyncio
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path

# Windows: psycopg 需要 SelectorEventLoop
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse

from api.deps import init_stores, shutdown_stores
from api.middleware.auth import AuthMiddleware
from api.routers import analysis, audit, governance, health, knowledge, platform, projects, qa, recall_test, sensitive, settings, system, v15, wiki
from packages.common.config import settings as app_settings

log = structlog.get_logger(__name__)

_STARTED_AT: float = 0.0  # 应用启动时间戳，供健康检查接口读取


def _check_dependencies() -> None:
    """启动时检测外部依赖连通性（OPT-10）。

    逐一检查 PostgreSQL、Milvus、Redis 等外部组件是否可达。
    PostgreSQL 为关键依赖，不可用时记录 error 级别日志；其余为可选依赖，记录 warning。
    """
    results = app_settings.validate_dependencies()
    critical = {"postgresql"}  # 关键依赖集合，不可用时应告警
    for name, info in results.items():
        if info["status"] == "ok":
            log.info("dependency_ok", component=name, addr=info["addr"])
        elif name in critical:
            log.error("dependency_critical_unavailable", component=name, error=info.get("error"))
        else:
            log.warning("dependency_unavailable", component=name, error=info.get("error"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理器。

    启动阶段依次执行：检查外部依赖 -> 初始化存储层 -> 记录启动时间。
    关闭阶段由 yield 后的代码处理（当前无需清理操作）。
    """
    global _STARTED_AT
    _check_dependencies()
    await init_stores()
    _STARTED_AT = time.time()
    log.info("app_started", version="v1.0.0-m0")
    yield
    # 关闭阶段：释放数据库连接
    await shutdown_stores()
    log.info("app_shutdown")


app = FastAPI(
    title="KAP API",
    description="KAP 知识智能体平台（全行业知识治理 · 制造能源优先 · 私有化部署）",
    version="v1.0.0-m0",
    lifespan=lifespan,
)

# ── 中间件注册（后添加的先执行 → Auth 先 add，CORS 后 add → CORS 先跑） ──
_CORS_ORIGINS = [
    origin.strip()
    for origin in (app_settings.cors_origins or "http://localhost:3000,http://localhost:5173").split(",")
    if origin.strip()
]
app.add_middleware(AuthMiddleware)  # 先 add → 后执行（Auth 在 CORS 之后）
app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)  # 后 add → 先执行（CORS preflight 先处理，再到 Auth）

# ── 路由注册 ─────────────────────────────────────────────
app.include_router(health.router)                          # 健康检查（无前缀）
app.include_router(qa.router, prefix="/api/v1")            # 智能问答
app.include_router(knowledge.router, prefix="/api/v1")     # 知识管理（文档导入/目录）
app.include_router(recall_test.router, prefix="/api/v1")   # 召回测试
app.include_router(audit.router, prefix="/api/v1")         # 审计日志
app.include_router(analysis.router, prefix="/api/v1")      # 分析功能
app.include_router(projects.router, prefix="/api/v1")      # 项目管理
app.include_router(wiki.router, prefix="/api/v1")          # V11: Wiki 知识编译
app.include_router(system.router, prefix="/api/v1")        # V15: 组件状态
app.include_router(governance.router, prefix="/api/v1")    # V15: 治理工单
app.include_router(sensitive.router, prefix="/api/v1")    # M2: 敏感映射解码
app.include_router(v15.router, prefix="/api/v1")           # V15: 专属路由 (Phase L 起)
app.include_router(platform.router)                        # 平台级接口
app.include_router(settings.router)                        # 系统设置

# ── 生产模式：服务前端静态文件 ──────────────────────────
_FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"

if _FRONTEND_DIST.is_dir():
    # 挂载前端构建产物中的 assets 目录（JS/CSS/图片等）
    app.mount("/assets", StaticFiles(directory=_FRONTEND_DIST / "assets"), name="static-assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        """SPA fallback: 非 API 路径返回 index.html。"""
        # API 路径不回退到 SPA
        if full_path.startswith("api/") or full_path == "api":
            return JSONResponse(status_code=404, content={"detail": f"API endpoint /{full_path} not found"})
        # 路径遍历防护：resolve 后必须仍在 dist 目录内
        file_path = (_FRONTEND_DIST / full_path).resolve()
        if file_path.is_file() and file_path.is_relative_to(_FRONTEND_DIST.resolve()):
            return FileResponse(file_path)
        return FileResponse(_FRONTEND_DIST / "index.html")
