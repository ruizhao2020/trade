# 登录与权限

系统采用 Token + RBAC：用户关联角色，角色关联权限点，模块的显示和接口访问均由权限点决定。

## Token

登录或注册返回 Bearer Token。后续 HTTP 请求使用：

```text
Authorization: Bearer <token>
```

WebSocket 使用：

```text
/ws?token=<token>
```

登录用户可调用 `PUT /api/v1/auth/password` 修改自己的密码，服务端会先校验当前密码。

生产部署必须设置不同的 `SIGNAL_TOKEN_SECRET`，并修改初始化管理员密码：

```text
SIGNAL_TOKEN_SECRET=<高强度随机值>
SIGNAL_BOOTSTRAP_ADMIN_USERNAME=admin
SIGNAL_BOOTSTRAP_ADMIN_PASSWORD=<高强度密码>
```

开发环境首次启动的管理员为 `admin / Admin123!`。

## 配置驱动模块

`modules` 表控制左侧导航：

- `code`：模块唯一编码，对应 `{code}.view` 权限。
- `name`、`icon`、`sort_order`：名称、图标和顺序。
- `component_key`：已有前端页面组件的注册键。
- `api_prefixes`：逗号分隔的 API 前缀；统一中间件自动检查 `{code}.view`。
- `api_permission`：模块 API 的准入权限，默认 `{code}.view`，共享服务可以配置为公共权限点。
- `enabled`、`visible`：是否启用、是否显示。

通过系统管理页面添加模块时会自动创建 `{code}.view` 权限，无需修改权限控制代码。新业务页面仍需实现自身组件；可以复用已有 `component_key`，或在页面实现后配置新的注册键。

## 接口权限

- 行情：`market.read`
- 公共分析能力：`analysis.compute`
- 指标模块：`indicators.view/calculate`
- 策略：`strategy.view/manage/evaluate/backtest`
- 选股：`screener.view/run`
- 系统管理：`admin.view/users/roles/modules`

接口权限由服务端依赖统一校验。隐藏左侧图标只是交互层，不能替代后端权限检查。
