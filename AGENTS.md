# AGENTS.md

Monorepo with two apps (a stock/futures trading-signal platform) plus supporting dirs.

## Layout

- `signal-layer/` — React 19 + Vite 8 + TypeScript + Tailwind CSS v4 frontend. ONE codebase, TWO entrypoints.
- `signal-layer-server/` — Python 3.12 FastAPI backend (Poetry; MySQL + Redis + akshare).
- `deploy/k8s/` — Kubernetes manifests for the dual-entry frontend build.
- `pinescript/` — a single Pine Script reference indicator (not built here).
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
- Services init in `app/api/deps.py::init_services()` (lifespan). Redis optional (degrades to no-op cache); MySQL init failure logs a warning and falls back to SQLite.
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

- Code comments/docstrings are largely in Chinese — keep consistent when editing.
- Backend routers in `app/api/*.py`, registered in `app/api/router.py` under `/api/v1`.
- Frontend API modules mirror backend routes in `src/api/*.ts`.
- `.env` is gitignored; `.env.example` is the template. Commit messages are terse (the existing history is mostly one-word messages).
