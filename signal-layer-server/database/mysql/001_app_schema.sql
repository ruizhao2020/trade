CREATE TABLE IF NOT EXISTS templates (
    id               VARCHAR(64)  NOT NULL PRIMARY KEY,
    user_id          BIGINT,
    name             VARCHAR(100) NOT NULL,
    logic            VARCHAR(3)   NOT NULL DEFAULT 'AND',
    condition_groups JSON         NOT NULL,
    primary_tf       VARCHAR(10)  NOT NULL DEFAULT '1d',
    secondary_tfs    JSON,
    enabled          BOOLEAN      NOT NULL DEFAULT TRUE,
    trade_params     JSON,
    created_at       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_user (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS klines (
    id          BIGINT        NOT NULL AUTO_INCREMENT PRIMARY KEY,
    symbol      VARCHAR(20)   NOT NULL,
    timeframe   VARCHAR(10)   NOT NULL,
    open_time   BIGINT        NOT NULL,
    open        DECIMAL(24,8) NOT NULL,
    high        DECIMAL(24,8) NOT NULL,
    low         DECIMAL(24,8) NOT NULL,
    close       DECIMAL(24,8) NOT NULL,
    volume      DECIMAL(24,8) NOT NULL,
    turnover    DECIMAL(24,8),
    is_closed   TINYINT(1)    NOT NULL DEFAULT 1,
    created_at  DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_symbol_tf_time (symbol, timeframe, open_time),
    INDEX idx_symbol_tf (symbol, timeframe),
    INDEX idx_open_time (open_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
