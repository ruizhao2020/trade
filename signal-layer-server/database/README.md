# 数据库初始化

本目录只保存项目的固定表结构。运行时动态创建的行情表不在这里维护。

## 固定表

| 数据库 | 表 | 用途 |
| --- | --- | --- |
| 应用库 | `templates` | 策略、入场/出场条件和交易参数 |
| 应用库 | `klines` | 项目保留的通用 K 线模型 |
| 行情库 | `stock_info` | A 股标的名称与行业信息 |

## 不纳入脚本的动态表

- `{symbol}_{周期}`，例如 `000001_sz_日线`、`RB0_5分钟`
- `_market_data_coverage`

这些表由 `MySQLMarketDataStore` 按需创建。

## 初始化方式

SQLite 应用库：

```bash
sqlite3 data/signal_layer.db < database/sqlite/001_app_schema.sql
```

MySQL 应用库：

```bash
mysql -u root -p signal_layer < database/mysql/001_app_schema.sql
```

MySQL 行情库固定表：

```bash
mysql -u root -p stock < database/mysql/002_market_reference_schema.sql
```

使用 `docker compose up` 初始化 MySQL 时，会自动执行应用库脚本。
