# JalDrishti

Dam Break & Flood Intelligence Platform — SIH Milestone 1.

A local React/Vite command center with CesiumJS, a FastAPI read API, and a Neon-ready PostgreSQL schema. This repository is the `jaldrishti/` project root; no second nested project folder is needed.

## Requirements

- Node.js 20.19+ or 22.12+ and npm
- Native Windows Python 3.10+ with pip and venv (prefer 3.12)
- Internet access for map imagery; a WebGL-capable browser with hardware acceleration
- Neon PostgreSQL and a Cesium ion token for database-backed data and World Terrain, respectively

## Windows PowerShell setup

Run from `C:\Users\kavya\JalDrishti`.

```powershell
Set-Location C:\Users\kavya\JalDrishti\frontend
npm install
Copy-Item .env.example .env
```

Set `VITE_CESIUM_ION_TOKEN` in `frontend/.env` to your Cesium ion token. Leave it empty to use flat terrain and public Esri satellite imagery. `VITE_API_BASE_URL=http://localhost:8000` points to FastAPI. Vite embeds frontend environment values into public JavaScript: use a browser-scoped Cesium token with appropriate origin restrictions. Restart Vite after changing `.env`.

```powershell
Set-Location C:\Users\kavya\JalDrishti\backend
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

If the Python launcher has no registered Python 3.12, use an installed native Windows Python executable. On the current machine the working executable is:

```powershell
& "$env:LOCALAPPDATA\Programs\Python\Python310\python.exe" -m venv .venv
```

The shell's bare `python` may resolve to MSYS2 and create `bin/` instead of `Scripts/`; use the native executable above. Virtual environment activation is optional because the commands use its interpreter directly.

## Neon and initial data

Create a Neon database and copy its PostgreSQL connection string into `backend/.env`:

```dotenv
DATABASE_URL=postgresql://USER:PASSWORD@YOUR-NEON-HOST/DATABASE?sslmode=require
FRONTEND_ORIGIN=http://localhost:5173
FRONTEND_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
```

These are placeholders. Never put the database URL in frontend files. The backend converts PostgreSQL URLs to the SQLAlchemy psycopg driver and keeps connection errors free of credentials. Use Neon's direct connection URL for migrations. Then run:

```powershell
Set-Location C:\Users\kavya\JalDrishti\backend
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m app.services.seed
```

The seed is idempotent: it inserts Hirakud Dam, partial and major breach scenarios, a completed prototype run, and its impact summary without overwriting existing records. The sample run references `data/sample/timeline.json`; its four API frames are defined in `app/services/sample.py`. No generic timeline persistence or hydraulic solver is included in Milestone 1.

## Run the application

Terminal 1:

```powershell
Set-Location C:\Users\kavya\JalDrishti\backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Terminal 2:

```powershell
Set-Location C:\Users\kavya\JalDrishti\frontend
npm run dev -- --port 5173 --strictPort
```

Open http://localhost:5173 or http://127.0.0.1:5173. API docs: http://localhost:8000/docs. Both development origins are allowed by default, including CORS headers on structured database errors. `FRONTEND_ORIGINS` accepts a comma-separated list, and the legacy `FRONTEND_ORIGIN` is also honored. Credentials are disabled and wildcard origins are excluded. Restart FastAPI after configuration changes.

FastAPI starts without a database. `/api/health` remains available; database routes return structured HTTP 503 errors. The frontend then shows clearly labeled local demo data and a retry control. A working API still serves prototype sample values, not live flood intelligence.

## Validation

```powershell
Set-Location C:\Users\kavya\JalDrishti\frontend
npm run build
npm test
npm run preview -- --port 4173
```

```powershell
Set-Location C:\Users\kavya\JalDrishti\backend
.\.venv\Scripts\python.exe -c "from app.main import app; from app.models import Dam, Scenario, SimulationRun, ImpactSummary; print(app.title)"
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m alembic upgrade head --sql
```

Tests exercise missing and unreachable database errors, seed idempotency, all read endpoints, response shapes, 404/422 behavior, and CORS. Successful database routes use an isolated in-memory SQLite test database; this does not replace verifying migrations and seeding against your Neon instance. No real Neon connection can be verified until credentials are supplied.

The frontend tests cover token normalization, nested frame selection, replay controls, inventory counts, asset threats, emergency layer restoration, scenario validation/persistence, pipeline cancellation/completion, comparison data, impact reconciliation and export generation. Cesium 1.129 is paired with Resium 1.19.0 and ZIP 2.7.57 to avoid incompatible newer transitive exports; retain the npm lockfile. Cesium's dedicated bundle is large and Vite reports a non-blocking size warning.

