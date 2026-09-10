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
