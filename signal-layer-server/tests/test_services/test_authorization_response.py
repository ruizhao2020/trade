"""左导航模块列表的过滤规则。

两条规则共同决定"用户能看到哪些模块"：
  1. 模块启用、可见，且用户持有 `{code}.view`；
  2. 非公开模块还要求 `private.access` —— 与模块准入中间件保持一致，
     否则导航会列出用户实际打不开的入口（点进去每个接口都是 403）。
"""

from app.api.auth import user_response
from app.models.auth import Module, Permission, Role, User


def make_module(id: int, code: str, *, api_permission: str, public_access: bool = False) -> Module:
    return Module(
        id=id, code=code, name=code, icon="chart",
        component_key=code, route_path=f"/{code}",
        api_prefixes=f"/api/v1/{code}", api_permission=api_permission, sort_order=id * 10,
        enabled=True, visible=True, public_access=public_access,
    )


def make_user(*permission_codes: str) -> User:
    role = Role(id=1, code="reader", name="只读用户", enabled=True)
    role.permissions = [
        Permission(id=index + 1, code=code, name=code)
        for index, code in enumerate(permission_codes)
    ]
    user = User(id=1, username="reader", display_name="只读用户", password_hash="x", enabled=True)
    user.roles = [role]
    return user


def test_modules_are_filtered_by_role_permissions():
    """没有 admin.view 的用户不应该看到 admin 模块。"""
    indicator = make_module(1, "indicators", api_permission="analysis.compute")
    admin = make_module(2, "admin", api_permission="admin.view")

    response = user_response(
        make_user("private.access", "indicators.view"),
        [indicator, admin],
    )

    assert [module.code for module in response.modules] == ["indicators"]
    assert response.permission_codes == ["indicators.view", "private.access"]


def test_non_public_modules_require_private_access():
    """持有 {code}.view 但没有 private.access 时，非公开模块不应出现在导航里。"""
    strategy = make_module(1, "strategy", api_permission="strategy.view")

    response = user_response(make_user("strategy.view"), [strategy])

    assert response.modules == []


def test_public_modules_do_not_require_private_access():
    """公开模块（如指标）不要求 private.access，匿名面也要能进。"""
    public_indicator = make_module(1, "indicators", api_permission="analysis.compute", public_access=True)

    response = user_response(make_user("indicators.view"), [public_indicator])

    assert [module.code for module in response.modules] == ["indicators"]


def test_disabled_or_hidden_modules_are_dropped():
    """模块被停用或设为不可见时不出现，即使权限齐全。"""
    enabled = make_module(1, "strategy", api_permission="strategy.view")
    disabled = make_module(2, "advisor", api_permission="advisor.view")
    disabled.enabled = False
    hidden = make_module(3, "content", api_permission="content.view")
    hidden.visible = False

    response = user_response(
        make_user("private.access", "strategy.view", "advisor.view", "content.view"),
        [enabled, disabled, hidden],
    )

    assert [module.code for module in response.modules] == ["strategy"]