Additional verification commands, from `frontend/`:

```powershell
node scripts/check-ion.mjs
node scripts/verify-render.mjs
node scripts/write-export-fixtures.mjs
..\backend\.venv\Scripts\python.exe ..\backend\tests\verify_export_files.py
```

The ion check reads Vite's development environment, normalizes wrapping quotes/whitespace, and verifies the terrain endpoint. It prints only `tokenConfigured` and `tokenFormatValid`; exit code zero also confirms the endpoint returned terrain metadata. It never prints the token or endpoint credentials. The file checks generate 16 files under the ignored `data/exports/verification/` directory, then parse JSON, CSV, GeoJSON and KML with independent Python parsers. Server rendering checks component output; it is not browser interaction testing.

See `VALIDATION.md` for the exact change manifest, observed results, and remaining manual browser checks. The optional WebMCP replay tool remains feature-detected and unverified in a supported browser context.

## Project map

```text
frontend/src/
  components/common/       Accessible controls and map error boundary
  components/dashboard/    Intelligence panel and depth chart
  components/map/          Cesium globe, layers, markers and popovers
  components/simulation/   Shared simulation playback timeline
  layouts/                 Command bar and collapsible navigation
  pages/                   Scenario, simulation, comparison, impact, exports
  services/                Central Axios client and API fallback lifecycle
  store/                   Zustand playback, layers and interface state
  styles/                  Plain CSS design tokens and responsive layouts
  utils/                   Formatting and downloads
  data/                    Clearly labeled frontend sample data
backend/app/
  api/ core/ database/ models/ schemas/ services/
backend/alembic/            Initial PostgreSQL migration
data/sample/               Versioned prototype timeline
data/raw/ processed/ exports/  Ignored GIS and simulation work directories
```

Routes: `/overview`, `/scenario`, `/simulation`, `/comparison`, `/impact`, `/exports`; `/` redirects to overview. Scenario Studio provides Partial Breach, Major Breach and Custom presets, field validation, local saving and a Continue to Simulation action. Simulation stages sample preparation, explicitly skips HEC-RAS, supports cancel/reset and starts playback when complete. Comparison provides six predefined partial/major breach metrics with a selectable chart. Impact Analysis links estimates and clickable asset states to the active frame. Export Center generates JSON, CSV, GeoJSON and KML with scenario/frame/time/source/validation metadata.

All nine requested API routes are available under `/api`; the seeded simulation ID is `44444444-4444-4444-8444-444444444444`.

Cesium workers, widgets, assets and third-party files are copied into `dist/cesium` during the Vite build. Ion is configured centrally before providers are created. Terrain failures fall back to ellipsoid terrain and a non-blocking warning. Satellite toggles the imagery layer, with OpenStreetMap as the street basemap. Flood boundaries are separate ground-clamped polylines, avoiding unsupported terrain polygon outlines. The original Hirakud camera destination/orientation is preserved. No ion buildings dependency is needed: 24 buildings, five road segments, six facilities, the river and flood states are illustrative sample geometry. Layer counts reflect enabled entities, not camera-frustum visibility. Sample buildings and road intersections are checked against the active prototype ring; this is not real GIS exposure analysis.

Playback advances one simulated minute per real second at 1× and retains position when speed changes. One active nested flood state is selected at T+00, T+15, T+30 or T+60; T+00 has no downstream inundation. The same frame drives geometry, asset threat state, impact cards, sector/risk breakdowns and exports. Playback stops at 60 and Restart returns to zero. Hiding flood does not stop playback.

Emergency Mode opens a keyboard-focusable briefing with three timeline-linked prototype alerts, road/facility threats, sample arrival countdowns and shelter references. It enables all risk layers and focuses the current extent. Exit (or Escape within the briefing) restores the previous layer visibility. All content is explicitly unofficial prototype intelligence.

Saved scenarios use `localStorage` under `jaldrishti.prototype-scenario`, with a session-state fallback when storage is unavailable. Browser storage is separate for `localhost` and `127.0.0.1`. Scenario saving does not write to Neon: the backend read API and database schema are preserved. Custom parameters and durations of 60–180 minutes are saved assumptions; all runs replay the same first-hour sample geometry, without calculating hydraulic effects from inputs. Comparison metrics are independent predefined sample estimates and are labeled separately from the illustrative map-asset inventory.

This is an interface and data foundation, not a validated dam-break forecast. There are no live warning feeds, hydraulic calculations, operational dispatch actions, authentication, or production deployment in this milestone.
