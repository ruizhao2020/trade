-- 默认账号仅用于首次初始化，生产部署后请立即修改密码。
-- 用户名：admin，初始密码：Admin123!

INSERT INTO modules
    (code, name, icon, component_key, route_path, api_prefixes, api_permission, sort_order, enabled, visible)
VALUES
    ('indicators', '指标', 'chart', 'indicators', '/indicators', '/api/v1/indicator,/api/v1/klines,/api/v1/chan,/api/v1/symbols', 'analysis.compute', 10, 1, 1),
    ('strategy', '策略', 'strategy', 'strategy', '/strategy', '/api/v1/templates,/api/v1/signal', 'strategy.view', 20, 1, 1),
    ('screener', '选股', 'filter', 'screener', '/screener', '/api/v1/screener', 'screener.view', 30, 1, 1),
    ('admin', '系统', 'settings', 'admin', '/admin', '/api/v1/admin', 'admin.view', 100, 1, 1)
ON DUPLICATE KEY UPDATE
    name=VALUES(name), icon=VALUES(icon), component_key=VALUES(component_key),
    route_path=VALUES(route_path), api_prefixes=VALUES(api_prefixes),
    api_permission=VALUES(api_permission), sort_order=VALUES(sort_order);

INSERT INTO permissions (code, name, description, module_id)
VALUES
    ('market.read', '读取行情', '', NULL),
    ('analysis.compute', '计算行情分析', '', NULL)
ON DUPLICATE KEY UPDATE name=VALUES(name), description=VALUES(description);

INSERT INTO permissions (code, name, description, module_id)
SELECT seed.code, seed.name, '', modules.id
FROM (
    SELECT 'indicators.view' AS code, '查看指标' AS name, 'indicators' AS module_code
    UNION ALL SELECT 'indicators.calculate', '计算指标', 'indicators'
    UNION ALL SELECT 'strategy.view', '查看策略', 'strategy'
    UNION ALL SELECT 'strategy.manage', '管理策略', 'strategy'
    UNION ALL SELECT 'strategy.evaluate', '评估策略', 'strategy'
    UNION ALL SELECT 'strategy.backtest', '策略回测', 'strategy'
    UNION ALL SELECT 'screener.view', '查看选股', 'screener'
    UNION ALL SELECT 'screener.run', '执行选股', 'screener'
    UNION ALL SELECT 'admin.view', '查看系统管理', 'admin'
    UNION ALL SELECT 'admin.users', '用户管理', 'admin'
    UNION ALL SELECT 'admin.roles', '角色管理', 'admin'
    UNION ALL SELECT 'admin.modules', '模块管理', 'admin'
) AS seed
JOIN modules ON modules.code = seed.module_code
ON DUPLICATE KEY UPDATE name=VALUES(name), module_id=VALUES(module_id);

INSERT INTO roles (code, name, description, built_in, enabled)
VALUES
    ('admin', '管理员', '拥有全部权限', 1, 1),
    ('member', '普通用户', '默认业务功能', 1, 1)
ON DUPLICATE KEY UPDATE
    name=VALUES(name), description=VALUES(description), built_in=VALUES(built_in);

INSERT INTO users (username, email, password_hash, display_name, enabled)
VALUES (
    'admin', NULL,
    'pbkdf2_sha256$210000$k8klz56Zk1AvuBWw6pJj8Q$UU1qzdx7mhnUbcX0JkdzLypxNH8m0J9EElYqYHVjhV4',
    '系统管理员', 1
)
ON DUPLICATE KEY UPDATE username=VALUES(username);

INSERT IGNORE INTO role_permissions (role_id, permission_id)
SELECT roles.id, permissions.id
FROM roles CROSS JOIN permissions
WHERE roles.code = 'admin';

INSERT IGNORE INTO role_permissions (role_id, permission_id)
SELECT roles.id, permissions.id
FROM roles CROSS JOIN permissions
WHERE roles.code = 'member' AND permissions.code NOT LIKE 'admin.%';

INSERT IGNORE INTO user_roles (user_id, role_id)
SELECT users.id, roles.id
FROM users JOIN roles ON roles.code = 'admin'
WHERE users.username = 'admin';
