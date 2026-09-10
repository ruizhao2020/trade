"""
============================================================================
应用配置（pydantic-settings）
============================================================================

## 功能
从环境变量或 .env 文件读取应用配置。所有配置项都通过 settings 实例访问。
环境变量前缀为 SIGNAL_（如 SIGNAL_MYSQL_HOST）。

## 配置项
- app_name/app_version: 应用基本信息
- MySQL 连接参数（host/port/user/password/database）
- Redis 连接参数（host/port/db/password）
- cache_ttl: 计算结果缓存时间（默认 300 秒）
- mock_base_price/mock_candle_count: 模拟数据参数
"""

import logging
from urllib.parse import quote_plus

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s | %(message)s',
    datefmt='%H:%M:%S',
)

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """应用全局配置。所有值可通过 .env 文件或 SIGNAL_ 前缀的环境变量覆盖"""

    # ==================== 应用基本信息 ====================
    app_name: str = "SignalLayer"
    app_version: str = "0.1.0"
    debug: bool = True

    # ==================== MySQL 数据库连接 ====================
    mysql_host: str = "localhost"
    mysql_port: int = 3306
    mysql_user: str = "root"
    mysql_password: str = "signal_layer"
    mysql_database: str = "signal_layer"
    mysql_pool_size: int = 10
    mysql_max_overflow: int = 20

    # ==================== Redis 缓存连接 ====================
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: str = ""

    # ==================== 缓存策略 ====================
    cache_ttl: int = 300

    # ==================== 开发/模拟数据 ====================
    mock_base_price: float = 50000.0
    mock_candle_count: int = 200

    # ==================== 认证与权限 ====================
    token_secret: str = "change-this-secret-before-production"
    token_expire_minutes: int = 1440
    bootstrap_admin_username: str = "admin"
    bootstrap_admin_password: str = "Admin123!"
    cors_origins: str = "http://localhost:4173,http://127.0.0.1:4173"

    @property
    def database_url(self) -> str:
        """组装 MySQL 连接字符串（aiomysql 驱动）"""
        return (
            f"mysql+aiomysql://{quote_plus(self.mysql_user)}:{quote_plus(self.mysql_password)}"
            f"@{self.mysql_host}:{self.mysql_port}/{self.mysql_database}"
            f"?charset=utf8mb4"
        )

    @property
    def redis_url(self) -> str:
        """组装 Redis 连接字符串"""
        auth = f":{self.redis_password}@" if self.redis_password else ""
        return f"redis://{auth}{self.redis_host}:{self.redis_port}/{self.redis_db}"

    model_config = {"env_prefix": "SIGNAL_", "env_file": ".env"}


# 全局配置实例。模块级导入：from app.config import settings
settings = Settings()
