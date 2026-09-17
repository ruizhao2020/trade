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
| 应用库 | `public_indicator_policies` | 公开站指标、参数、详情和信号标记配置 |
| 应用库 | `public_indicator_feature_policies` | 任意指标的公开子功能、线条和信号配置 |
| 应用库 | `notification_channels` | 企业微信、飞书、浏览器通知渠道 |
| 应用库 | `notification_templates` | 管理员维护的通知内容模板 |
| 应用库 | `strategy_monitors` | 策略与标的的轮询监控配置 |
| 应用库 | `notification_events` | 建仓、清仓、止损、止盈事件记录 |
| 应用库 | `screener_schedules` | 个人定时策略选股任务 |
| 应用库 | `content_templates` | 可扩展文章分析模板 |
| 应用库 | `article_drafts` | 结构化分析、图表规格及平台文章草稿 |
| 行情库 | `stock_info` | A 股标的名称与行业信息 |

权限配置说明：`modules.public_access` 控制模块接口是否允许匿名访问；默认“指标”模块开启，其他模块关闭。`roles.registration_default` 控制新注册用户自动绑定的角色，默认角色为“普通用户”。两项均可在系统管理页面配置。

公开指标配置采用通用的“指标 + 子功能”模型。指标服务会从渲染描述中自动发现线条和信号标记，写入 `public_indicator_feature_policies`；新指标和新子功能默认不公开，管理员可在“系统 → 公开展示”中启用。缠论的分型、笔、段、中枢、背驰和买卖点也使用同一张通用表。

通知模块采用后台轮询已收盘行情（默认 60 秒，可按监控调整），触发事件后写入 `notification_events`，并投递到已启用的企业微信机器人、飞书机器人或浏览器通知渠道。它不依赖长连接实时行情；如需盘中实时提醒，可将轮询间隔调低并接入实时行情源。

## 不纳入脚本的动态表

- `{symbol}_{周期}`，例如 `000001_sz_日线`、`RB0_5分钟`
- `_market_data_coverage`

这些表由 `MySQLMarketDataStore` 按需创建。

动态行情表除 OHLCV 与成交额外，还会保存筹码计算所需的可用字段：

- `turnover_rate`：换手率，单位为百分比
- `circulating_shares`：当日流通股本，单位为股
- `adjustment_factor`：前复权因子
- `adjustment_type`：价格复权类型，当前为 `qfq`

旧动态表会在行情回填时自动补列；已有完整K线但缺少上述字段时，服务会先返回K线，并在后台补齐筹码字段，避免阻塞图表加载。

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

初始化后会创建内置模块、21 个权限点、`admin/member/researcher` 角色及首个管理员。新注册用户只有 `member` 角色，管理员授予 `researcher` 后才能进入私有研究工作区。开发环境初始账号为 `admin / Admin123!`，首次登录后应立即修改密码。

MySQL 行情库固定表：

```bash
mysql -u root -p stock < database/mysql/002_market_reference_schema.sql
```

使用 `docker compose up` 初始化 MySQL 时，会自动执行应用库脚本。

从旧 SQLite 迁移：

```bash
python3 scripts/migrate_sqlite_to_mysql.py data/backup/signal_layer-before-mysql.sqlite
```
