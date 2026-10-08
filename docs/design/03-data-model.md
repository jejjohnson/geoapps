# Data model

How detections, entities, observations and events are stored, and who writes each table.
It implements workstream A of the design plan and the entity, monitoring and attribution pages of the extreme-events framework, adapted to the four apps.

**Running example:** a public plume from the UNEP IMEO Eye on Methane dataset (MARS), imported into a fresh instance, then reviewed, attributed and watched.

## 1. The objects, top to bottom

```
DATASET          one fetched file, public or private:
  │              URL, licence, checksum, fetch time
  │ asserts
  ▼
ASSERTION        "provider P says record R",
  │              accepted or not
  │ creates
  ▼
DETECTION        one snapshot of one event, born
  │              predicted (app 1 decides)
  │ seen by          ▲ anchored to
  │ SENSOR           │ SCENE (scene id, for now)
  │
  │ labelled by
  ├──────────► LABEL      a verdict, append-only
  │                │ frozen into
  │                ▼
  │             LABEL SET  versioned training data
  │
  │ emitted from
  ▼
SOURCE           one emission point in space,
  │              many detections over the years
  │ chained in time into
  ├──────────► EVENT      one episode at a source,
  │                       start and end within bounds
  │
  │ attributed to (scored, then confirmed)
  ▼
FACILITY         a site: the sources on it
  │ belongs to (valid over a time range)
  ▼
ASSET            a government reporting unit:
  │              lease, licence, concession
  │ operated / owned by (valid, with share)
  ▼
ORG              a company, a government or a
                 regulator; orgs nest through
                 ORG RELATION (subsidiary, JV)

LOCATION         where monitoring looks: an area
  │              around a source or facility
  │ looked at by
  ▼
OBSERVATION      one look: valid fraction and
                 detection limit, with or without
                 a detection
```

Three distinctions carry most of the design:

- **A detection is a snapshot; an event is an episode.** Two detections on 4 and 9 September at the same source are one event if nothing closed it in between.
- **A source is what we saw; a facility is what is there.** A source exists because plumes came from that point. A facility exists because a registry or an analyst says there is a site, and it groups every source on that site.
- **A location is where we look.** It is a monitoring decision with an area, sensors and a revisit schedule. Persistence is counted over its observations, never over detections alone.

## 2. Schemas

| Schema | Holds | Written by | App |
| --- | --- | --- | --- |
| `core` | runs, ETLs, jobs, datasets, assertions | workers, API | all |
| `ref` | sensors, sources, facilities, external ids | importers, app 2 | all |
| `review` | detections, labels, label sets | importers, app 1 | 1 |
| `attribution` | source → facility links, assets, orgs, roles | app 2, importers | 2 |
| `monitor` | locations, their status history, observations, events | monitoring pipelines | 3, 4 |
| `notify` | watches, alerts, outbox, feedback | app 3 | 3 |

`catalog` (pgSTAC) joins later; until then a detection carries its scene id as text.

## 3. Time

Two clocks, kept apart on purpose.

- **Validity** says when something was true in the world. Every link that can change carries `valid tstzrange`: source → facility, facility → asset, org → asset, org → org, facility → government.
- **Recording** says when we learned it: `created_at` on every row. Rows are never updated to change a fact. A change closes the old range and opens a new row.

"Who operated this lease on 14 September?" is the role whose `valid` contains that date.
"What did we believe on 1 October?" adds `created_at ≤ 1 October`.

Exclusion constraints make the database, not the app, refuse contradictions:

```
attribution.source_facility
  EXCLUDE (source_id =, valid &&) WHERE status = 'confirmed'
  -- a source sits on one facility at a time

attribution.facility_asset
  EXCLUDE (facility_id =, valid &&)
  -- a facility reports under one asset at a time

attribution.org_asset
  EXCLUDE (asset_id =, valid &&) WHERE role = 'operator'
  -- one operator at a time; owners may share
```

## 4. Provenance

Every imported fact names where it came from.

- `core.dataset` is one fetched file: name, URL, licence, attribution text, SHA-256, row count, fetch time. Fetching the same bytes twice is a no-op.
- `core.assertion` is one claim from one provider about one record, and whether it was accepted.
- `ref.xref` maps a provider's record id to our entity, so `USA123` in MARS and `fac-77` in a registry can both point at one source.

A detection from MARS therefore carries `dataset_id`, an assertion, and an xref from `('unep-mars', 'detection', id_plume)`. Re-importing a newer file matches on the xref instead of creating duplicates.

## 5. Status: who may say a plume is real

Every detection is born `predicted`, whoever produced it, our model or a public dataset (E4). Only `review.label` rows change that, through `repo.record_verdict`.

A curated public dataset has already been reviewed by its provider. Its importer can, when asked, record that review as a label whose analyst is `provider:<name>`. The verdict is still a label, so it stays visible and reversible, and the instance owner decides whether to trust it.

## 6. Events: start and end within bounds

We never see an emission start or stop, only the looks around it. For one event at one source:

