# Running example: methane plumes

How the general platform is used for one event kind, methane (CH₄) plumes, and how to run it on public data.
The other design documents use plumes as their running example; this page is the practical side of that: the importers, the data they bring, and what to watch out for.

## 1. Why plumes

A methane plume exercises every part of the platform at once:

- **Detection:** a retrieval and segmentation on one scene, with a calibrated probability that the plume is real.
- **Validation (app 1):** many false positives, so a person must confirm each one before anything downstream sees it.
- **Quantification:** a flux Q̂ ± σ_Q in kg h⁻¹ from the plume's mass and the wind.
- **Attribution (app 2):** the plume points back at a source, the source sits on a facility, and the facility leads to an asset, an operator and a government, all of which change over time.
- **Monitoring and alerts (app 3):** sources emit intermittently, so persistence needs the clear looks that found nothing, and watchers care about specific sites.

## 2. The kind

`ch4_plume` is registered in `geoapps_core.kinds`:

```
name        ch4_plume
geometry    Polygon (the outline), or Point when only the source location is known
marks       p          probability the plume is real, [0, 1]
            viability  scene viability, [0, 1]
            q_kg_h, q_sigma_kg_h            flux and its uncertainty (optional: unquantified plumes exist)
            wind_u_m_s, wind_v_m_s, wind_speed_m_s
            total_emission_t, total_emission_sigma_t   transient events only
link        same_source: detections at one source chain into events
entities    source → facility → asset → operator, government
```

An unquantified plume ranks in the validation queue as if Q̂ = Q_ref, so it is neither buried nor promoted.

## 3. Public data: the Eye on Methane plumes

`import_mars_plumes` downloads the public plume list of UNEP IMEO's [Eye on Methane](https://methanedata.unep.org/download-dataset) (the Methane Alert and Response System, MARS) and imports it.

**Formats.** The list is published as a ZIP of GeoJSON, whose features carry each plume's outline, and as a ZIP of CSV with the source point only. The GeoJSON is the default; the CSV also works and gives points.

**Mapping**, following the published [data dictionary](https://methanedata.unep.org/dict-mars-plumes):

```
geometry (GeoJSON)          plume outline                → review.detection geometry
id_plume                    unique plume id              → ref.xref (unep-mars, detection)
source_name                 source id                    → ref.source, via ref.xref
satellite                   satellite and agency         → ref.sensor
tile_date                   observation time             → observed_at
lat, lon                    source location              → origin, and the source point
ch4_fluxrate(_std)          kg h⁻¹                       → marks.q_kg_h, q_sigma_kg_h
wind_u, wind_v, wind_speed  m s⁻¹                        → marks.wind_*
total_emission(_std)        t                            → marks.total_emission_*
tile, tile_background       product ids                  → scene_id, attrs
country, sector             where and what               → ref.source
actionable, notified, institutions, last_update, insert_date → attrs
```

**Geometry rules.** Outlines inside a GeometryCollection are gathered into one geometry. Self-intersecting outlines are repaired with `ST_MakeValid` on the way in. A record with an outline but no lat/lon gets the outline's centre as its origin, and `attrs.origin_from = "outline_centroid"` says so.

**Provenance.** The file is recorded in `core.dataset` with its URL, SHA-256 and licence, and every plume gets an assertion and an xref. Rerunning the import on the same bytes does nothing. A newer file updates plumes that nobody has reviewed yet and reports, without changing them, the ones already reviewed (`changed_after_review`).

**Validation.** Every imported plume is born `predicted`, as everywhere else (gate E4). MARS analysts have already reviewed their public plumes, so `accept_provider_validation: true` records that review as a label by `provider:unep-mars` instead of reviewing each plume again. The verdict is still a label, so it stays visible and reversible, and a label set can be frozen from those labels alone.

**What it cannot give.** MARS lists plumes, not the clear looks that found nothing, so persistence is not computed from it (data model §7). Events chain by the 30-day gap rule, with t_a and t_d left unknown. Attribution has nothing to propose until a facility inventory is imported.

**Licence.** CC BY-NC-SA 4.0: non-commercial use only, credit to UNEP IMEO, and anything derived from it shared under the same licence. The map shows the credit line for every dataset that contributed detections.

**Queue order on an archive.** The urgency term u(a) decays after the notification window, so plumes months old all score near zero. The queue then falls back to newest first.

## 4. Try it

With Docker:

```bash
cp geoapps.toml.example geoapps.toml
docker compose -f compose.local.yml up --build
```

Open http://localhost:5173, go to **Jobs** and submit `import_mars_plumes`; add `"limit": 500` to the parameters for a quick first try. **Validate** fills with the public plumes, **Sources** with their history.

Without Docker, after the README's setup:

```bash
uv run geoapps-worker submit import_mars_plumes '{"limit": 500}'
uv run geoapps-worker run
```

## 5. Your own plumes

`import_detections` takes any GeoJSON FeatureCollection of polygons or points. For plumes, put `observed_at` and `p` in each feature's properties, plus `q_kg_h` and `q_sigma_kg_h` when the plume is quantified:

```json
{"type": "Feature",
 "geometry": {"type": "Polygon", "coordinates": [[[-103.48, 31.87], [-103.47, 31.873], [-103.468, 31.869], [-103.48, 31.87]]]},
 "properties": {"observed_at": "2026-09-14T17:32:00Z", "scene_id": "my-scene-42",
                "p": 0.9, "q_kg_h": 980, "q_sigma_kg_h": 310}}
```

## 6. Synthetic plumes

`seed_demo` creates teardrop-shaped plumes around five made-up Permian well pads, with scene ids starting `synthetic-`. They exist for tests and for trying the platform with no network; they are never real observations.

## 7. Tests specific to plumes

- The MARS importer is tested against `packages/geoapps-workers/tests/data/mars_fixture.csv`, which follows the published columns; its rows are invented (sources `TST…`, country "Testland").
- GeoJSON outline tests cover a plain polygon, an outline inside a GeometryCollection, an outline without lat/lon, and a self-intersecting outline repaired into two polygons.
- Gate F1 is checked with plume wind: with the wind blowing east, a facility directly downwind scores zero.
