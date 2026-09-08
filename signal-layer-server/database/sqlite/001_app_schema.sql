PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS templates (
    id               VARCHAR(64)  NOT NULL PRIMARY KEY,
    user_id          BIGINT,
    name             VARCHAR(100) NOT NULL,
    logic            VARCHAR(3)   NOT NULL DEFAULT 'AND',
    condition_groups JSON         NOT NULL DEFAULT '[]',
    primary_tf       VARCHAR(10)  NOT NULL DEFAULT '1d',
    secondary_tfs    JSON,
    enabled          BOOLEAN      NOT NULL DEFAULT 1,
    trade_params     JSON,
    created_at       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_user ON templates (user_id);

CREATE TABLE IF NOT EXISTS klines (
    id          INTEGER       NOT NULL PRIMARY KEY AUTOINCREMENT,
    symbol      VARCHAR(20)   NOT NULL,
    timeframe   VARCHAR(10)   NOT NULL,
    open_time   BIGINT        NOT NULL,
    open        NUMERIC(24,8) NOT NULL,
    high        NUMERIC(24,8) NOT NULL,
    low         NUMERIC(24,8) NOT NULL,
    close       NUMERIC(24,8) NOT NULL,
    volume      NUMERIC(24,8) NOT NULL,
    turnover    NUMERIC(24,8),
    is_closed   BOOLEAN       NOT NULL DEFAULT 1,
    created_at  DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uk_symbol_tf_time UNIQUE (symbol, timeframe, open_time)
);

CREATE INDEX IF NOT EXISTS idx_symbol_tf ON klines (symbol, timeframe);
CREATE INDEX IF NOT EXISTS idx_open_time ON klines (open_time);
