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

CREATE TABLE IF NOT EXISTS system_settings (
    `key`          VARCHAR(100) NOT NULL PRIMARY KEY,
    value_number   DOUBLE       NOT NULL,
    name           VARCHAR(100) NOT NULL,
    description    VARCHAR(500) NOT NULL DEFAULT '',
    created_at     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS users (
    id            INT          NOT NULL AUTO_INCREMENT PRIMARY KEY,
    username      VARCHAR(50)  NOT NULL UNIQUE,
    email         VARCHAR(120) UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    display_name  VARCHAR(80)  NOT NULL DEFAULT '',
    enabled       TINYINT(1)   NOT NULL DEFAULT 1,
    last_login_at DATETIME,
    created_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS roles (
    id          INT          NOT NULL AUTO_INCREMENT PRIMARY KEY,
    code        VARCHAR(64)  NOT NULL UNIQUE,
    name        VARCHAR(80)  NOT NULL,
    description VARCHAR(255) NOT NULL DEFAULT '',
    built_in    TINYINT(1)   NOT NULL DEFAULT 0,
    enabled     TINYINT(1)   NOT NULL DEFAULT 1,
    registration_default TINYINT(1) NOT NULL DEFAULT 0,
    created_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS modules (
    id            INT          NOT NULL AUTO_INCREMENT PRIMARY KEY,
    code          VARCHAR(64)  NOT NULL UNIQUE,
    name          VARCHAR(80)  NOT NULL,
    icon          VARCHAR(40)  NOT NULL DEFAULT 'module',
    component_key VARCHAR(80)  NOT NULL DEFAULT '',
    route_path    VARCHAR(120) NOT NULL DEFAULT '',
    api_prefixes  VARCHAR(500) NOT NULL DEFAULT '',
    api_permission VARCHAR(100) NOT NULL DEFAULT '',
    sort_order    INT          NOT NULL DEFAULT 0,
    enabled       TINYINT(1)   NOT NULL DEFAULT 1,
    visible       TINYINT(1)   NOT NULL DEFAULT 1,
    public_access TINYINT(1)   NOT NULL DEFAULT 0,
    created_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS permissions (
    id          INT          NOT NULL AUTO_INCREMENT PRIMARY KEY,
    code        VARCHAR(100) NOT NULL UNIQUE,
    name        VARCHAR(100) NOT NULL,
    description VARCHAR(255) NOT NULL DEFAULT '',
    module_id   INT,
    created_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_permission_module (module_id),
    CONSTRAINT fk_permission_module FOREIGN KEY (module_id) REFERENCES modules(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS user_roles (
    user_id INT NOT NULL,
    role_id INT NOT NULL,
    PRIMARY KEY (user_id, role_id),
    CONSTRAINT fk_user_roles_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT fk_user_roles_role FOREIGN KEY (role_id) REFERENCES roles(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS role_permissions (
    role_id       INT NOT NULL,
    permission_id INT NOT NULL,
    PRIMARY KEY (role_id, permission_id),
    CONSTRAINT fk_role_permissions_role FOREIGN KEY (role_id) REFERENCES roles(id) ON DELETE CASCADE,
    CONSTRAINT fk_role_permissions_permission FOREIGN KEY (permission_id) REFERENCES permissions(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS public_indicator_policies (
    id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    indicator_type VARCHAR(64) NOT NULL UNIQUE,
    display_name VARCHAR(100) NOT NULL DEFAULT '',
    public_visible TINYINT(1) NOT NULL DEFAULT 1,
    show_parameters TINYINT(1) NOT NULL DEFAULT 1,
    show_details TINYINT(1) NOT NULL DEFAULT 1,
    show_markers TINYINT(1) NOT NULL DEFAULT 0,
    sort_order INT NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS public_indicator_feature_policies (
    id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    indicator_type VARCHAR(64) NOT NULL,
    feature_code VARCHAR(100) NOT NULL,
    display_name VARCHAR(100) NOT NULL,
    public_visible TINYINT(1) NOT NULL DEFAULT 0,
    show_details TINYINT(1) NOT NULL DEFAULT 0,
    sort_order INT NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_public_indicator_feature (indicator_type, feature_code),
    INDEX idx_public_indicator_feature (indicator_type, sort_order)
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
    amount      DECIMAL(24,8),
    turnover    DECIMAL(24,8),
    turnover_rate      DECIMAL(16,8),
    circulating_shares DECIMAL(24,4),
    adjustment_factor DECIMAL(24,12),
    adjustment_type   VARCHAR(8),
    is_closed   TINYINT(1)    NOT NULL DEFAULT 1,
    created_at  DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_symbol_tf_time (symbol, timeframe, open_time),
    INDEX idx_symbol_tf (symbol, timeframe),
    INDEX idx_open_time (open_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS notification_channels (
    id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    name VARCHAR(80) NOT NULL,
    channel_type VARCHAR(20) NOT NULL,
    webhook_url VARCHAR(1000),
    enabled TINYINT(1) NOT NULL DEFAULT 1,
    is_shared TINYINT(1) NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_notification_channel_user (user_id),
    CONSTRAINT fk_notification_channel_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS notification_templates (
    id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    event_type VARCHAR(32) NOT NULL UNIQUE,
    name VARCHAR(80) NOT NULL,
    content VARCHAR(4000) NOT NULL,
    enabled TINYINT(1) NOT NULL DEFAULT 1,
    updated_by INT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS content_templates (
    id VARCHAR(64) NOT NULL PRIMARY KEY,
    user_id INT NULL,
    name VARCHAR(100) NOT NULL,
    description VARCHAR(500) NOT NULL DEFAULT '',
    sections JSON NOT NULL,
    enabled TINYINT(1) NOT NULL DEFAULT 1,
    built_in TINYINT(1) NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS article_drafts (
    id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    template_id VARCHAR(64) NOT NULL,
    title VARCHAR(200) NOT NULL,
    symbol VARCHAR(32) NOT NULL,
    symbol_name VARCHAR(100) NOT NULL,
    market VARCHAR(16) NOT NULL,
    as_of DATETIME NOT NULL,
    timeframes JSON NOT NULL,
    structured_data JSON NOT NULL,
    chart_specs JSON NOT NULL,
    standard_markdown LONGTEXT NOT NULL,
    platform_variants JSON NOT NULL,
    status VARCHAR(24) NOT NULL DEFAULT 'draft',
    reviewed_at DATETIME NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_article_draft_user (user_id, created_at),
    INDEX idx_article_draft_symbol (symbol, as_of)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS strategy_monitors (
    id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    template_id VARCHAR(64) NOT NULL,
    symbol VARCHAR(32) NOT NULL,
    symbol_name VARCHAR(80) NOT NULL DEFAULT '',
    channel_ids JSON NOT NULL,
    enabled TINYINT(1) NOT NULL DEFAULT 1,
    poll_interval_seconds INT NOT NULL DEFAULT 60,
    last_checked_at DATETIME NULL,
    last_bar_time BIGINT NULL,
    in_position TINYINT(1) NOT NULL DEFAULT 0,
    entry_price DOUBLE NULL,
    stop_loss_price DOUBLE NULL,
    take_profit_price DOUBLE NULL,
    event_types JSON NULL,
    schedule_enabled TINYINT(1) NOT NULL DEFAULT 0,
    schedule_time VARCHAR(5) NOT NULL DEFAULT '09:30',
    schedule_weekdays JSON NULL,
    last_schedule_key VARCHAR(32) NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_monitor_user_template_symbol (user_id, template_id, symbol),
    INDEX idx_strategy_monitor_enabled (enabled, last_checked_at),
    CONSTRAINT fk_strategy_monitor_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT fk_strategy_monitor_template FOREIGN KEY (template_id) REFERENCES templates(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS notification_events (
    id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    monitor_id INT NOT NULL,
    event_type VARCHAR(24) NOT NULL,
    symbol VARCHAR(32) NOT NULL,
    symbol_name VARCHAR(80) NOT NULL DEFAULT '',
    template_name VARCHAR(100) NOT NULL,
    timeframe VARCHAR(10) NOT NULL,
    bar_time BIGINT NOT NULL,
    price DOUBLE NOT NULL,
    title VARCHAR(160) NOT NULL,
    content VARCHAR(2000) NOT NULL,
    delivery_status JSON NOT NULL,
    is_read TINYINT(1) NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_monitor_event_bar (monitor_id, event_type, bar_time),
    INDEX idx_notification_event_user (user_id, is_read, created_at),
    CONSTRAINT fk_notification_event_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS screener_schedules (
    id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    template_id VARCHAR(64) NOT NULL,
    market VARCHAR(16) NOT NULL DEFAULT 'stock',
    universe_limit INT NOT NULL DEFAULT 50,
    min_progress INT NOT NULL DEFAULT 1,
    schedule_time VARCHAR(5) NOT NULL DEFAULT '01:00',
    schedule_weekdays JSON NULL,
    channel_ids JSON NULL,
    enabled TINYINT(1) NOT NULL DEFAULT 1,
    last_run_key VARCHAR(32) NULL,
    last_run_at DATETIME NULL,
    last_result_count INT NOT NULL DEFAULT 0,
    last_error VARCHAR(500) NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_screener_schedule_user_template_time (user_id, template_id, market, schedule_time),
    INDEX idx_screener_schedule_enabled (enabled, last_run_at),
    CONSTRAINT fk_screener_schedule_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    CONSTRAINT fk_screener_schedule_template FOREIGN KEY (template_id) REFERENCES templates(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
