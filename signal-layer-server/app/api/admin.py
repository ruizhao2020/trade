from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.auth import user_response
from app.api.security import require_permission
from app.db import get_session
from app.models.auth import Module, Permission, Role, User, role_permissions
from app.schemas.auth import (
    ModuleCreate, ModuleResponse, ModuleUpdate, PermissionCreate, PermissionResponse,
    RoleCreate, RoleResponse, RoleUpdate, UserResponse, UserRoleUpdate,
)
from app.services.module_access_service import invalidate_module_rules

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


def role_response(role: Role) -> RoleResponse:
    return RoleResponse(
        id=role.id, code=role.code, name=role.name, description=role.description,
        built_in=role.built_in, enabled=role.enabled,
        registration_default=bool(getattr(role, "registration_default", False)),
        permission_codes=sorted(permission.code for permission in role.permissions),
    )


def module_response(module: Module) -> ModuleResponse:
    values = {column: getattr(module, column) for column in (
        "id", "code", "name", "icon", "component_key", "route_path", "api_prefixes", "api_permission", "sort_order", "enabled", "visible", "public_access",
    )}
    values["public_access"] = bool(values.get("public_access", False))
    return ModuleResponse(**values)


@router.get("/users", response_model=list[UserResponse], dependencies=[Depends(require_permission("admin.users"))])
async def list_users(session: AsyncSession = Depends(get_session)):
    return [user_response(user) for user in (await session.execute(select(User).order_by(User.id))).scalars()]


