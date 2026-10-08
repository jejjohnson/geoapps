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
- [`03-data-model.md`](docs/design/03-data-model.md): datasets, detections, sources, events, facilities, assets and orgs, with validity ranges, provenance and the constraints the database enforces.

## What is here

The whole loop, end to end, on real public data: the Eye on Methane plumes are imported with their sources, sensors and licence; an analyst confirms or rejects each one; confirmed plumes chain into events at their source; a source can be attributed to a facility, and through it to an asset, an operator and a government, each valid over time; a confirmed plume on a watched area raises an alert, and a dismissal comes back as feedback.

```
packages/
  geoapps-core      science and rules with no I/O: priority, persistence, event chaining,
                    attribution weights, IoU carry-over, the event-kind registry, config
  geoapps-db        the only code that writes to Postgres: models and repository functions,
                    one module per schema (core, ref, review, attribution, monitor, notify),
                    and the Alembic migrations
  geoapps-workers   registered ETL steps with typed parameters, and a Postgres job queue
                    (FOR UPDATE SKIP LOCKED) the worker drains
  geoapps-api       FastAPI: queue, verdicts, sources, events, attribution, watches, alerts,
                    feedback, datasets, ETL jobs, catalog search
web/                React + TypeScript + Vite + MapLibre shell; types generated from the OpenAPI schema
docs/design/        the design documents
compose.local.yml   PostGIS, migrations, api, worker, titiler and web on one machine
```

Registered steps:

| Step | What it does |
|---|---|
| `import_mars_plumes` | Downloads the public [Eye on Methane](https://methanedata.unep.org/download-dataset) plume list (UNEP IMEO MARS, CC BY-NC-SA 4.0) as GeoJSON and imports it: one detection per plume with its outline as the geometry and the source point as its origin, one source per MARS source id, one sensor per satellite, with the dataset's checksum and licence. Self-intersecting outlines are repaired on the way in. The CSV download (points only) also works. Rerunning it skips unchanged files and updates revised plumes that nobody has reviewed yet. |
| `import_detections` | Your own detections from a GeoJSON FeatureCollection. |
| `seed_demo` | Synthetic plumes, for tests and offline trials only. |

Every imported plume is born `predicted`. MARS has already reviewed its public plumes, so `import_mars_plumes` takes `accept_provider_validation: true` to record that review as a label by `provider:unep-mars` instead of reviewing each plume yourself. Persistence is not computed from MARS: it lists plumes, not the clear looks that found nothing.

The MARS data is licensed for non-commercial use only, and anything derived from it must be shared under the same licence. The map shows the credit line for every dataset that contributed plumes.

The map has three basemaps: streets (OpenFreeMap), imagery (EOX Sentinel-2 cloudless) and an offline Natural Earth 1:10m map served by the app itself, with coasts, country and state lines, rivers, lakes, highways, urban areas and place names. If a remote basemap can't be reached, the map falls back to the offline one. `web/scripts/build-basemap.mjs` rebuilds the offline layers from Natural Earth (public domain) and Noto Sans glyphs (SIL OFL).

Not built yet, in the order the design plan's roadmap takes them: drawing a redraw on the map, a facility inventory import (attribution has nothing to propose until facilities exist), the ingest half of the explorer, pgSTAC and Zarr through titiler.xarray, monitoring pipelines that record observations, the notebook client, GeoParquet exports, scheduled pipelines, outbound notifications and auth.

## Quickstart with Docker

```bash
cp geoapps.toml.example geoapps.toml
docker compose -f compose.local.yml up --build
```

Then open http://localhost:5173, go to **Jobs** and submit `import_mars_plumes` (add `"limit": 500` to the parameters for a quick first try). The **Validate** tab fills with the public plumes and **Sources** with their history. The API docs are at http://localhost:8000/api/docs.

## Quickstart without Docker

You need [uv](https://docs.astral.sh/uv/), Node 20 or newer, and PostgreSQL with PostGIS 3.4.

```bash
uv sync
cp geoapps.toml.example geoapps.toml
export GEOAPPS_DATABASE_URL=postgresql+psycopg://geoapps:geoapps@localhost:5432/geoapps

uv run geoapps-db upgrade                              # create schemas and tables
uv run geoapps-worker sync                             # register the ETL steps
uv run geoapps-worker submit import_mars_plumes '{}'  # queue the public Eye on Methane plumes
uv run geoapps-worker run &                            # drain the queue
uv run geoapps-api &                                   # http://localhost:8000/api/docs

cd web && npm install && npm run dev                   # http://localhost:5173
```

Catalog previews need titiler on port 8001 (`docker compose -f compose.local.yml up titiler` runs just that).

### Bring your own detections

`import_detections` takes a GeoJSON FeatureCollection, from a path or URL, of polygons or points with `observed_at` and `p` in their properties, plus `q_kg_h` and `q_sigma_kg_h` when the plume is quantified. Every row lands as `predicted` and waits for a verdict.

```bash
uv run geoapps-worker submit import_detections '{"source": "my_plumes.geojson"}'
```

## Tests

The pure tests run anywhere. The database tests need a throwaway PostGIS database, because they drop and recreate every geoapps schema. The MARS importer is tested against a fixture that follows the published column list; its rows are invented.

```bash
uv run pytest                                          # core only; database tests skip
GEOAPPS_TEST_DATABASE_URL=postgresql+psycopg://geoapps:geoapps@localhost:5432/geoapps_test uv run pytest
uv run ruff check packages && uv run ruff format --check packages
cd web && npm run build                                # typecheck and bundle
```

Tests are named after the design plan's gates, so a failing test points at the decision it protects:

| Gate | What the test checks |
|---|---|
| A1 | migrations go head → base → head, and the models match head exactly |
| A2 | 10,000 random operator links leave no overlap for one asset; a source sits on one facility at a time (exclusion constraints) |
| A3 | with 3 operator changes, "who operated it on date X?" is right on 1,000 of 1,000 random dates |
| E1 | a label carries over to a reprocessed mask when IoU ≥ 0.5 |
| E4 | a rejected plume raises no alert; only a confirmed one reaches watches |
| E5 | priority decays by e⁻¹ one λ past the window; window-closing plumes always alert |
| F1 | a source directly downwind of the plume scores zero |
| G3, H5 | overpasses needed to verify a repair; persistence posterior |
| H1 | invalid ETL parameters return 422 and create no job |
| K1 | resubmitting a job with the same key returns the same job |
| L2 | marks are validated against the event kind before a row exists |
| — | events chain by a 30-day gap, or split at a clear look; persistence counts only looks that could see the threshold |
| — | an import of the same bytes is a no-op; a re-import never rewrites a reviewed plume |

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
