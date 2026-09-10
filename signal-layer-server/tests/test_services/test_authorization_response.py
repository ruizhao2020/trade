from app.api.auth import user_response
from app.models.auth import Module, Permission, Role, User


def test_navigation_modules_are_filtered_by_role_permissions():
    indicator = Module(
        id=1, code="indicators", name="指标", icon="chart",
        component_key="indicators", route_path="/indicators", api_prefixes="/api/v1/indicator", api_permission="analysis.compute", sort_order=10,
        enabled=True, visible=True,
    )
    admin = Module(
        id=2, code="admin", name="系统", icon="settings",
        component_key="admin", route_path="/admin", api_prefixes="/api/v1/admin", api_permission="admin.view", sort_order=100,
        enabled=True, visible=True,
    )
    role = Role(id=1, code="reader", name="只读用户", enabled=True)
    role.permissions = [Permission(id=1, code="indicators.view", name="查看指标")]
    user = User(id=1, username="reader", display_name="只读用户", password_hash="x", enabled=True)
    user.roles = [role]

    response = user_response(user, [indicator, admin])

    assert [module.code for module in response.modules] == ["indicators"]
    assert response.permission_codes == ["indicators.view"]
