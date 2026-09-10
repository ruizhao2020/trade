# 数据库初始化

本目录只保存项目的固定表结构。正式运行统一使用 MySQL，SQLite 脚本仅用于测试和历史数据迁移。运行时动态创建的行情表不在这里维护。

## 固定表

| 数据库 | 表 | 用途 |
| --- | --- | --- |
| 应用库 | `templates` | 策略、入场/出场条件和交易参数 |
| 应用库 | `klines` | 项目保留的通用 K 线模型 |
| 应用库 | `users` | 登录用户 |
| 应用库 | `roles` | 角色配置 |
| 应用库 | `modules` | 配置驱动的左侧模块 |
| 应用库 | `permissions` | 模块与功能权限点 |
| 应用库 | `user_roles` | 用户角色关系 |
| 应用库 | `role_permissions` | 角色权限关系 |
| 行情库 | `stock_info` | A 股标的名称与行业信息 |

## 不纳入脚本的动态表

- `{symbol}_{周期}`，例如 `000001_sz_日线`、`RB0_5分钟`
- `_market_data_coverage`

这些表由 `MySQLMarketDataStore` 按需创建。

## 初始化方式

SQLite 测试/迁移库：

```bash
sqlite3 data/signal_layer.db < database/sqlite/001_app_schema.sql
sqlite3 data/signal_layer.db < database/sqlite/010_access_control_seed.sql
```

MySQL 应用库：

```bash
mysql -u root -p signal_layer < database/mysql/001_app_schema.sql
mysql -u root -p signal_layer < database/mysql/010_access_control_seed.sql
```

初始化后会创建内置模块、14 个权限点、`admin/member` 角色及首个管理员。开发环境初始账号为 `admin / Admin123!`，首次登录后应立即修改密码。

MySQL 行情库固定表：

```bash
mysql -u root -p stock < database/mysql/002_market_reference_schema.sql
```

使用 `docker compose up` 初始化 MySQL 时，会自动执行应用库脚本。

从旧 SQLite 迁移：

```bash
python3 scripts/migrate_sqlite_to_mysql.py data/backup/signal_layer-before-mysql.sqlite
```