- t_a: last valid look **without** a plume before it
- t_b: first look **with** a plume
- t_c: last look **with** a plume
- t_d: first valid look **without** a plume after it

The start lies in [t_a, t_b] and the end in [t_c, t_d]. With no observations (a detections-only dataset such as MARS), t_a and t_d are unknown and stay null. Events are then chained by a gap rule: a detection more than G days after the previous one opens a new event (G = 30 by default).

```
# Shapes: one source; K validated detections sorted by time t₁ ≤ … ≤ t_K
# new event at k  ⇔  t_k − t_{k−1} > G
# Q̄_e = ∑ wₖ Qₖ / ∑ wₖ,  wₖ = 1/σₖ²     inverse-variance mean when σ is known
```

## 7. Persistence

Persistence is the fraction of valid looks at a location that showed a plume:

```
# Shapes: N_valid looks of one location in a window; N_det of them with a detection
# P | data ~ Beta(1 + N_det, 1 + N_valid − N_det)
```

It needs observations, including the ones that found nothing. A detections-only dataset cannot supply them, so MARS plumes give sources and events but no persistence until a monitoring pipeline records looks.

## 8. Tables

### core

- `run`: id, stream, etl, versions, created_at
- `etl`: name, version, description, params_schema, writes
- `job`: id, etl, params, state, key, submitted_by, run_id, result, error, timestamps
- `dataset`: id, name, url, licence, attribution, sha256, n_records, fetched_at, run_id
- `assertion`: id, provider, dataset_id, record_id, claim, accepted, asserted_at

### ref

- `sensor`: id, name, platform, agency, sensor_type, gsd_m
- `source`: id, name, event_kind, source_type, sector, country, point, status, first_seen, last_seen, attrs
- `facility`: id, name, facility_type, sector, country, geometry, status, valid, attrs
- `xref`: entity, entity_id, provider, record_id, match_score; unique per (provider, entity, record_id)

### review

- `detection`: id, kind, status, sensor_id, source_id, event_id, dataset_id, scene_id, observed_at, geometry (outline or point), origin, marks, priority, supersedes_id, run_id
- `label`: id, detection_id, scene_id, geometry, verdict, analyst, note
- `label_set`: id, name, frozen_at, filter, n_labels
- `label_set_member`: label_set_id, label_id

### attribution

- `source_facility`: id, source_id, facility_id, score, method, status, valid, decided_by, decided_at, supersedes_id, assertion_id, run_id
- `org`: id, name, org_type (company, government, regulator), country
- `org_relation`: parent_id, child_id, relation, valid
- `asset`: id, name, asset_type, jurisdiction, reporting_id, government_id, valid
- `facility_asset`: facility_id, asset_id, valid, assertion_id
- `org_asset`: org_id, asset_id, role (operator, owner), share, valid, assertion_id
- `facility_government`: facility_id, org_id, role, valid, assertion_id

### monitor

- `location`: id, name, area, status, source_id, facility_id, sensors, revisit_days
- `location_status`: location_id, status, at, by, reason (one row per transition)
- `observation`: id, location_id, sensor_id, scene_id, observed_at, valid_fraction, detection_limit_kg_h, detection_id, run_id
- `event`: id, kind, source_id, location_id, t_a, t_b, t_c, t_d, status, n_detections, q_mean_kg_h, q_sigma_kg_h, run_id

### notify

- `watch`, `alert`, `outbox` as before
- `feedback`: id, author, about (alert, detection, attribution, facility), about_id, kind, body, action, created_at. Dismissing an alert writes one.

## 9. The running example, as rows

One MARS record, `id_plume = 3f1c…`, `source_name = USA123`, Sentinel-2, 14 September, 1 400 ± 600 kg/h:

```
core.dataset      7  unep-mars-plumes  CC BY-NC-SA 4.0  sha256 9a1e…  n=…
core.assertion    41 provider=unep-mars  record=3f1c…  claim=plume
ref.sensor        2  "Sentinel-2 (ESA)"
ref.source        12 USA123  Oil and Gas  United States  POINT(−103.48 31.87)
ref.xref          (unep-mars, source, USA123)    → source 12
                  (unep-mars, detection, 3f1c…)  → detection 901
review.detection  901 ch4_plume  predicted  sensor 2  source 12  dataset 7
                      outline: MULTIPOLYGON(…) from the GeoJSON feature
                      origin:  POINT(−103.48 31.87) from lat/lon
                      q 1400 ± 600 kg/h
monitor.event     55  source 12  t_b = t_c = 14 Sep  open
```

An analyst confirms it: one `review.label` row, status `validated`, and any watch over the Permian raises one alert. Later, app 2 proposes `source 12 → facility 1042` with score 0.86; confirming it opens a `source_facility` row valid from 14 September, and from then on the facility's asset and operator answer "who".

## 10. Not yet

- pgSTAC scenes in place of scene ids
- plume groups (one moment seen by two sensors) between detection and event
- regions and roll-ups with Monte Carlo samples (framework page 6)
- the notification state machine to operators and governments
