from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from datetime import datetime

from sqlalchemy import delete, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.auth import Module, Permission, Role, User, role_permissions, user_roles
from app.models.template import Template


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64decode(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def hash_password(password: str) -> str:
    if len(password) < 8:
        raise ValueError("密码至少需要 8 位")
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 210_000)
    return f"pbkdf2_sha256$210000${_b64encode(salt)}${_b64encode(digest)}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, rounds, salt, expected = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), _b64decode(salt), int(rounds))
        return hmac.compare_digest(actual, _b64decode(expected))
    except (ValueError, TypeError):
        return False


def create_access_token(user_id: int) -> tuple[str, int]:
    expires_at = int(time.time()) + settings.token_expire_minutes * 60
    header = _b64encode(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    payload = _b64encode(json.dumps({"sub": str(user_id), "exp": expires_at}, separators=(",", ":")).encode())
    signing_input = f"{header}.{payload}"
    signature = hmac.new(settings.token_secret.encode(), signing_input.encode(), hashlib.sha256).digest()
    return f"{signing_input}.{_b64encode(signature)}", expires_at


def decode_access_token(token: str) -> int:
    try:
        header, payload, signature = token.split(".")
        signing_input = f"{header}.{payload}"
        expected = hmac.new(settings.token_secret.encode(), signing_input.encode(), hashlib.sha256).digest()
        # 比较规范化后的 Base64URL 文本，拒绝“解码字节相同但末尾字符被篡改”的非规范编码。
        if not hmac.compare_digest(_b64encode(expected), signature):
            raise ValueError("无效 Token")
        claims = json.loads(_b64decode(payload))
        if int(claims["exp"]) <= int(time.time()):
            raise ValueError("Token 已过期")
        return int(claims["sub"])
    except (KeyError, ValueError, TypeError, json.JSONDecodeError) as error:
        raise ValueError("无效或已过期的 Token") from error


def permission_codes(user: User) -> set[str]:
    return {
        permission.code
        for role in user.roles
        if role.enabled
        for permission in role.permissions
    }


async def authenticate(session: AsyncSession, username: str, password: str) -> User | None:
    result = await session.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()
    if not user or not user.enabled or not verify_password(password, user.password_hash):
        return None
    user.last_login_at = datetime.now()
    await session.commit()
    return user


MODULE_DEFINITIONS = [
    ("indicators", "指标", "chart", "indicators", "/indicators", "/api/v1/indicator,/api/v1/klines,/api/v1/chan,/api/v1/symbols", "analysis.compute", 10),
    ("strategy", "策略", "strategy", "strategy", "/strategy", "/api/v1/templates,/api/v1/signal", "strategy.view", 20),
    ("screener", "选股", "filter", "screener", "/screener", "/api/v1/screener", "screener.view", 30),
    ("admin", "系统", "settings", "admin", "/admin", "/api/v1/admin", "admin.view", 100),
]

PERMISSION_DEFINITIONS = [
    ("market.read", "读取行情", None),
    ("analysis.compute", "计算行情分析", None),
    ("indicators.view", "查看指标", "indicators"),
    ("indicators.calculate", "计算指标", "indicators"),
    ("strategy.view", "查看策略", "strategy"),
    ("strategy.manage", "管理策略", "strategy"),
    ("strategy.evaluate", "评估策略", "strategy"),
    ("strategy.backtest", "策略回测", "strategy"),
    ("screener.view", "查看选股", "screener"),
    ("screener.run", "执行选股", "screener"),
    ("admin.view", "查看系统管理", "admin"),
    ("admin.users", "用户管理", "admin"),
    ("admin.roles", "角色管理", "admin"),
    ("admin.modules", "模块管理", "admin"),
]


async def seed_access_control(session: AsyncSession):
    existing_modules = {item.code: item for item in (await session.execute(select(Module))).scalars()}
    for code, name, icon, component_key, route_path, api_prefixes, api_permission, sort_order in MODULE_DEFINITIONS:
        if code not in existing_modules:
            module = Module(
                code=code, name=name, icon=icon, component_key=component_key,
                route_path=route_path, api_prefixes=api_prefixes,
                api_permission=api_permission, sort_order=sort_order,
            )
            session.add(module)
            existing_modules[code] = module
        elif not existing_modules[code].api_prefixes:
            existing_modules[code].api_prefixes = api_prefixes
        if not existing_modules[code].api_permission:
            existing_modules[code].api_permission = api_permission
    await session.flush()

    existing_permissions = {item.code: item for item in (await session.execute(select(Permission))).scalars()}
    for code, name, module_code in PERMISSION_DEFINITIONS:
        if code not in existing_permissions:
            permission = Permission(
                code=code,
                name=name,
                module=existing_modules[module_code] if module_code else None,
            )
            session.add(permission)
            existing_permissions[code] = permission
    await session.flush()

    roles = {item.code: item for item in (await session.execute(select(Role))).scalars()}
    member_created = "member" not in roles
    if "admin" not in roles:
        roles["admin"] = Role(code="admin", name="管理员", description="拥有全部权限", built_in=True)
        session.add(roles["admin"])
    if "member" not in roles:
        roles["member"] = Role(code="member", name="普通用户", description="默认业务功能", built_in=True)
        session.add(roles["member"])
    await session.flush()
    reset_role_ids = [roles["admin"].id]
    if member_created:
        reset_role_ids.append(roles["member"].id)
    await session.execute(delete(role_permissions).where(
        role_permissions.c.role_id.in_(reset_role_ids)
    ))
    admin_permission_ids = [permission.id for permission in existing_permissions.values()]
    member_permission_ids = [
        permission.id for code, permission in existing_permissions.items()
        if not code.startswith("admin.")
    ]
    if admin_permission_ids:
        await session.execute(insert(role_permissions), [
            {"role_id": roles["admin"].id, "permission_id": permission_id}
            for permission_id in admin_permission_ids
        ])
    if member_created and member_permission_ids:
        await session.execute(insert(role_permissions), [
            {"role_id": roles["member"].id, "permission_id": permission_id}
            for permission_id in member_permission_ids
        ])

    users = (await session.execute(select(User))).scalars().all()
    if not users:
        admin = User(
            username=settings.bootstrap_admin_username,
            display_name="系统管理员",
            password_hash=hash_password(settings.bootstrap_admin_password),
            enabled=True,
        )
        session.add(admin)
        await session.flush()
        await session.execute(insert(user_roles).values(user_id=admin.id, role_id=roles["admin"].id))
        users = [admin]
    bootstrap_admin = next((user for user in users if user.username == settings.bootstrap_admin_username), users[0])
    # 兼容升级前没有归属人的策略数据，将其交给首个管理员。
    await session.execute(
        update(Template).where(Template.user_id.is_(None)).values(user_id=bootstrap_admin.id)
    )
    await session.commit()
    from app.services.module_access_service import invalidate_module_rules
    invalidate_module_rules()
