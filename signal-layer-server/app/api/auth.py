from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.security import current_user
from app.db import get_session
from app.models.auth import USER_STATUS_ACTIVE, USER_STATUS_PENDING, Module, Role, User
from app.schemas.auth import (
    ChangePasswordRequest, LoginRequest, RegisterRequest, RegisterResponse, TokenResponse, UserResponse, ModuleResponse,
)
from app.services.auth_service import (
    authenticate, create_access_token, hash_password, permission_codes, verify_password,
)

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
        # 未落库的对象 status 还是 None（列默认值只在 flush 时生效），按列默认视为已通过。
        status=user.status or USER_STATUS_ACTIVE,
        created_at=user.created_at,
        role_codes=[role.code for role in user.roles if role.enabled],
        permission_codes=sorted(codes),
        modules=[
            ModuleResponse(
                id=module.id, code=module.code, name=module.name, icon=module.icon,
                component_key=module.component_key, route_path=module.route_path,
                api_prefixes=module.api_prefixes,
                api_permission=module.api_permission,
                sort_order=module.sort_order, enabled=module.enabled, visible=module.visible,
                public_access=bool(getattr(module, "public_access", False)),
            )
            for module in allowed_modules
            if module.enabled
            and module.visible
            and f"{module.code}.view" in codes
            # 与模块准入中间件保持一致：非公开模块还要求 private.access。
            # 否则左导航会列出用户实际打不开的入口（点进去每个接口都是 403）。
            and (bool(getattr(module, "public_access", False)) or "private.access" in codes)
        ],
    )


async def response_with_modules(session: AsyncSession, user: User) -> UserResponse:
    modules = (await session.execute(select(Module).order_by(Module.sort_order, Module.id))).scalars().all()
    return user_response(user, list(modules))


@router.post("/register", response_model=RegisterResponse, status_code=201)
async def register(body: RegisterRequest, session: AsyncSession = Depends(get_session)):
    duplicate = (await session.execute(
        select(User).where(or_(User.username == body.username, User.email == body.email if body.email else False))
    )).scalar_one_or_none()
    if duplicate:
        raise HTTPException(status_code=409, detail="用户名或邮箱已存在")
    registration_role = (await session.execute(
        select(Role).where(Role.registration_default.is_(True), Role.enabled.is_(True)).order_by(Role.id)
    )).scalars().first()
    if registration_role is None:
        registration_role = (await session.execute(select(Role).where(Role.code == "member", Role.enabled.is_(True)))).scalar_one()
    user = User(
        username=body.username,
        email=body.email,
        display_name=body.display_name or body.username,
        password_hash=hash_password(body.password),
        enabled=True,
        status=USER_STATUS_PENDING,
    )
    user.roles = [registration_role]
    session.add(user)
    await session.commit()
    await session.refresh(user)
    # 不签发令牌：审核通过前该账号无法登录，也无法换取任何私有模块的访问权。
    return RegisterResponse(
        status=USER_STATUS_PENDING,
        message="注册已提交，请等待管理员审核通过后登录",
        username=user.username,
        display_name=user.display_name,
    )


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, session: AsyncSession = Depends(get_session)):
    user, reason = await authenticate(session, body.username, body.password)
    if not user:
        raise HTTPException(status_code=401, detail=reason or "用户名或密码错误")
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
