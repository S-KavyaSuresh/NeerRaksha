# NeerRaksha

Dam Break & Flood Intelligence Platform.

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

## Simulation pipeline (dam-break flood)

The simulation lifecycle API is database-independent and works even when Neon is
unavailable:

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/api/simulations` | Create a run (`{scenario, engine}`), returns a `sim-…` id immediately |
| GET | `/api/simulations/{id}` | Status: `queued`/`running`/`completed`/`failed`/`cancelled` + progress |
| GET | `/api/simulations/{id}/summary` | Impact summary (population exposure is `null` + status, never fabricated) |
| GET | `/api/simulations/{id}/timeline` | Per-minute area/depth/velocity series |
| GET | `/api/simulations/{id}/timeline/{minute}` | Depth-banded flood GeoJSON for that minute |
| GET | `/api/simulations/{id}/results/{layer}` | `flood_extent` GeoJSON; `max_depth`/`max_velocity`/`arrival_time` GeoTIFF |
| GET | `/api/simulations/{id}/validation` | Sentinel-1 / GEE comparison — honest `unavailable` stub |

`engine` is `approximate` (default), `delft3d`, or `sph`:

- **approximate** — wraps `backend/simulation/ujjani_solver.py`. By default it serves
  the committed pre-computed products in `results/ujjani/<scenario>/`
  (MODEL OUTPUT, not validated). Set `NEERRAKSHA_RUN_LIVE_SOLVER=1` to run the
  solver live (needs `scipy` + a cropped DEM).
- **delft3d** — `backend/simulation/delft3d_engine.py` builds a small UGRID mesh
  from a DEM (`backend/simulation/dem_to_ugrid.py`), writes an `.mdu`, runs
  `dflowfm-cli.exe`, and post-processes the map file
  (`backend/simulation/postprocess.py`). If the executable or a DEM is missing it
  reports a clear error and the job falls back to the approximate engine.
- **sph** — `backend/simulation/sph_engine.py`, a demonstration-scale particle
  router (not a validated SPH solver). Kept separate from Delft3D output.

Configurable via environment variables (all optional):
`DELFT3D_EXECUTABLE`, `DELFT3D_REFERENCE_MESH`, `NEERRAKSHA_DEM`,
`NEERRAKSHA_SYNTHETIC_DEM`, `NEERRAKSHA_RESULTS_ROOT`, `NEERRAKSHA_SIM_WORKDIR`,
`NEERRAKSHA_RUN_LIVE_SOLVER`.

In the UI: **Simulation → Run Simulation** posts to `/api/simulations`, polls
status, then loads the flood timeline. Moving the timeline (0–60 min) updates the
Cesium flood layer frame-by-frame. If the API is unreachable the app degrades to
the local approximate preview.

Two of the three engines are genuine numerical solvers:

- **`sph`** — `backend/simulation/sph_solver.py` is a real 2D weakly-compressible
  SPH dam-break (Wendland C2 kernel, Tait EOS, Monaghan artificial viscosity,
  XSPH, CFL-limited symplectic integration, cell-linked-list neighbours; pure
  NumPy). `sph_engine.py` runs it and reconstructs the particle field onto a
  clearly-labelled demonstration footprint. `python -m simulation.sph_solver`
  runs it standalone.
- **`delft3d`** — real `dflowfm-cli.exe` with auto-generated discharge forcing on
  the proven Ujjani mesh (Phase 1).

A failed `sph` or `delft3d` run returns `status: failed` — never a silent
fallback to the approximate engine.

## Benchmark (verification, not validation)

`POST /api/benchmarks/run`, `GET /api/benchmarks/{id}`,
`GET /api/benchmarks/{id}/comparison` run an idealised dry-bed dam-break in **both**
the SPH solver and Delft3D D-Flow FM (flat frictionless channel, `initialwaterlevel`
polygon IC) and compare each — and each other — against the **Ritter (1892)**
analytical shallow-water solution (`x_f(t) = x0 + 2·√(g·H0)·t`). No experimental
reference values are used. Metrics: front-position RMSE/MAE/relative-error, depth-
profile RMSE at a reference time, wet-region 1D IoU (threshold + grid stated), and
front arrival time at a gauge. Artifacts land in
`results/benchmark/{metadata.json, sph/, delft3d/, comparison/{comparison,metrics}.json}`.
Frontend: the **Benchmark** workspace page. This is VERIFICATION / BENCHMARKING —
**calibration and validation are explicitly NOT performed**, and no real-world
accuracy is claimed.

## Ujjani dam-break scenario (generalized, engine-independent)

**Objective:** a physically-located breach at the actual Ujjani Dam
(`18.0739 N, 75.1200 E` → EPSG:32643 `≈ 512698, 1998366`) on the real 30 m DEM,
replacing the Phase-1 mesh-edge release. One scenario schema
(`backend/simulation/scenario.py`) feeds all three engines:

```
scenario JSON  ->  validate + resolve (DEM sample at dam, domain check)
   ->  breach model (linear width+depth growth over formation time)
   ->  broad-crested weir hydrograph  Q(t) = Cw·b(t)·H(t)^1.5 , then Qpeak·exp(-(t-tf)/τ)
        Cw = (2/3)·Cd·√(2g/3) ;  cf. Fread (1988) DAMBRK / USBR (1988), simplified
        peak discharge is MODEL INPUT / DERIVED — NOT an observed Ujjani value
   ->  engine adapter
        · delft3d_scenario  : internal discharge SOURCE POINT at the dam (sorsin, sink
                              placed outside the mesh -> inflow only) on the real
                              Ujjani terrain mesh; postprocess -> GeoTIFF + GeoJSON
        · sph_scenario      : genuine Phase-2 WCSPH solver on a scenario-derived
                              REDUCED-RESOLUTION prototype (fixed 0.40 m model head;
                              scenario sets the column aspect ratio + runout).
                              NOT full-scale, NOT georeferenced — GeoJSON carries a
                              flagged demonstration affine placement at the dam.
        · approximate       : the existing demo engine, mapped from the same schema.
   ->  common result: depth / velocity / arrival / extent + full metadata
