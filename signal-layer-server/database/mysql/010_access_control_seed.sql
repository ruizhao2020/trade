-- 默认账号仅用于首次初始化，生产部署后请立即修改密码。
-- 用户名：admin，初始密码：Admin123!

INSERT INTO modules
    (code, name, icon, component_key, route_path, api_prefixes, api_permission, sort_order, enabled, visible, public_access)
VALUES
    ('indicators', '指标', 'chart', 'indicators', '/indicators', '/api/v1/indicator,/api/v1/klines,/api/v1/chan,/api/v1/symbols', 'analysis.compute', 10, 1, 1, 1),
    ('strategy', '策略', 'strategy', 'strategy', '/strategy', '/api/v1/templates,/api/v1/signal', 'strategy.view', 20, 1, 1, 0),
    ('screener', '选股', 'filter', 'screener', '/screener', '/api/v1/screener', 'screener.view', 30, 1, 1, 0),
    ('admin', '系统', 'settings', 'admin', '/admin', '/api/v1/admin', 'admin.view', 100, 1, 1, 0),
    ('notifications', '通知', 'bell', 'notifications', '/notifications', '/api/v1/notifications', 'notifications.view', 40, 1, 1, 0)
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
    UNION ALL SELECT 'notifications.view', '查看通知', 'notifications'
    UNION ALL SELECT 'notifications.manage', '管理个人通知任务', 'notifications'
    UNION ALL SELECT 'notifications.admin', '管理通知渠道和模板', 'notifications'
) AS seed
JOIN modules ON modules.code = seed.module_code
ON DUPLICATE KEY UPDATE name=VALUES(name), module_id=VALUES(module_id);

INSERT INTO roles (code, name, description, built_in, enabled, registration_default)
VALUES
    ('admin', '管理员', '拥有全部权限', 1, 1, 0),
    ('member', '普通用户', '默认业务功能', 1, 1, 1)
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
WHERE roles.code = 'member' AND permissions.code NOT LIKE 'admin.%' AND permissions.code <> 'notifications.admin';

INSERT IGNORE INTO user_roles (user_id, role_id)
SELECT users.id, roles.id
FROM users JOIN roles ON roles.code = 'admin'
WHERE users.username = 'admin';

INSERT INTO notification_templates (event_type, name, content, enabled)
VALUES
    ('screener_completed', '定时选股完成', '【定时选股完成】\\n策略：{{strategy_name}}\\n市场：{{market}}\\n扫描：{{scanned_count}} 个，命中：{{matched_count}} 个\\n结果：{{screen_results}}\\n时间：{{trigger_time}}', 1),
    ('screener_failed', '定时选股失败', '【定时选股失败】\\n策略：{{strategy_name}}\\n原因：{{error}}\\n时间：{{trigger_time}}', 1),
    ('entry', '策略建仓', '【策略建仓】\\n策略：{{strategy_name}}\\n标的：{{symbol_name}}（{{symbol}}）\\n价格：{{price}}\\n建议仓位：{{position_size}}\\n止损：{{stop_loss}}\\n止盈：{{take_profit}}\\n时间：{{trigger_time}}', 1),
    ('exit', '策略清仓', '【策略清仓】\\n策略：{{strategy_name}}\\n标的：{{symbol_name}}（{{symbol}}）\\n价格：{{price}}\\n时间：{{trigger_time}}', 1),
    ('stop_loss', '触发止损', '【触发止损】\\n策略：{{strategy_name}}\\n标的：{{symbol_name}}（{{symbol}}）\\n价格：{{price}}\\n止损价：{{stop_loss}}\\n时间：{{trigger_time}}', 1),
    ('take_profit', '触发止盈', '【触发止盈】\\n策略：{{strategy_name}}\\n标的：{{symbol_name}}（{{symbol}}）\\n价格：{{price}}\\n止盈价：{{take_profit}}\\n时间：{{trigger_time}}', 1),
    ('scheduled', '策略定时快照', '【策略定时推送】\\n策略：{{strategy_name}}\\n标的：{{symbol_name}}（{{symbol}}）\\n最新价：{{price}}\\n信号状态：{{signal_status}}\\n时间：{{trigger_time}}', 1)
ON DUPLICATE KEY UPDATE name=VALUES(name);