@router.put("/users/{user_id}/roles", response_model=UserResponse)
async def update_user_roles(
    user_id: int,
    body: UserRoleUpdate,
    session: AsyncSession = Depends(get_session),
    actor: User = Depends(require_permission("admin.users")),
):
    user = (await session.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    roles = (await session.execute(select(Role).where(Role.code.in_(body.role_codes)))).scalars().all()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    if len(roles) != len(set(body.role_codes)):
        raise HTTPException(status_code=400, detail="包含不存在的角色")
    if user.id == actor.id and ("admin" not in body.role_codes or body.enabled is False):
        raise HTTPException(status_code=400, detail="不能停用自己或移除自己的管理员角色")
    user.roles = list(roles)
    if body.enabled is not None:
        user.enabled = body.enabled
    await session.commit()
    return user_response(user)


@router.get("/roles", response_model=list[RoleResponse], dependencies=[Depends(require_permission("admin.roles"))])
async def list_roles(session: AsyncSession = Depends(get_session)):
    return [role_response(role) for role in (await session.execute(select(Role).order_by(Role.id))).scalars()]


@router.post("/roles", response_model=RoleResponse, status_code=201, dependencies=[Depends(require_permission("admin.roles"))])
async def create_role(body: RoleCreate, session: AsyncSession = Depends(get_session)):
    if (await session.execute(select(Role).where(Role.code == body.code))).scalar_one_or_none():
        raise HTTPException(status_code=409, detail="角色编码已存在")
    permissions = (await session.execute(select(Permission).where(Permission.code.in_(body.permission_codes)))).scalars().all()
    if body.registration_default:
        await session.execute(update(Role).values(registration_default=False))
    role = Role(code=body.code, name=body.name, description=body.description, enabled=body.enabled, registration_default=body.registration_default)
    role.permissions = list(permissions)
    session.add(role)
    await session.commit()
    await session.refresh(role)
    return role_response(role)


@router.put("/roles/{role_id}", response_model=RoleResponse, dependencies=[Depends(require_permission("admin.roles"))])
async def update_role(role_id: int, body: RoleUpdate, session: AsyncSession = Depends(get_session)):
    role = (await session.execute(select(Role).where(Role.id == role_id))).scalar_one_or_none()
    if not role:
        raise HTTPException(status_code=404, detail="角色不存在")
    if role.code == "admin":
        if body.enabled is False:
            raise HTTPException(status_code=400, detail="不能停用内置管理员角色")
        if body.permission_codes is not None and set(body.permission_codes) != {
            permission.code for permission in role.permissions
        }:
            raise HTTPException(status_code=400, detail="内置管理员始终拥有全部权限")
    if body.registration_default is True:
        await session.execute(update(Role).where(Role.id != role_id).values(registration_default=False))
    for field in ("name", "description", "enabled", "registration_default"):
        value = getattr(body, field)
        if value is not None:
            setattr(role, field, value)
    if body.permission_codes is not None:
        role.permissions = list((await session.execute(
            select(Permission).where(Permission.code.in_(body.permission_codes))
        )).scalars().all())
    await session.commit()
    return role_response(role)


@router.get("/modules", response_model=list[ModuleResponse], dependencies=[Depends(require_permission("admin.modules"))])
async def list_modules(session: AsyncSession = Depends(get_session)):
    return [module_response(module) for module in (await session.execute(select(Module).order_by(Module.sort_order))).scalars()]


@router.post("/modules", response_model=ModuleResponse, status_code=201, dependencies=[Depends(require_permission("admin.modules"))])
async def create_module(body: ModuleCreate, session: AsyncSession = Depends(get_session)):
    if (await session.execute(select(Module).where(Module.code == body.code))).scalar_one_or_none():
        raise HTTPException(status_code=409, detail="模块编码已存在")
    values = body.model_dump()
    if not values["api_prefixes"]:
        values["api_prefixes"] = f"/api/v1/{body.code}"
    if not values["api_permission"]:
        values["api_permission"] = f"{body.code}.view"
    module = Module(**values)
    session.add(module)
    await session.flush()
    view_permission = Permission(code=f"{module.code}.view", name=f"查看{module.name}", module=module)
    session.add(view_permission)
    await session.flush()
    admin_role_ids = (await session.execute(select(Role.id).where(Role.code == "admin"))).scalars().all()
    if admin_role_ids:
        await session.execute(insert(role_permissions), [
            {"role_id": role_id, "permission_id": view_permission.id}
            for role_id in admin_role_ids
        ])
    await session.commit()
    await session.refresh(module)
    invalidate_module_rules()
    return module_response(module)


@router.put("/modules/{module_id}", response_model=ModuleResponse, dependencies=[Depends(require_permission("admin.modules"))])
async def update_module(module_id: int, body: ModuleUpdate, session: AsyncSession = Depends(get_session)):
    module = (await session.execute(select(Module).where(Module.id == module_id))).scalar_one_or_none()
    if not module:
        raise HTTPException(status_code=404, detail="模块不存在")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(module, field, value)
    await session.commit()
    invalidate_module_rules()
    return module_response(module)


@router.get("/permissions", response_model=list[PermissionResponse], dependencies=[Depends(require_permission("admin.roles"))])
async def list_permissions(session: AsyncSession = Depends(get_session)):
    permissions = (await session.execute(
        select(Permission).options(selectinload(Permission.module)).order_by(Permission.code)
    )).scalars().all()
    return [PermissionResponse(
        id=item.id, code=item.code, name=item.name, description=item.description,
        module_code=item.module.code if item.module else None,
    ) for item in permissions]


@router.post("/permissions", response_model=PermissionResponse, status_code=201, dependencies=[Depends(require_permission("admin.modules"))])
async def create_permission(body: PermissionCreate, session: AsyncSession = Depends(get_session)):
    if (await session.execute(select(Permission).where(Permission.code == body.code))).scalar_one_or_none():
        raise HTTPException(status_code=409, detail="权限编码已存在")
    module = None
    if body.module_code:
        module = (await session.execute(select(Module).where(Module.code == body.module_code))).scalar_one_or_none()
        if not module:
            raise HTTPException(status_code=400, detail="模块不存在")
    permission = Permission(code=body.code, name=body.name, description=body.description, module=module)
    session.add(permission)
    await session.commit()
    await session.refresh(permission)
    return PermissionResponse(
        id=permission.id, code=permission.code, name=permission.name,
        description=permission.description, module_code=module.code if module else None,
    )
