# AGENTS.md — udpxy-scanner

## Project overview

Full-stack IPTV/udpxy multicast source scanner: discovers, validates, and manages live UDP multicast streams.

- **Backend** (`server/`): FastAPI + SQLite + aiohttp. Scans hosts via udpxy HTTP proxy, validates streams, enriches with GeoIP (ip2region).
- **Frontend** (`web/`): Vue 3 + Vite + Pinia. SPA served by nginx in production.
- **CI scanners** (`.github/scripts/`): Python scripts triggered by `repository_dispatch` from external services (ZoomEye, GitHub Code Search) that push discovered hosts back to the backend.

## Architecture

### Backend (`server/`)

| Directory | Purpose |
|-----------|---------|
| `main.py` | FastAPI app entrypoint, CORS, auth middleware, router registration |
| `routers/` | API route modules: `auth`, `settings`, `configs`, `iptv`, `cron`, `subscriptions` |
| `services/` | Business logic: `validator` (stream probing), `geoip`, `source_cache`, `subscription_fetcher`, `cron_heartbeat`, `log_buffer` |
| `core/` | Scan engine (`engine.py` — background threading + asyncio), task runner status (`status.py`) |
| `db/` | SQLite schemas + connection managers (`database.py`), Pydantic models (`models.py`) |

Three separate SQLite databases (WAL mode):
- `udpxy_scanner.db` — settings, scan configs, sessions, subscriptions
- `source_cache.db` — cached host lists per source type + geo data
- `iptv_list.db` — validated live sources (the "活源池")

Database paths are configurable via env vars: `DB_PATH`, `CACHE_DB_PATH`, `IPTV_DB_PATH`.

### Auth model

- Password-based login → in-memory session tokens (not JWT).
- Sessions stored in `routers/auth._sessions` dict (7-day TTL).
- Auth middleware in `main.py` exempts these paths: `/api/login`, `/api/logout`, `/api/source/push`, `/api/cron/heartbeat`, `/api/source-cache/list`.
- Default password: `admin` (override via `UDPXY_SCANNER_PASSWORD` env var).

### Scan engine flow

1. `trigger_background_queue()` spawns a daemon thread running `execute_scan_queue()`.
2. Engine reads subscription hosts from `source_cache`, deduplicates against `iptv_list`.
3. Concurrent validation via `aiohttp` (configurable concurrency, default 64).
4. Valid hosts → GeoIP enrichment → batch upsert into `iptv_list`.
5. SQLite writes serialized via `threading.Lock` (`_db_write_lock`) to prevent "database is locked".
6. Supports runtime queue append (`enqueue_background_queue`) and stop/resume.

### External push API

`POST /api/source/push` accepts JSON with `{ sourceType, sourceName, hosts: [{host}] }` — this is the endpoint CI scripts call back into.

## Frontend (`web/`)

- Dev: `cd web && npm run dev` (Vite dev server on :5173, proxies `/api` → `http://localhost:7860`)
- Build: `cd web && npm run build` (outputs to `web/dist/`)
- Lint: `cd web && npm run lint` (ESLint with Vue + Prettier config)
- Node version: `^20.19.0 || >=22.12.0`

## Docker / Compose

```bash
docker compose up --build
# backend → :7860, frontend → :8080
```

- Backend: Python 3.11-slim, uvicorn on port 7860. Downloads ip2region xdb on build.
- Frontend: Node 20 build stage → nginx:alpine. `VITE_API_BASE` build arg (default `/api`). nginx proxies `/api/` → `backend:7860`.
- Data volume: `./data:/app/data` (holds all 3 SQLite DBs).

## CI / GitHub Actions

- **`trigger_zoomeye`** → `.github/workflows/zoomeye.yml` → `.github/scripts/zoomeye.py`: Playwright-based ZoomEye scraper, pushes hosts to backend.
- **`trigger_github`** → `.github/workflows/gihub.yml` → `.github/scripts/github.py`: GitHub Code Search scanner, pushes hosts to backend.
- **`hf-sync.yml`**: Auto-syncs `server/` to HuggingFace Spaces on push to `server/**`.
- All workflows require `env` environment with secrets: `PUSH_CALLBACK_URL`, `PUSH_API_KEY`, `MY_GITHUB_TOKEN`, `HF_TOKEN`, `HF_SPACE_ID`.

## Key conventions

- Backend timezone forced to `Asia/Shanghai` at app startup (`main.py`).
- SQLite connections use `contextmanager` pattern (`get_db()`, `get_cache_db()`, `get_iptv_db()`), auto-commit on success, rollback on exception.
- Push payload format: `{ sourceType, sourceName, hosts: [{host}] }` — no `traceId` field.
- Vue alias: `@` → `src/`.
