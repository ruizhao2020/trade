from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.security import current_user
from app.db import get_session
from app.models.auth import Module, Role, User
from app.schemas.auth import ChangePasswordRequest, LoginRequest, RegisterRequest, TokenResponse, UserResponse, ModuleResponse
from app.services.auth_service import authenticate, create_access_token, hash_password, permission_codes, verify_password

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def user_response(user: User, modules: list[Module] | None = None) -> UserResponse:
    codes = permission_codes(user)
    allowed_modules = modules or []
    return UserResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        display_name=user.display_name,
        enabled=user.enabled,
        role_codes=[role.code for role in user.roles if role.enabled],
        permission_codes=sorted(codes),
        modules=[
            ModuleResponse(
                id=module.id, code=module.code, name=module.name, icon=module.icon,
                component_key=module.component_key, route_path=module.route_path,
                api_prefixes=module.api_prefixes,
                api_permission=module.api_permission,
                sort_order=module.sort_order, enabled=module.enabled, visible=module.visible,
            )
            for module in allowed_modules
            if module.enabled and module.visible and f"{module.code}.view" in codes
        ],
    )


async def response_with_modules(session: AsyncSession, user: User) -> UserResponse:
    modules = (await session.execute(select(Module).order_by(Module.sort_order, Module.id))).scalars().all()
    return user_response(user, list(modules))


@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(body: RegisterRequest, session: AsyncSession = Depends(get_session)):
    duplicate = (await session.execute(
        select(User).where(or_(User.username == body.username, User.email == body.email if body.email else False))
    )).scalar_one_or_none()
    if duplicate:
        raise HTTPException(status_code=409, detail="用户名或邮箱已存在")
    member = (await session.execute(select(Role).where(Role.code == "member", Role.enabled.is_(True)))).scalar_one()
    user = User(
        username=body.username,
        email=body.email,
        display_name=body.display_name or body.username,
        password_hash=hash_password(body.password),
        enabled=True,
    )
    user.roles = [member]
    session.add(user)
    await session.commit()
    await session.refresh(user)
    token, expires_at = create_access_token(user.id)
    return TokenResponse(access_token=token, expires_at=expires_at, user=await response_with_modules(session, user))


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, session: AsyncSession = Depends(get_session)):
    user = await authenticate(session, body.username, body.password)
    if not user:
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    token, expires_at = create_access_token(user.id)
    return TokenResponse(access_token=token, expires_at=expires_at, user=await response_with_modules(session, user))


@router.get("/me", response_model=UserResponse)
async def me(user: User = Depends(current_user), session: AsyncSession = Depends(get_session)):
    return await response_with_modules(session, user)


@router.put("/password", status_code=204)
async def change_password(
    body: ChangePasswordRequest,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
):
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="当前密码不正确")
    if body.current_password == body.new_password:
        raise HTTPException(status_code=400, detail="新密码不能与当前密码相同")
    user.password_hash = hash_password(body.new_password)
    await session.commit()
