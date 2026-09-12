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
    amount      NUMERIC(24,8),
    turnover    NUMERIC(24,8),
    turnover_rate      NUMERIC(16,8),
    circulating_shares NUMERIC(24,4),
    adjustment_factor NUMERIC(24,12),
    adjustment_type   VARCHAR(8),
    is_closed   BOOLEAN       NOT NULL DEFAULT 1,
    created_at  DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uk_symbol_tf_time UNIQUE (symbol, timeframe, open_time)
);

CREATE INDEX IF NOT EXISTS idx_symbol_tf ON klines (symbol, timeframe);
CREATE INDEX IF NOT EXISTS idx_open_time ON klines (open_time);

CREATE TABLE IF NOT EXISTS users (
    id            INTEGER      NOT NULL PRIMARY KEY AUTOINCREMENT,
    username      VARCHAR(50)  NOT NULL UNIQUE,
    email         VARCHAR(120) UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    display_name  VARCHAR(80)  NOT NULL DEFAULT '',
    enabled       BOOLEAN      NOT NULL DEFAULT 1,
    last_login_at DATETIME,
    created_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS roles (
    id          INTEGER      NOT NULL PRIMARY KEY AUTOINCREMENT,
    code        VARCHAR(64)  NOT NULL UNIQUE,
    name        VARCHAR(80)  NOT NULL,
    description VARCHAR(255) NOT NULL DEFAULT '',
    built_in    BOOLEAN      NOT NULL DEFAULT 0,
    enabled     BOOLEAN      NOT NULL DEFAULT 1,
    created_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS modules (
    id            INTEGER      NOT NULL PRIMARY KEY AUTOINCREMENT,
    code          VARCHAR(64)  NOT NULL UNIQUE,
    name          VARCHAR(80)  NOT NULL,
    icon          VARCHAR(40)  NOT NULL DEFAULT 'module',
    component_key VARCHAR(80)  NOT NULL DEFAULT '',
    route_path    VARCHAR(120) NOT NULL DEFAULT '',
    api_prefixes  VARCHAR(500) NOT NULL DEFAULT '',
    api_permission VARCHAR(100) NOT NULL DEFAULT '',
    sort_order    INTEGER      NOT NULL DEFAULT 0,
    enabled       BOOLEAN      NOT NULL DEFAULT 1,
    visible       BOOLEAN      NOT NULL DEFAULT 1,
    created_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS permissions (
    id          INTEGER      NOT NULL PRIMARY KEY AUTOINCREMENT,
    code        VARCHAR(100) NOT NULL UNIQUE,
    name        VARCHAR(100) NOT NULL,
    description VARCHAR(255) NOT NULL DEFAULT '',
    module_id   INTEGER,
    created_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (module_id) REFERENCES modules(id) ON DELETE SET NULL
);
CREATE INDEX IF NOT EXISTS idx_permission_module ON permissions (module_id);

CREATE TABLE IF NOT EXISTS user_roles (
    user_id INTEGER NOT NULL,
    role_id INTEGER NOT NULL,
    PRIMARY KEY (user_id, role_id),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (role_id) REFERENCES roles(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS role_permissions (
    role_id       INTEGER NOT NULL,
    permission_id INTEGER NOT NULL,
    PRIMARY KEY (role_id, permission_id),
    FOREIGN KEY (role_id) REFERENCES roles(id) ON DELETE CASCADE,
    FOREIGN KEY (permission_id) REFERENCES permissions(id) ON DELETE CASCADE
);
