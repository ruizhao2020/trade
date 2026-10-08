# 契约测试用 fixture

这里的 JSON 是**真实后端响应报文**，供 `src/api/contract.test.ts` 使用。

## 为什么用真实报文

`src/api/*.ts` 里的类型和映射是手写的单向猜测：后端把 `open_time` 改名成 `openTime` 时，
映射会安静地返回 `undefined`，**TypeScript 不会报错**（它检查的是我们自己写的类型）。
拿真实报文当输入，后端一改字段名/改类型，契约测试立刻失败。

## 刷新方式

1. 启动后端（`./start-private.sh`），准备一个可用的 Bearer 令牌；
2. 按下面的清单重新抓取（注意参数约束，例如 `/chan` 的 `limit` 最小是 10）；
3. **抓完必须校验报文形状**：如果结果是 `{"detail": "..."}`，说明令牌过期或参数非法，
   这种"错误报文"当 fixture 会让契约测试假通过（曾经真的抓到过一次）。

| 文件 | 请求 |
| --- | --- |
| `auth-me.json` | `GET /api/v1/auth/me` |
| `templates.json` | `GET /api/v1/templates`。每个 `trade_params` 都带 `max_hold_bars`（后端把默认值也序列化出来），契约测试断言它映射到 `maxHoldBars`；把字段删掉应回退到 0（不限），这点也有用例守着 |
| `markets.json` | `GET /api/v1/symbols/markets` |
| `indicator-list.json` | `GET /api/v1/indicator/list` |
| `klines-v0-1d.json` | `GET /api/v1/klines/V0?timeframe=1d&limit=5` |
| `chan-v0-1d.json` | `GET /api/v1/chan/V0/1d?limit=10` |
| `indicator-calculate.json` | `POST /api/v1/indicator/calculate`，body 见下 |
| `signal-evaluate.json` | `POST /api/v1/signal/evaluate`，template 用 `templates.json` 里的建议模板（id 形如 `advisor_volume:*`） |
| `backtest-open-position.json` | `POST /api/v1/signal/backtest`，symbol `000002_sz`、template 取 `templates.json` 里的「布林通道策略」、`kline_limit` 500。它刻意覆盖「**0 笔已完成交易 + 1 笔持有中**」：那条策略只设了入场条件，止损止盈关闭、无出场条件、持仓上限不限，所以仓位从 2025-02-12 一直持到现在（浮动 -49%）。契约测试断言 `open_position` 映射成 `openPosition`，并守住"报文里没有这个字段时回退为 null" |
| `advisor-run-detail.json` | `GET /api/v1/advisor/runs/{id}`（**已裁剪**：只保留前 8 个候选，完整报文可达数百 KB） |

`indicator-calculate` 的请求体（刻意同时覆盖"样本不足/预热期"与"有值"两种情况，
以及"决策字段 + 渲染字段"两类输出）：

```json
{"symbol": "V0", "timeframe": "1d", "kline_limit": 60,
 "indicators": [{"type": "ma", "params": {"period": 260}},
                {"type": "ma", "params": {"period": 20}},
                {"type": "bollinger", "params": {"period": 20, "std": 2}},
                {"type": "rsi", "params": {"period": 14}},
                {"type": "macd", "params": {"fast": 12, "slow": 26, "signal": 9}},
                {"type": "kdj", "params": {"n": 9, "m1": 3, "m2": 3}},
                {"type": "support_resistance", "params": {}},
                {"type": "liquidity_zone", "params": {}},
                {"type": "liquidity_sweep", "params": {}}]}
```

**改动这份请求体时，必须同步更新上面的 README 与 `contract.test.ts` 里的断言。**
照着过期的文档重抓会让新指标从 fixture 里消失，契约测试随即失败。

指标引擎的输出契约是**逐根等长 + 预热期字段为 null**，这份报文把两边都覆盖住：

| 指标 | 预期形状 |
| --- | --- |
| `ma period=260` | 60 行全 `value: null`（60 根数据不够 260 根均线）；`support`/`resistance` 是 0/1 标志位，0 表示未触及 |
| `ma period=20` | 前 19 行 `null`，第 20 行起有值 |
| `bollinger` | 三轨同步 null / 有值 |
| `rsi period=14` | 前 14 行 `null`，下标 14 起有值 |
| `macd` | `dif` 自下标 25 起有值，`dea`/`histogram` 自下标 33 起有值 |
| `kdj` | 前 8 行 `null`，下标 8 起有值 |
| `support_resistance` | 决策字段（`nearest_support` 等）与渲染线 `level_1..level_6`；后者是"当前有效位"的快照，不在 outputs 白名单里 |
| `liquidity_sweep` | `render.plots` 为**空**、信号走 `render.markers`（挂在被扫价位上的 SSL/BSL SWEEP）；决策字段 `bull_signal`/`bear_signal`/`bull_level`/`bear_level`/`atr`。主图叠加折线的值必须是价格量级，这条由 `test_indicator_contract.py` 的护栏守住 |
| `liquidity_zone` | 决策字段（`nearest_zone_*`、`sweep_up/down` 等，只描述仍在聚集阶段的区）与**按槽位的方框字段** `zone_{k}_low/high/consumed/swept/swept_from_top`；`zone_{k}_*` 不在 outputs 白名单里，前端按这套命名约定还原方框 |

前端 `IndicatorRenderer` 对线/柱共用同一个 data 数组并过滤 null，
所以这些 null 行必须能被解析且不报错。

## 两个容易踩的点

- **`/indicator/list` 的 `render.plots` 对 `ma`/`macd` 是空的**（元数据没填，引擎里的
  `RenderSpec` 才有完整字段）。断言"每个指标都有 plots"会失败——这是数据现状，不是 bug。
- **请求缓存**（`recentMarketRequests`）按 `symbol:timeframe:limit` 复用同一个 promise，
  因此同一测试文件里对同一 key 的第二次调用不会发出请求。契约测试要避开重复 key。
