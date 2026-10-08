# geoapps

A platform for events that remote sensing sees intermittently: something appears in a scene, may or may not be real, may come back on the next pass, and matters to someone because of where it is and who is behind it.

Trace-gas plumes, oil spills, floods, heavy rain and tropical cyclones all have that shape. Each pass gives a snapshot; snapshots form events with a start and an end; events happen at places that registries know about; and people want to be told when something they care about happens. geoapps handles that shape once, and each kind of event plugs in what is particular to it.

## The problem

Machine detection over satellite archives produces candidates, not facts. Turning them into something people can act on needs the same steps whatever the phenomenon:

```
SCENE           one look by one sensor
  │ a model finds
  ▼
DETECTION       a candidate snapshot: a shape,
  │             a time, its measurements, and
  │             how likely it is to be real
  │ a person confirms or rejects
  ▼
VALIDATED       only these go further
  │ chained over time into
  ▼
EVENT           one episode, start and end
  │             known within bounds
  │ attributed to
  ▼
ENTITY          the place, site or organization
  │             behind it, valid over time
  │ watched by
  ▼
ALERT           someone who cares is told;
                their feedback becomes labels
```

And underneath, three things that are easy to get wrong:

- **Non-detections matter.** "How often does this happen here?" needs every clear look that found nothing, not only the detections.
- **The world changes.** Who operates a site, which unit a region reports under, which registry names it: all valid over time, and answers depend on the date.
- **Methods change.** Models are retrained, products reprocessed and datasets revised; every row has to say which data and versions produced it, and human labels must survive reprocessing.

## Four apps on one platform

| App | What it is for |
|---|---|
| 1. Labeling and validation | A person has the final say on every predicted detection. Nothing unvalidated goes downstream. |
| 2. Attribution | A validated detection reaches the entities behind it, each link valid over a time window. |
| 3. Watchlists and alerts | Watch an area, a site or a kind of event; validated detections raise alerts; dismissals become labels. |
| 4. Analysis and research | Every layer, what-if reruns in a sandbox, model comparison and promotion, a catalog explorer and a notebook client. |

geoapps is an app, not a dataset. Each instance brings its own data, public or private, its own storage and its own compute. One person on a laptop and a small team run the same code with different configuration, with PostgreSQL in both cases.

## Event kinds

Core tables and apps never branch on what an event is. A kind registers:

- **geometry** of one snapshot: a point, an outline, a track segment;
- **marks**: what a detection measures, validated before a row exists;
- **link rule**: how detections chain into events (same source, overlap, a tracker);
- **entities** it may be attributed to;
- **publication policy**: whether and how validated events may be exported.

Methane plumes are the kind implemented first and the running example in the design documents ([`04-running-example-methane.md`](docs/design/04-running-example-methane.md) shows it on public data). [Walkthroughs](docs/design/walkthroughs/README.md) cover the other kinds discussed so far:

| Kind | Snapshot | Linked into events by | Attributed to |
|---|---|---|---|
| [Trace-gas plumes](docs/design/walkthroughs/01-other-trace-gases.md) (CH₄, CO₂, NO₂, SO₂) | outline + source point | same source over passes | facility, operator, government |
| [Oil spills](docs/design/walkthroughs/02-oil-spills.md) | slick outline | overlap after drift | vessel, platform, pipeline |
| [Floods](docs/design/walkthroughs/03-floods.md) | flood extent per pass | overlap within a basin | basin, admin region |
| [Heavy rain](docs/design/walkthroughs/04-heavy-rain.md) | footprint per time step | contiguous in space and time | basin, admin region |
| [Tropical cyclones](docs/design/walkthroughs/05-tropical-cyclones.md) | centre + wind radii | the system's tracker | landfall regions |
 Other kinds plug in through `geoapps_core.kinds.register_kind` with their own steps; sensitive kinds, such as conflict events, are out of scope.

## Design

- [`01-design-plan.md`](docs/design/01-design-plan.md): the four apps, ownership rules, a running example in eight stages, data placement, the stack, and workstreams A to M with their gates.
- [`02-end-to-end-pipeline.md`](docs/design/02-end-to-end-pipeline.md): one event from scene to alert in 14 steps, and how the other kinds fit the same pipeline.
- [`03-data-model.md`](docs/design/03-data-model.md): datasets, detections, sources, events, facilities, assets and orgs, with validity ranges, provenance and the constraints the database enforces.
- [`04-running-example-methane.md`](docs/design/04-running-example-methane.md): the methane plume kind, the public Eye on Methane import, and how to try it.
- [`walkthroughs/`](docs/design/walkthroughs/README.md): the same path, scene to alert, for other trace gases, oil spills, floods, heavy rain and tropical cyclones, with what each kind plugs in and what geoapps still lacks for it.

## What is here

