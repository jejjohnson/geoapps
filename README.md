# geoapps

Four apps on one platform for events that intermittent remote sensing can extract: trace-gas plumes, oil spills, floods, heavy rain and tropical cyclones. Methane plumes are the running example.

| App | What it is for |
|---|---|
| 1. Labeling and validation | A person has the final say on every predicted plume. Nothing unvalidated goes downstream. |
| 2. Attribution | A validated detection reaches a source, facility, asset, operator and government, each link valid over a time window. |
| 3. Watchlists and alerts | Watch an area, a site or a kind; validated events raise alerts; dismissals become labels. Outbound notifications come later. |
| 4. Analysis and research | Every layer, what-if reruns in a sandbox, model comparison and promotion, the catalog explorer and notebook client. |

geoapps is an app, not a dataset. Each instance brings its own data, public or private, its own storage and its own compute. One person on a laptop and a small team run the same code with different configuration, with Postgres in both cases.

The design lives in [`docs/design`](docs/design):

- [`01-design-plan.md`](docs/design/01-design-plan.md): the four apps, ownership rules, the running example in eight stages, data placement, the stack, and workstreams A to M with their gates.
- [`02-end-to-end-pipeline.md`](docs/design/02-end-to-end-pipeline.md): one plume from scene to alert in 14 steps, and how the other event kinds fit the same pipeline.

## What is here: the walking skeleton

This is the thinnest version of the whole loop, end to end: a predicted plume lands, an analyst confirms or rejects it, a confirmed plume on a watched area raises an alert, the watcher keeps or dismisses it, and any registered ETL can be submitted as a job from the browser.

```
packages/
  geoapps-core      science and rules with no I/O: priority, persistence, attribution weights,
                    IoU carry-over, the event-kind registry, instance config
  geoapps-db        the only code that writes to Postgres: SQLAlchemy 2 + GeoAlchemy2 models,
                    Alembic migrations, and the repository functions every write goes through
  geoapps-workers   registered ETL steps with typed parameters, and a Postgres job queue
                    (FOR UPDATE SKIP LOCKED) the worker drains
  geoapps-api       FastAPI: validation queue, verdicts, watches, alerts, ETL jobs, catalog search
web/                React + TypeScript + Vite + MapLibre shell; types generated from the OpenAPI schema
docs/design/        the design documents
compose.local.yml   PostGIS, migrations, api, worker, titiler and web on one machine
```

Not built yet, in the order the design plan's roadmap takes them: drawing a redraw on the map, attribution (app 2), the ingest half of the explorer, pgSTAC and Zarr through titiler.xarray, the notebook client, GeoParquet exports, scheduled pipelines, outbound notifications and auth.

## Quickstart with Docker

```bash
cp geoapps.toml.example geoapps.toml
docker compose -f compose.local.yml up --build
```

Then open http://localhost:5173, go to **Jobs**, submit `seed_demo`, and the **Validate** tab fills with synthetic plumes around five made-up Permian well pads. The API docs are at http://localhost:8000/api/docs.

## Quickstart without Docker

You need [uv](https://docs.astral.sh/uv/), Node 20 or newer, and PostgreSQL with PostGIS 3.4.

```bash
uv sync
cp geoapps.toml.example geoapps.toml
export GEOAPPS_DATABASE_URL=postgresql+psycopg://geoapps:geoapps@localhost:5432/geoapps

uv run geoapps-db upgrade                              # create schemas and tables
uv run geoapps-worker sync                             # register the ETL steps
uv run geoapps-worker submit seed_demo '{"n": 12}'     # queue some synthetic plumes
uv run geoapps-worker run &                            # drain the queue
uv run geoapps-api &                                   # http://localhost:8000/api/docs

cd web && npm install && npm run dev                   # http://localhost:5173
```

Catalog previews need titiler on port 8001 (`docker compose -f compose.local.yml up titiler` runs just that).

### Bring your own detections

`import_detections` takes a GeoJSON FeatureCollection, from a path or URL, of polygons with `observed_at`, `q_kg_h`, `q_sigma_kg_h` and `p` in their properties. Every row lands as `predicted` and waits for a verdict.

```bash
uv run geoapps-worker submit import_detections '{"source": "my_plumes.geojson"}'
```

## Tests

The pure tests run anywhere. The database tests need a throwaway PostGIS database, because they drop and recreate the `core`, `ref`, `review` and `notify` schemas.

```bash
uv run pytest                                          # core only; database tests skip
GEOAPPS_TEST_DATABASE_URL=postgresql+psycopg://geoapps:geoapps@localhost:5432/geoapps_test uv run pytest
uv run ruff check packages && uv run ruff format --check packages
cd web && npm run build                                # typecheck and bundle
```

Tests are named after the design plan's gates, so a failing test points at the decision it protects:

| Gate | What the test checks |
|---|---|
| A1 | migrations upgrade from empty and downgrade cleanly |
| E1 | a label carries over to a reprocessed mask when IoU ≥ 0.5 |
| E4 | a rejected plume raises no alert; only a confirmed one reaches watches |
| E5 | priority decays by e⁻¹ one λ past the window; window-closing plumes always alert |
| F1 | a source directly downwind of the plume scores zero |
| G3, H5 | overpasses needed to verify a repair; persistence posterior |
| H1 | invalid ETL parameters return 422 and create no job |
| K1 | resubmitting a job with the same key returns the same job |
| L2 | marks are validated against the event kind before a row exists |

## Changing the API

The web client's types come from the backend's OpenAPI schema, so a renamed field breaks `npm run build` rather than the page:

```bash
uv run geoapps-openapi web/openapi.json && (cd web && npm run gen:api)
```

## Changing the schema

```bash
uv run geoapps-db revision -m "add attribution links"  # autogenerate from the models
uv run geoapps-db upgrade
```