```

Every field is classified `REAL DATA` (DEM, dam coordinate, CRS) / `MODEL INPUT`
(breach width/depth/formation time, duration, Manning n) / `ASSUMPTION / DEMO`
(reservoir level, assumed head, recession time, weir Cd) / `MODEL OUTPUT`. There
are **no observations**. `validation_status` is always `NOT PERFORMED`; the run
class is `MODEL DEMONSTRATION / SCENARIO SIMULATION`.

API (async, own job runner; no silent fallback):
`GET /api/scenarios/presets`, `POST /api/scenarios/run`,
`GET /api/scenarios/{id}`, `/{id}/results`, `/{id}/hydrograph`,
`/{id}/timeline/{minute}`, `/{id}/layers/{layer}`.
Frontend: the **Ujjani Dam-Break** workspace page (engine + preset + breach
inputs, hydrograph chart, dam location, assumptions, limitations; flood frames
feed the existing Cesium layer + timeline).

Presets (DEMO / ASSUMED numeric values — not historical events):

| preset | breach width | breach depth | formation time | assumed head | Qpeak (medium DEM head) |
|---|---|---|---|---|---|
| small_breach | 60 m | 6 m | 3600 s | 10 m | ≈ 1 500 m³/s |
| medium_breach | 150 m | 12 m | 1800 s | 15 m | ≈ 10 600 m³/s |
| large_rapid_breach | 250 m | 25 m | 600 s | 25 m | ≈ 53 000 m³/s |

Phase-1 Delft3D Ujjani, Phase-2 SPH, and Phase-3 benchmark paths are unchanged.

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
