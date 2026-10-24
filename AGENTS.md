# AGENTS.md

Monorepo with two apps (a stock/futures trading-signal platform) plus supporting dirs.

## Layout

- `signal-layer/` — React 19 + Vite 8 + TypeScript + Tailwind CSS v4 frontend. ONE codebase, TWO entrypoints.
- `signal-layer-server/` — Python 3.12 FastAPI backend (Poetry; MySQL + Redis + akshare).
- `deploy/k8s/` — Kubernetes manifests for the dual-entry frontend build.
- `deploy/ecs/` — single-server Docker Compose deploy (nginx + FastAPI + MySQL + Redis + certbot) serving two hostnames: public site and private site. See `deploy/ecs/README.md`. Its two Dockerfiles use the REPO ROOT as build context (so the root `.dockerignore` applies); the frontend build in `signal-layer/Dockerfile` uses the `signal-layer/` subdir as context.
- `pinescript/` — a single Pine Script reference indicator (not built here).
- `articles/` — 对外的指标科普文章（`<slug>.md`）与配图（`images/`，统一尺寸、按图一/图二编号）。写作约定与配图方法论见 `articles/README.md`。
- `.agents/skills/indicator-article/` — 项目级 skill：写指标科普文章 + 从真实图表导配图 + 程序化校验的完整流程（含 `scripts/find_window.py`）。写/改这类文章时先读它。
- `public/` (repo ROOT) — `real_data.json` sample data. Do NOT confuse with the frontend's `signal-layer/public/` (favicon/icons). Two different `public/` dirs.
- `signal-layer-server/data/` — gitignored runtime data (SQLite dev DB, backups).

## Frontend — `signal-layer/`

Two builds share all indicators/chart/API code, switched by Vite `--mode` (not file path):
- `public` mode → `src/public-main.tsx` → `src/public/PublicApp.tsx` (no auth / no private modules)
- `private` mode → `src/private-main.tsx` → `src/App.tsx` (login + full workspace)

`vite.config.ts` swaps the entry by rewriting `/src/main.tsx` in `index.html` when `mode === 'public'` (that file does NOT exist — never create it; mode selects the entry). `src/surface.ts` sets `<html data-signal-surface>`. Public/private visibility is enforced server-side too — URL obscurity is not a security boundary.

Commands (run inside `signal-layer/`):
- `npm run dev:public -- --host 127.0.0.1 --port 4174`
- `npm run dev:private -- --host 127.0.0.1 --port 4175`
- `npm run build:public` → `dist-public`; `npm run build:private` → `dist-private`
- `npm run lint` (eslint flat config `eslint.config.js`)
- `npm test` / `npm run test:watch` (vitest, `happy-dom`, setup `src/testing/setup.ts`)

- Path alias `@` → `/src` (vite + tsconfig).
- API client: `src/api/client.ts` (singleton `api`). Base = `import.meta.env.VITE_API_BASE ?? 'http://localhost:8000/api/v1'`. There is NO frontend `.env` — `VITE_API_BASE` is injected at Docker build time (`--build-arg VITE_API_BASE=...`). Dev proxy forwards `/api` → `http://localhost:8000`.
- Auth token lives in `localStorage` key `signal_layer_access_token`, sent as `Authorization: Bearer`. Every request also sends `X-Signal-Surface: public|private`. On 401 (non-auth path) the client clears the token and dispatches `signal-layer:unauthorized`.
- Tests are colocated `*.test.ts(x)` next to source.

TypeScript gotchas (`tsconfig.app.json`): `verbatimModuleSyntax` (must use `import type` for type-only imports) and `erasableSyntaxOnly` (no TS enums / namespaces / parameter properties).

## Backend — `signal-layer-server/`

- Poetry, Python 3.12. Config via pydantic-settings, env prefix `SIGNAL_`, loaded from `.env` (keys in `.env.example`).
- Run: `uvicorn app.main:app --host 0.0.0.0 --port 8000` (from `signal-layer-server/`). Swagger `/docs`, health `/health`.
- Services init in `app/api/deps.py::init_services()` (lifespan). Redis optional (degrades to no-op cache). MySQL init failure does NOT switch to SQLite (`_get_db_url()` always returns the configured MySQL URL): it only logs a warning and keeps starting, so `/health` stays 200 while every DB-backed endpoint returns 500. Deploys must verify a data endpoint, not just `/health`.
- Tests: `poetry run pytest` (`asyncio_mode=auto`, `testpaths=tests`). Single: `poetry run pytest tests/test_engine/test_duan.py`. Tests use fixtures/monkeypatch + in-memory SQLite — NO live MySQL/Redis required.
- Dev admin login: `admin / Admin123!` (override in prod via `SIGNAL_BOOTSTRAP_ADMIN_PASSWORD`).

