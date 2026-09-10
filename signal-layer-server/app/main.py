"""
============================================================================
SignalLayer 应用入口
============================================================================

## 功能
FastAPI 应用的主入口文件。负责：
1. 创建 FastAPI 应用实例
2. 配置 CORS 中间件（允许前端跨域请求）
3. 注册所有 API 路由（通过 api_router）
4. 管理应用生命周期（启动时初始化服务，关闭时清理资源）
5. 提供健康检查端点 /health

## 启动方式
    uvicorn app.main:app --host 0.0.0.0 --port 8000

## 依赖关系
- app.config: 读取环境变量配置（数据库连接、Redis 地址等）
- app.api.router: 注册所有 API 子路由（klines/chan/indicator/signal/template/ws）
- app.api.deps: 服务初始化与依赖注入（Redis 连接、缓存、计算服务）
"""

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.router import api_router
from app.api.deps import init_services, shutdown_services
from app.config import settings
from app.middleware.module_access import ModuleAccessMiddleware

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    应用生命周期管理。
    启动阶段：初始化 Redis 连接、创建 ChanService/IndicatorService 等服务实例。
    关闭阶段：关闭 Redis 连接，清理资源。

    注意：如果 Redis 不可用，init_services 会降级为 no-op 模式（不使用缓存）。
    """
    logger.info("Starting SignalLayer services...")
    if not settings.debug and settings.token_secret == "change-this-secret-before-production":
        raise RuntimeError("生产环境必须配置 SIGNAL_TOKEN_SECRET")
    await init_services()
    logger.info("All services initialized successfully")
    _print_routes(app)
    yield
    logger.info("Shutting down SignalLayer services...")
    await shutdown_services()
    logger.info("Services shut down complete")


# 创建 FastAPI 应用实例
# docs_url="/docs": 启用 Swagger UI（开发环境通过 http://localhost:8000/docs 访问）
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# CORS 来源通过 SIGNAL_CORS_ORIGINS 配置，生产环境使用实际前端域名。
app.add_middleware(ModuleAccessMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册所有 API 子路由
# 路由前缀定义在各子模块中（如 /api/v1/klines、/api/v1/chan 等）
app.include_router(api_router)


@app.get("/health")
async def health_check():
    """健康检查端点。负载均衡器/监控系统用于检测服务是否存活"""
    logger.debug("Health check requested")
    return {"status": "ok", "version": settings.app_version}


def _print_routes(app: FastAPI):
    """启动时打印所有已注册的 API 端点列表，方便开发者确认路由正确性"""
    output = ["", "=" * 60, "  SignalLayer API Endpoints", "=" * 60]
    for route in app.routes:
        if hasattr(route, "methods") and hasattr(route, "path"):
            methods = ",".join(route.methods)
            output.append(f"  {methods:<8} {route.path}")
    output.append("=" * 60 + "\n")
    for line in output:
        print(line)
