from __future__ import annotations

from collections.abc import Callable
from typing import Optional

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models.auth import User
from app.services.auth_service import decode_access_token, permission_codes

bearer = HTTPBearer(auto_error=False)


async def current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer),
    session: AsyncSession = Depends(get_session),
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="请先登录", headers={"WWW-Authenticate": "Bearer"})
    try:
        user_id = decode_access_token(credentials.credentials)
    except ValueError as error:
        raise HTTPException(status_code=401, detail=str(error), headers={"WWW-Authenticate": "Bearer"}) from error
    middleware_user = getattr(request.state, "current_user", None)
    if middleware_user is not None and middleware_user.id == user_id:
        return middleware_user
    user = (await session.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not user or not user.enabled:
        raise HTTPException(status_code=401, detail="用户不存在或已停用")
    return user


async def optional_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer),
    session: AsyncSession = Depends(get_session),
) -> User | None:
    """Resolve a bearer user when present; anonymous requests remain public."""
    if credentials is None or credentials.scheme.lower() != "bearer":
        return None
    try:
        user_id = decode_access_token(credentials.credentials)
    except ValueError:
        return None
    middleware_user = getattr(request.state, "current_user", None)
    if middleware_user is not None and middleware_user.id == user_id:
        return middleware_user
    user = (await session.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    return user if user and user.enabled else None


def require_permission(code: str) -> Callable:
    async def dependency(user: User = Depends(current_user)) -> User:
        if code not in permission_codes(user):
            raise HTTPException(status_code=403, detail=f"缺少权限：{code}")
        return user
    return dependency