```
packages/
  geoapps-core      science and rules with no I/O: queue priority, persistence, event chaining,
                    attribution weights, label carry-over, the event-kind registry, config
  geoapps-db        the only code that writes to Postgres: models and repository functions,
                    one module per schema (core, ref, review, attribution, monitor, notify),
                    and the Alembic migrations
  geoapps-workers   registered steps (ETLs) with typed parameters, and a Postgres job queue
                    (FOR UPDATE SKIP LOCKED) that workers drain
  geoapps-api       FastAPI: queue, verdicts, sources, events, attribution, watches, alerts,
                    feedback, datasets, jobs, catalog search
web/                React + TypeScript + Vite + MapLibre shell; types generated from the OpenAPI schema
docs/design/        the design documents
compose.local.yml   PostGIS, migrations, api, worker, titiler and web on one machine
```

Working end to end today: detections arrive from an import step as `predicted`; an analyst confirms or rejects each one; confirmed detections chain into events at their source; a source can be attributed to a facility and through it to an asset, an operator and a government, each valid over time; a confirmed detection on a watched area raises an alert, and a dismissal comes back as feedback. Every import records where its data came from and under which licence, and the map credits it.

Registered steps:

| Step | What it does |
|---|---|
| `import_detections` | Any GeoJSON FeatureCollection of detections, for any registered kind. |
| `import_mars_plumes` | Public methane plumes from UNEP IMEO's Eye on Methane, with outlines, sources and sensors ([details](docs/design/04-running-example-methane.md#3-public-data-the-eye-on-methane-plumes)). |
| `seed_demo` | Synthetic detections, for tests and offline trials only. |

The map has three basemaps: streets (OpenFreeMap), imagery (EOX Sentinel-2 cloudless) and an offline Natural Earth 1:10m map served by the app itself, with coasts, country and state lines, rivers, lakes, highways, urban areas and place names. If a remote basemap can't be reached, the map falls back to the offline one. `web/scripts/build-basemap.mjs` rebuilds the offline layers from Natural Earth (public domain) and Noto Sans glyphs (SIL OFL).

Not built yet, in the order the design plan's roadmap takes them: redrawing a detection on the map, an entity inventory import, the ingest half of the catalog explorer, pgSTAC and Zarr through titiler.xarray, monitoring pipelines that record observations, the notebook client, GeoParquet exports, scheduled pipelines, outbound notifications and auth.

## Quickstart with Docker

```bash
cp geoapps.toml.example geoapps.toml
docker compose -f compose.local.yml up --build
```

Open http://localhost:5173, go to **Jobs** and submit an import step; the **Validate** tab fills with what it brought in. The API docs are at http://localhost:8000/api/docs. For a first run on public data, follow [the running example](docs/design/04-running-example-methane.md#4-try-it).

## Quickstart without Docker

You need [uv](https://docs.astral.sh/uv/), Node 20 or newer, and PostgreSQL with PostGIS 3.4.

```bash
uv sync
cp geoapps.toml.example geoapps.toml
export GEOAPPS_DATABASE_URL=postgresql+psycopg://geoapps:geoapps@localhost:5432/geoapps

uv run geoapps-db upgrade                                             # create schemas and tables
uv run geoapps-worker sync                                            # register the steps
uv run geoapps-worker submit import_detections '{"source": "my.geojson", "kind": "ch4_plume"}'
uv run geoapps-worker run &                                           # drain the queue
uv run geoapps-api &                                                  # http://localhost:8000/api/docs

cd web && npm install && npm run dev                                  # http://localhost:5173
```

Catalog previews need titiler on port 8001 (`docker compose -f compose.local.yml up titiler` runs just that).

### Bring your own detections

`import_detections` takes a GeoJSON FeatureCollection, from a path or URL. Each feature's geometry is the kind's shape (or a point when only the location is known), and its properties hold an `observed_at` time and the kind's marks; `GET /api/kinds` lists each kind's marks schema. Every row lands as `predicted` and waits for a verdict.

## Tests

The pure tests run anywhere. The database tests need a throwaway PostGIS database, because they drop and recreate every geoapps schema.

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
| A2 | 10,000 random role links leave no overlap; a source sits on one facility at a time (exclusion constraints) |
| A3 | with 3 operator changes, "who operated it on date X?" is right on 1,000 of 1,000 random dates |
| E1 | a label carries over to a reprocessed shape when IoU ≥ 0.5 |
| E4 | a rejected detection raises no alert; only a confirmed one reaches watches |
| E5 | queue priority decays by e⁻¹ one λ past the window; detections whose window is closing always alert |
| F1 | a candidate source directly downwind of the detection scores zero |
| G3, H5 | looks needed to verify that something stopped; the persistence posterior |
| H1 | invalid step parameters return 422 and create no job |
| K1 | resubmitting a job with the same key returns the same job |
| L2 | marks are validated against the event kind before a row exists |
| — | events chain by a gap rule, or split at a clear look; persistence counts only looks able to see the threshold |
| — | importing the same bytes is a no-op; a re-import never rewrites a reviewed detection |

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
