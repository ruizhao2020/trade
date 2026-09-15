from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from sqlalchemy import select

from app.db import get_session
from app.models.auth import User
from app.services.auth_service import decode_access_token, permission_codes
from app.services.module_access_service import module_rules


class ModuleAccessMiddleware(BaseHTTPMiddleware):
    """依据 modules.api_prefixes 配置执行模块级准入，无需在路由中硬编码模块。"""

    async def dispatch(self, request: Request, call_next):
        public_path = request.url.path in {"/health", "/openapi.json", "/docs", "/redoc"}
        if request.method == "OPTIONS" or public_path or request.url.path.startswith("/api/v1/auth/"):
            return await call_next(request)

        async for session in get_session():
            matched = next(
                (
                    rule for rule in await module_rules(session)
                    if request.url.path == rule[0].rstrip("/")
                    or request.url.path.startswith(rule[0].rstrip("/") + "/")
                ),
                None,
            )
            if not matched:
                return await call_next(request)

            _, required_permission, module_enabled, public_access = matched
            if not module_enabled:
                return JSONResponse({"detail": "模块已停用"}, status_code=403)
            if public_access:
                return await call_next(request)
            authorization = request.headers.get("Authorization", "")
            if not authorization.lower().startswith("bearer "):
                return JSONResponse({"detail": "请先登录"}, status_code=401)
            try:
                user_id = decode_access_token(authorization.split(" ", 1)[1])
            except ValueError as error:
                return JSONResponse({"detail": str(error)}, status_code=401)
            user = (await session.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
            if not user or not user.enabled:
                return JSONResponse({"detail": "用户不存在或已停用"}, status_code=401)
            if required_permission not in permission_codes(user):
                return JSONResponse({"detail": f"缺少模块权限：{required_permission}"}, status_code=403)
            request.state.current_user = user
            break
        return await call_next(request)
