# Repository Guidelines

## Commands

```bash
# Install dependencies (Python 3.10+)
pip install -r requirements.txt
playwright install chromium          # only required for non-fast (browser) mode

# Run the Web UI (default: http://127.0.0.1:8080)
python web.py

# Run the CLI automator (reads ./config.yaml; copy config.yaml.example first)
python clash_automator.py
```

There is no test suite, linter, or build step configured in this repo.

The Web UI writes generated configs into `./exports/` (served at `/exports/*`). The CLI writes `<original>_checked.yaml` into the project root. Both directories are git-ignored via `*.yaml` / `*_checked.yaml` rules.

## Architecture

There are **two entry points sharing the same core**:

- `clash_automator.py` — CLI: reads `config.yaml`, loads the target Clash YAML from `yaml_path`, iterates every proxy, writes `<name>_checked.yaml`.
- `web.py` — FastAPI app. The YAML is pasted into the browser (not read from disk), results stream back over SSE, and the user selects a subset to export. Mounts `routers/views.py` (Jinja2 `templates/index.html`) and `routers/api.py` (all `/api/*` endpoints).

Both entry points drive the same pipeline: **Clash External Controller (HTTP API) → switch proxy → probe current IP through that proxy → annotate node name**.

### Layered modules

- `core/clash_api.py` — `ClashController`: thin async wrapper over Clash's REST API (`PUT /proxies/{selector}`, `PATCH /configs`, `GET /configs` for port discovery). The checker forces `mode=global` before iterating so selector switches actually route traffic.
- `core/ip_checker.py` — `IPChecker`: orchestrator. Owns an in-memory `cache: {ip: result}`, a lightweight `get_simple_ip()` helper (ipify / ident.me) used as a cache key, and two public methods:
  - `check_fast(proxy, source, fallback)` — wrapped in a 15s `asyncio.wait_for`; tries the chosen source, then the other if `fallback=True`.
  - `check_browser(proxy)` — Playwright-based, only accepts cache entries that contain `bot_score` (i.e. produced by the browser source, not the fast sources).
- `core/sources/` — strategy pattern. `BaseCheckSource` defines `check()` + shared `get_emoji()` thresholds (⚪≤10, 🟢≤30, 🟡≤50, 🟠≤70, 🔴≤90, ⚫ otherwise). Implementations:
  - `ping0.py` — scrapes ping0.cc via `curl_cffi` with `impersonate="chrome124"`; detects Cloudflare challenge HTML and returns `None` to trigger fallback. Produces `shared_users` (not bot_score).
  - `ippure.py` — ippure.com API.
  - `browser.py` — Playwright render of ippure.com; the only source that yields `bot_score`.
- `state.py` — `AppState` global singleton (`state`) holding the singleton `IPChecker`, the running task id, the progress counter, and an append-only `events: List[Dict]` queue consumed by the SSE generator. The web layer is stateful-by-process — do not run multiple workers.
- `routers/api.py` — REST + SSE. `POST /api/start` kicks off `asyncio.create_task(_run_check(...))`, `GET /api/progress` tails `state.events`, `POST /api/nodes/{id}/recheck` reruns a single node, `POST /api/export` rewrites the original YAML (deep-copied) with selected/renamed proxies and rewires `proxy-groups` using a name-map.
- `schemas.py` — Pydantic request bodies. Frontend sends the full runtime config in `request.config` (not `config.yaml`) — the Web path never reads the YAML config file.

### Result shape (contract between sources → checker → router → frontend)

Every source returns a dict with at least: `ip`, `pure_score`, `pure_emoji`, `ip_attr`, `ip_src`, `full_string`, `source`. `ping0` adds `shared_users`/`shared_emoji`; `browser` adds `bot_score`. `full_string` is the `【...】` suffix appended to the proxy name — all annotation logic lives in the sources, not the router.

### Config: two worlds

- **CLI path**: `utils/config_loader.load_config("config.yaml")` at module import time in `clash_automator.py`. Keys become module-level constants (`FAST_MODE`, `SOURCE`, `FALLBACK`, etc.).
- **Web path**: config arrives per-request in `StartRequest.config` / `RecheckRequest.config`. Every handler calls `state.checker.headless = headless` to re-sync the toggle before each run. `config.yaml` is **not** read by `web.py`.

If you add a new config key, update `config.yaml.example` and both paths (CLI constants + web handlers). The frontend (`static/js/app.js`) also needs to send the key in its config payload.

### Caching & cleanup

- `IPChecker.cache` is keyed by IP string; it's cleared on completion/error of a web run (`state.checker.clear_cache()`) and also on shutdown via the FastAPI `lifespan` calling `state.checker.stop()`.
- Browser results are only cache-hits for other browser-mode calls (the `"bot_score" in cached` guard in `check_browser`); fast-mode results are always reusable.

### Name-mapping on export

`routers/api.py` `export_yaml` deep-copies `state.original_yaml`, substitutes the proxies list with `{original_name → new_name}` pairs from selected nodes, then walks every `proxy-groups[*].proxies` list replacing old names and dropping names that belong to deselected nodes while preserving literals like `DIRECT`/`REJECT`. Any change to how nodes are renamed must keep this round-trip intact.
