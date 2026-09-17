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

CREATE TABLE IF NOT EXISTS notification_channels (
    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    name VARCHAR(80) NOT NULL,
    channel_type VARCHAR(20) NOT NULL,
    webhook_url VARCHAR(1000),
    enabled BOOLEAN NOT NULL DEFAULT 1,
    is_shared BOOLEAN NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS notification_templates (
    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    event_type VARCHAR(32) NOT NULL UNIQUE,
    name VARCHAR(80) NOT NULL,
    content VARCHAR(4000) NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT 1,
    updated_by INTEGER,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS content_templates (
    id VARCHAR(64) NOT NULL PRIMARY KEY,
    user_id INTEGER,
    name VARCHAR(100) NOT NULL,
    description VARCHAR(500) NOT NULL DEFAULT '',
    sections JSON NOT NULL DEFAULT '[]',
    enabled BOOLEAN NOT NULL DEFAULT 1,
    built_in BOOLEAN NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS article_drafts (
    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    template_id VARCHAR(64) NOT NULL,
    title VARCHAR(200) NOT NULL,
    symbol VARCHAR(32) NOT NULL,
    symbol_name VARCHAR(100) NOT NULL,
    market VARCHAR(16) NOT NULL,
    as_of DATETIME NOT NULL,
    timeframes JSON NOT NULL DEFAULT '[]',
    structured_data JSON NOT NULL DEFAULT '{}',
    chart_specs JSON NOT NULL DEFAULT '[]',
    standard_markdown TEXT NOT NULL,
    platform_variants JSON NOT NULL DEFAULT '{}',
    status VARCHAR(24) NOT NULL DEFAULT 'draft',
    reviewed_at DATETIME,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_article_draft_user ON article_drafts (user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_article_draft_symbol ON article_drafts (symbol, as_of);

CREATE TABLE IF NOT EXISTS strategy_monitors (
    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    template_id VARCHAR(64) NOT NULL,
    symbol VARCHAR(32) NOT NULL,
    symbol_name VARCHAR(80) NOT NULL DEFAULT '',
    channel_ids JSON NOT NULL DEFAULT '[]',
    enabled BOOLEAN NOT NULL DEFAULT 1,
    poll_interval_seconds INTEGER NOT NULL DEFAULT 60,
    last_checked_at DATETIME,
    last_bar_time BIGINT,
    in_position BOOLEAN NOT NULL DEFAULT 0,
    entry_price REAL,
    stop_loss_price REAL,
    take_profit_price REAL,
    event_types JSON NOT NULL DEFAULT '["entry","exit","stop_loss","take_profit"]',
    schedule_enabled BOOLEAN NOT NULL DEFAULT 0,
    schedule_time VARCHAR(5) NOT NULL DEFAULT '09:30',
    schedule_weekdays JSON NOT NULL DEFAULT '[1,2,3,4,5]',
    last_schedule_key VARCHAR(32),
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (user_id, template_id, symbol)
);

CREATE TABLE IF NOT EXISTS notification_events (
    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    monitor_id INTEGER NOT NULL,
    event_type VARCHAR(24) NOT NULL,
    symbol VARCHAR(32) NOT NULL,
    symbol_name VARCHAR(80) NOT NULL DEFAULT '',
    template_name VARCHAR(100) NOT NULL,
    timeframe VARCHAR(10) NOT NULL,
    bar_time BIGINT NOT NULL,
    price REAL NOT NULL,
    title VARCHAR(160) NOT NULL,
    content VARCHAR(2000) NOT NULL,
    delivery_status JSON NOT NULL DEFAULT '{}',
    is_read BOOLEAN NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (monitor_id, event_type, bar_time)
);

CREATE TABLE IF NOT EXISTS screener_schedules (
    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    template_id VARCHAR(64) NOT NULL,
    market VARCHAR(16) NOT NULL DEFAULT 'stock',
    universe_limit INTEGER NOT NULL DEFAULT 50,
    min_progress INTEGER NOT NULL DEFAULT 1,
    schedule_time VARCHAR(5) NOT NULL DEFAULT '01:00',
    schedule_weekdays JSON NOT NULL DEFAULT '[1,2,3,4,5]',
    channel_ids JSON NOT NULL DEFAULT '[]',
    enabled BOOLEAN NOT NULL DEFAULT 1,
    last_run_key VARCHAR(32),
    last_run_at DATETIME,
    last_result_count INTEGER NOT NULL DEFAULT 0,
    last_error VARCHAR(500),
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (user_id, template_id, market, schedule_time)
);

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
    registration_default BOOLEAN NOT NULL DEFAULT 0,
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
    public_access BOOLEAN      NOT NULL DEFAULT 0,
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

CREATE TABLE IF NOT EXISTS public_indicator_policies (
    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    indicator_type VARCHAR(64) NOT NULL UNIQUE,
    display_name VARCHAR(100) NOT NULL DEFAULT '',
    public_visible BOOLEAN NOT NULL DEFAULT 1,
    show_parameters BOOLEAN NOT NULL DEFAULT 1,
    show_details BOOLEAN NOT NULL DEFAULT 1,
    show_markers BOOLEAN NOT NULL DEFAULT 0,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS public_indicator_feature_policies (
    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    indicator_type VARCHAR(64) NOT NULL,
    feature_code VARCHAR(100) NOT NULL,
    display_name VARCHAR(100) NOT NULL,
    public_visible BOOLEAN NOT NULL DEFAULT 0,
    show_details BOOLEAN NOT NULL DEFAULT 0,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (indicator_type, feature_code)
);