### Database schema — CRITICAL gotcha

Schema is NOT managed by Alembic (`alembic/versions/` is EMPTY; `alembic.ini` has a hardcoded URL, and `alembic/env.py` imports only `kline`/`template`/`auth` models — `notification`/`content` would be missed by autogenerate). Changes land in two places:
1. Fixed app tables: `database/mysql/*.sql` (MySQL, auto-run on `docker compose up`) and `database/sqlite/*.sql` (tests + migration). Seed: `010_access_control_seed.sql`.
2. At startup, `init_db()` (`app/db/__init__.py`) runs `Base.metadata.create_all` PLUS `_ensure_compat_columns`, which ALTERs old tables to add missing columns.

When you add a model column, update BOTH the SQL schema files AND `_ensure_compat_columns` so fresh installs and existing DBs both work.

Dynamic market-data tables (`{symbol}_{timeframe}`, e.g. `000001_sz_日线`, plus `_market_data_coverage`) are created at runtime by `MySQLMarketDataStore`, never in schema scripts. `tests/test_database/test_schema_files.py` asserts dynamic tables stay out of saved SQL.

### Market data pipeline

`MarketDataManager` (`app/market_data/manager.py`) is the ONLY K-line read path — indicators, Chan (缠论), backtest all go through `DataService`. Flow: read dynamic MySQL table → check `_market_data_coverage` → fetch only missing ranges from external adapters (`app/adapters/`: akshare, baostock, binance, futures) → write → merge. Coverage metadata distinguishes weekends/holidays from "not yet fetched".

### Auth & permissions

Token + RBAC (see `docs/AUTHORIZATION.md`). HTTP `Authorization: Bearer <token>`; WebSocket `/ws?token=<token>`. Left-nav is config-driven from the `modules` table; `ModuleAccessMiddleware` enforces `{code}.view` per module via `api_prefixes`. Adding a module auto-creates its `{code}.view` permission — no permission-code edits needed.

## Conventions

Standing rules from the user — apply them to every change unless told otherwise:

- **Do not touch ECS deployment as part of feature work.** The user deploys himself. `deploy/ecs/` stays as reference; don't add deployment steps, notes, or image/build changes to feature changes.
- **Do not expose changes on the public site by default.** Public visibility is data-driven (`public_indicator_policies` / `public_indicator_feature_policies` seeds). Don't add public policy rows or public-surface content for a new indicator/module unless the user asks for it explicitly.
- **只改代码，不改文档——除非用户明确要求。** "文档"指 `articles/` 下的指标文章与配图，以及 README/说明类 markdown。
  指标文档的更新由用户发起；代码改了而文档没跟上时，在交付说明里写一句"文档未同步"即可，不要顺手改。
  代码注释与 docstring 属于代码，照常维护。

- Code comments/docstrings are largely in Chinese — keep consistent when editing.
- Backend routers in `app/api/*.py`, registered in `app/api/router.py` under `/api/v1`.
- Frontend API modules mirror backend routes in `src/api/*.ts`.
- `.env` is gitignored; `.env.example` is the template. Commit messages are terse (the existing history is mostly one-word messages).

### UI 交互约定

- **弹窗一律挂在指标文字上，不挂在整根 K 线或图表空白处。** 点击标记文字弹出说明；
  点空白或普通 K 线不弹窗（避免误触）。
- **带弹窗的指标文字统一用中括号包起来**，与普通文字区分：`[放量冲高回落]`、`[底背驰]`、`[一买]`。
  中括号只加在**可点击**的文字上；弹窗内部的标题不加。
- 实现方式：给标记写入 `id`（形如 `form:<指标>:<字段>:<秒级时间>`），通过
  `MarkerDetailProvider.getMarkerDetail(id)` 找回详情，复用 `IndicatorMarkerPopover`；
  中括号由前端在渲染标记时按"该标记是否有弹窗内容"统一添加，**不要写死在各指标里**。

