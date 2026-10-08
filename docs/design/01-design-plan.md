# Geo apps: design plan for four apps on one platform

Oct 8, 2026 · @J. Emmanuel Johnson

## Summary

Build four apps as four views over one data platform: one PostgreSQL database, one data-access package, one FastAPI backend and one frontend shell. GeoStack stays the compute core and never imports app code; the apps call it only through batch jobs, never inside a request.

The four apps share every object. A detection validated in app 1 is the thing attributed in app 2, watched in app 3 and studied in app 4, and feedback from app 3 flows back into the labels of app 1. Splitting them into four databases would turn every one of those joins into application code.

One rule holds across all four: no machine-predicted plume reaches attribution, notifications, persistence counts or the public catalog until a person has validated it in app 1. Models may rank and route the review queue; they never decide that a plume is real.

The platform is not methane-specific. Any event that intermittent remote sensing can extract (trace-gas plumes, oil spills, floods, heavy rain, tropical cyclones) enters as an event kind on the same core (workstream L). Plumes stay the running example because they exercise attribution and notification hardest. Sensitive kinds, such as conflict events, are out of scope.

For now it is a watchlist and model-reinforcement platform: analysts' verdicts and watchers' dismissals become labels that retrain the models, and watchlists turn validated events into alerts. Outbound notifications to operators or governments come later, on the same rules.

geoapps is an app, not a dataset: every instance brings its own data, public or private, and its own storage and compute. One person on a laptop and a team in the cloud run the same code with different configuration (workstream M).

Two shared capabilities sit under all four apps and surface mainly in app 4: a catalog explorer whose ETLs analysts can run themselves, and a Python client that moves data and layers between a notebook and the app.

- **A. One database, one data-access layer.** Relationship data (facilities, assets, operators, governments, notifications, feedback) is written concurrently and needs history. PostgreSQL + PostGIS + pgSTAC holds it, with one schema per app, and a single Python package of SQLAlchemy 2 + GeoAlchemy2 models and Alembic migrations is the only code allowed to write.
- **B. Exports are an optional, one-way GeoParquet snapshot.** Each instance can publish dated GeoParquet snapshots of its validated data with a stac-geoparquet index, read by DuckDB and DuckDB-WASM. Nothing is published by default, because the data belongs to whoever runs the instance.
- **C. Rasters are served, not stored in the database.** Sparse scene COGs and dense Zarr cubes stay on object storage. titiler serves both (pgSTAC mosaics for COGs, an xarray backend for Zarr), and Postgres only holds their STAC items and footprints.
- **D. One frontend shell, four apps.** Each app needs the same map, layer panel, time slider and attribute table. One React + TypeScript shell on MapLibre, deck.gl and DuckDB-WASM, styled after GeoLibre, hosts all four as routes.
- **E. App 1: labeling and validation.** A predicted plume is only a candidate until a person says it is real. Analysts confirm, reject, redraw or add detections, nothing unvalidated goes downstream, and every verdict is a label anchored to scene + geometry and frozen into versioned label sets. A priority score orders the queue and alerts analysts to plumes that are likely, large, could trigger a notification, or are close to leaving the notification window.
- **F. App 2: attribution.** A detection has to reach a source, a facility, an asset, an operator and a government, each link valid only over a time window. Candidate sources are scored automatically, analysts confirm, and every link stores the method and the source-database snapshot it used.
- **G. App 3: watchlists and alerts, notifications later.** Users watch sites, facilities, regions or event kinds and get alerts when validated events cross their rules; dismissing an alert as wrong sends it back for review, closing the reinforcement loop. Outbound notifications to operators or governments are a later phase that reuses the rules and adds a state machine with replies.
- **H. Catalog explorer with callable ETLs.** Analysts want to see what a public catalog holds, overlay it, and ingest it only if it is worth it, without asking an engineer. ETLs are registered with a typed parameter schema, previews read remote items without copying, and ingests land in a staging collection that is promoted or expires.
- **I. A researcher client for notebooks and scripts.** A new algorithm is tried on a laptop, not in the app, but its output should show up in the app beside production. geoapps-client pulls scenes, labels and detections with a few helpers, and pushes results back as private scratch layers.
- **J. App 4: analysis and research.** Looking at data, trying algorithms and judging them is exploratory work, done by different people with different write rights from validation. App 4 hosts the explorer (H) and researchers' layers (I), compares model versions on frozen label sets, and owns model promotion. It reads every layer (data held and data available, sources, facilities, notifications, time series and persistence) and runs what-if reruns in a private sandbox.
- **K. Scheduled pipelines: discovery, monitoring, reanalysis and backfill.** These are three kinds of work with different triggers, scopes and output streams, each made of many pipelines. They share one set of primitives (registered steps, scopes, streams, run tuples, triggers), and only monitoring records the non-detections that persistence needs.
- **L. Every phenomenon is an event kind.** Gases, oil spills, floods, rain and cyclones differ in data, geometry, what they measure and who is told, but not in how detections are stored, reviewed, grouped into events and versioned. Each kind plugs in its operators, geometry, marks, linking rule, entity types, priority, notification and publication policy; the core and the apps never branch on a kind's name.
- **M. One codebase, from a laptop to a team, on your own data.** A researcher alone and a small team need the same platform, and neither should depend on someone else's data. An instance is configured with its sources, storage, executors and users; Postgres runs in both profiles, outputs are precomputed, and jobs go to local or cloud compute.

**End state.** Object storage holds bytes (COG, Zarr, GeoParquet, PMTiles); Postgres holds rows that point at them. geoapps-db owns every table and migration. The FastAPI backend owns the HTTP contract and job submission. Workers run GeoStack operators (plumax, geotoolz, xrtoolz, xtremax) and write back through geoapps-db. The shell owns the look; apps 1–4 own only their panels and workflows, and the explorer lives in app 4. geoapps-client owns the notebook path in and out.

## Ownership rules

Dependencies point down toward storage, and the only path from GeoStack into the database runs through a worker.

```
  CLIENTS
    geoapps-web (one shell)    app 1 validation · app 2 attribution
                               app 3 watch · app 4 research
    notebook / script          geoapps-client
          │
          ├──► geoapps-api      FastAPI · auth · ETL registry
          ├──► titiler          COG · pgSTAC mosaics · Zarr
          └──► object storage   public GeoParquet, read directly
          │
  SERVICES
    geoapps-api ──► geoapps-workers     discover · monitor · reanalyse
                       └─ GeoStack      geotoolz · xrtoolz · plumax · xtremax
    geoapps-api, workers ──► geoapps-db only writer · ORM · Alembic
          │
  STORAGE
    geoapps-db ──► PostgreSQL           PostGIS · pgSTAC
    titiler    ──► PostgreSQL (pgSTAC), object storage
    workers    ──► object storage, public STAC catalogs
```

Arrows mean "calls or reads". The shell reaches Postgres only through the API, reads rasters through titiler and the public GeoParquet directly; GeoStack sits inside the workers because no other service may import it. A notebook reaches the platform the same way the shell does, through the API, and its downloads use signed URLs the API hands out.

1. **Object storage** owns bytes: scene COGs, Zarr cubes, GeoParquet exports and PMTiles. Nothing is overwritten; a new version is a new key.
2. **PostgreSQL** owns relationships, workflow state and history, plus the pgSTAC catalog of every file. It never stores pixels; rows point at files by URI and checksum.
3. **geoapps-db** owns the ORM models, Alembic migrations and query functions. It is the only code that writes to Postgres. It never imports FastAPI or JAX.
4. **geoapps-workers** own every computation: ingestion, retrieval, segmentation, scoring, exports and outbound notifications. They import GeoStack and geoapps-db. They never serve HTTP.
5. **geoapps-api** owns the HTTP contract, authentication, permissions, job submission and the registry of ETLs users may run. It imports geoapps-db and never GeoStack, so no JAX runs in the web process.
6. **titiler** owns pixel serving for COG and Zarr. It reads object storage and pgSTAC and never writes.
7. **geoapps-web** owns the shell: map, layer panel, time slider, attribute table, catalog explorer, sign-in. It talks to the API, titiler and the public GeoParquet, never to Postgres.
8. **Apps 1–4** own their panels and workflows inside the shell. They share objects through the API, never by importing each other's code.
9. **GeoStack** (geotoolz, xrtoolz, pipekit, plumax, xtremax and the GeoML libraries) owns the algorithms as pure operators with no I/O. It never imports anything named geoapps.
10. **geoapps-client** owns the researcher's path in and out: search, open, download and scratch layers. It calls the API and reads the public catalog, may import GeoStack to open arrays, and never touches Postgres.
11. **Public catalogs** (other people's STAC APIs and buckets) are read-only inputs. Previews read them in place; only a registered ETL copies from them, and only into a staging collection.
12. **App 1** owns the verdict on every detection. A detection leaves `predicted` only by a person's decision; apps 2 and 3, persistence counts and the public export read only `validated` rows, and app 4 may show the rest only with its status on screen.
13. **App 4** reads every layer and writes only to scratch, staging and sandbox streams. It never edits a verdict, an entity link or a notification.
14. **geoapps-pipelines** owns schedules, triggers and pipeline definitions for discovery, monitoring, reanalysis and backfill. It enqueues registered steps for the workers and never computes or writes results itself.
15. **Event kinds** own everything phenomenon-specific: operators, geometry, marks, linking, entity types, priority, notification and publication rules. Core tables and apps never branch on a kind's name.
16. **Instance configuration** owns data sources, storage locations, executors, licences and users. Code never hard-codes a bucket, a cloud or a sensor's licence.

## How the apps compose: one running example

One Tanager-1 scene over the Permian Basin shows a methane plume near a well pad, and the same plume passes through all four apps. The scene is a hyperspectral COG with 30 m pixels; the retrieval turns it into an enhancement map, the segmenter into a mask, and the estimator into a flux. N is the number of pixels in the scene, K the number of candidate sources within the search radius, and T the number of overpasses of a site.

### Stage 1: a detection lands and an analyst reviews it (workers → geoapps-db → api → app 1)

**TL;DR.** A new scene produces a candidate plume, an analyst confirms, redraws or rejects it, and the verdict is stored against the scene and the drawn shape.

**Problem.** Let s be the scene id, ΔΩ ∈ ℝᴺ the methane column enhancement in mol m⁻², M ∈ {0, 1}ᴺ the plume mask, and Q ± σ\_Q the flux in kg h⁻¹. A label is ℓ = (s, G, v, a, t): the scene, a polygon G, a verdict v ∈ {confirm, reject, redraw, add}, the analyst a and the time t. Plume ids die when a scene is reprocessed, so a label is matched to a new detection by mask overlap.

```latex
\operatorname{IoU}(M_a, M_b) = \frac{\lvert M_a \wedge M_b \rvert}{\lvert M_a \vee M_b \rvert}, \qquad \ell \text{ carries over to } d \iff \operatorname{IoU}(G_\ell, M_d) \ge \tau
```

```python
# Shapes: N pixels in scene s; one detection d; one label ℓ
# ΔΩ = retrieval(L1 radiance)                                     arguments sketched
delta_omega = retrieve(scene)                       # (B, N) → (N,) mol m⁻²      GeoStack operator, name to verify
# M = segment(ΔΩ)
mask = segment(delta_omega)                          # (N,) → (N,) {0, 1}          GeoStack operator, name to verify
# Q ± σ_Q = IME(ΔΩ, M, u₁₀)
q, q_sigma = estimate(delta_omega, mask, wind)      # (N,), (N,), (2,) → (), ()   plumax, name to verify

# one row per detection, pointing at its COGs by URI
db.detections.add(scene_id=s, geom=polygon(mask),   # (N,) → Polygon              proposed (A)
                  q_kg_h=q, q_sigma=q_sigma, run_id=run.id)

# ℓ = (s, G, v, a, t), anchored to the scene, not to the detection id
api.post("/labels", scene_id=s, geom=G,             # Polygon → label row         proposed (E)
         verdict="redraw", detection_hint=d.id)
```

Nothing in geoapps exists yet; geoapps is an independent platform, so its schema starts fresh; PVB is a design reference, not a source of code or data. The payoff of anchoring labels to (scene, geometry) is that a reprocessed archive keeps every analyst decision, and the unmatched ones become the reprocessing quality report.

Until a verdict exists the detection's status is `predicted`. Attribution, notifications, persistence and the export filter it out; only a confirm or a redraw turns it `validated`, and a reject is kept as a labelled false positive.

The detection enters app 1's queue with a priority π\_d. Here p\_d ∈ \[0, 1\] is the calibrated probability that d is a real plume, v\_d ∈ \[0, 1\] the viability of its scene (clear, in swath, retrieval quality passed), Q̂\_d the predicted flux in kg h⁻¹ and Q\_ref a reference flux. n\_d ∈ {0, 1} is 1 when validating d would fire stage 4's notification rule, weighted by β ≥ 0. a\_d is the time since the overpass, τ the notification window and λ how fast priority decays once outside it.

```latex
\pi_d = p_d \, v_d \, g(\hat{Q}_d) \, (1 + \beta n_d) \, u(a_d), \qquad g(Q) = \log\left(1 + \frac{Q}{Q_{\mathrm{ref}}}\right), \qquad u(a) = \begin{cases} 1 & a \le \tau \\ e^{-(a - \tau)/\lambda} & a > \tau \end{cases}
```

An alert fires when π\_d ≥ π₀, or when n\_d = 1 and the window closes within δ (τ − a\_d ≤ δ). Detections outside the window stay in the queue at lower priority, flagged as such; nothing leaves the queue unreviewed.

```python
# Shapes: D queued detections; one value per detection
# π_d = p_d · v_d · g(Q̂_d) · (1 + β n_d) · u(a_d)
pri = priority(p, v, q_hat, would_notify, age,            # (D,) × 5 → (D,)       proposed (E)
               tau=tau, lam=lam, beta=beta, q_ref=q_ref)
# alert ⇔ π_d ≥ π₀ ∨ (n_d = 1 ∧ τ − a_d ≤ δ)
alert = (pri >= pi0) | (would_notify & (tau - age <= delta))   # (D,) → (D,) bool     proposed (E)
```

### Stage 2: labels retrain the segmenter (app 1 → app 4 → pipekit-evaluate → workers)

**TL;DR.** Freeze the labels into a named set, retrain the segmenter, and promote the new version only if it beats the current one on scenes it has never seen.

**Problem.** A frozen label set 𝓛ₖ is split by site into a training part and a golden set 𝓖 of fixed scenes that no model version ever trains on. For a model version m, precision Pₘ and recall Rₘ count matches at IoU ≥ τ, and bₘ is the median relative flux error on matched plumes. Version m′ replaces m only when the gate below holds on 𝓖.

```latex
\mathrm{F1}_{m'} \ge \mathrm{F1}_{m} + \delta, \qquad \lvert b_{m'} \rvert \le \lvert b_m \rvert, \qquad \mathrm{F1} = \frac{2 P R}{P + R}
```

```python
# Shapes: |𝓖| golden scenes, each (N,); n_m detections per scene for version m
# 𝓛ₖ = freeze(labels where t ≤ tₖ)
label_set = db.label_sets.freeze("labels-2026Q4")    # rows → frozen set             proposed (E)
# split by site so no site sits on both sides
train, golden = label_set.split(by="site_id")         # set → (set, set)             proposed (E)

# P, R, b on 𝓖 for old and new versions
report = benchmark(estimators=[seg_v3, seg_v4],       # |𝓖| × (N,) → table          pipekit-evaluate, arguments sketched
                   data=golden, scorers=[f1_at_iou(τ), flux_bias])

# promote only if F1′ ≥ F1 + δ and |b′| ≤ |b|
if report.passes(gate="E2"):
    db.operators.promote("segment", version="v4")     # registry row                 proposed (E)
```

The benchmark half is GeoBench work: the golden set is a GeoBench card with an OSE track, so app 1 supplies the frozen labels, app 4 adds a compare view and a promote action, and neither builds a second evaluation framework.

### Stage 3: attribution as of the scene date (app 2 → workers → geoapps-db)

**TL;DR.** Rank the nearby sources for the confirmed plume, let an analyst pick one, and roll that source up to its facility, asset, operator and government as they were on the day of the scene.

**Problem.** Let o be the plume origin, t the scene time, u the 10 m wind at (o, t) from a named wind product, and φ the bearing the wind blows toward. Candidate source j sits at sⱼ, at haversine distance dⱼ from o, and θⱼ is the bearing from sⱼ to o. A good candidate is close and upwind, so its weight falls with distance and with misalignment; j = 0 is an "unknown source" with a fixed weight w₀.

```latex
w_j = \exp\left(-\frac{d_j^2}{2 \ell^2}\right) \left(\frac{1 + \cos(\theta_j - \varphi)}{2}\right)^{\kappa}, \qquad p(j \mid \text{plume}) = \frac{w_j}{w_0 + \sum_{k=1}^{K} w_k}
```

Here ℓ is a length scale in metres and κ sets how sharply misalignment is penalised. Every link above the source is valid only over a time window, so the roll-up is an as-of query, not a join on current ownership.

```python
# Shapes: K candidate sources within radius r of o; one scene time t
# dⱼ, θⱼ = haversine(sⱼ, o), bearing(sⱼ, o)
cands = db.sources.within(o, radius_m=2_000, as_of=t)    # point → (K,) rows           proposed (F)
# wⱼ = exp(−dⱼ² / 2ℓ²) · ((1 + cos(θⱼ − φ)) / 2)^κ
w = score(cands.geom, o, wind.at(o, t), ell=500, kappa=4)  # (K,) → (K,)               proposed (F)
# p(j | plume) = wⱼ / (w₀ + ∑ₖ wₖ)
p = w / (w0 + w.sum())                                   # (K,) → (K,)                 proposed (F)
db.attributions.propose(d.id, cands.id, p,               # (K,) → K rows               proposed (F)
                        method="auto:v1", source_db="sources@2026-10-01", wind="ERA5")
```

```sql
-- source → facility → asset → operator, government, each valid over a tstzrange
SELECT f.facility_id, a.asset_id, o.org_id AS operator, g.org_id AS government
FROM   attribution.facility_source fs
JOIN   attribution.asset_facility af ON af.facility_id = fs.facility_id AND af.valid @> :t
JOIN   attribution.org_asset o       ON o.asset_id = af.asset_id AND o.role = 'operator'   AND o.valid @> :t
JOIN   attribution.org_asset g       ON g.asset_id = af.asset_id AND g.role = 'government' AND g.valid @> :t
WHERE  fs.source_id = :source_id AND fs.valid @> :t;
```

The vocabulary is the one settled in the extreme-events pages: a facility groups sources, an asset is a government reporting unit, and a government can also link straight to a facility. Storing the source-database snapshot and wind product on each proposal is what lets a 2023 plume be re-attributed against 2023 infrastructure.

### Stage 4: a watched site raises an alert (app 2 → app 3 → workers → watcher)

**TL;DR.** When a validated, attributed source on someone's watchlist becomes persistent or large, raise an alert to the people watching it; outbound notifications come later on the same rule.

**Problem.** For a site observed over T overpasses, N\_valid of them were observable (in swath, clear, above the detection limit) and N\_det showed a confirmed detection. The persistence P is the chance a valid overpass shows a plume. With a flat prior its posterior is a Beta, and the trigger fires on that posterior or on the flux, never on a raw detection.

```latex
P \mid \text{data} \sim \operatorname{Beta}\left(1 + N_{\mathrm{det}},\ 1 + N_{\mathrm{valid}} - N_{\mathrm{det}}\right), \qquad \text{alert} \iff \Pr(P > p_0 \mid \text{data}) \ge 0.9 \ \lor\ \hat{Q} \ge Q_0
```

An alert is a row that is raised, seen, then kept or dismissed; a dismissal with a reason ("not a plume", "wrong source") goes back to app 1 or app 2 as a review request. The later outbound phase reuses the rule and adds the state machine below; sending is always a worker reading an outbox table, so a crash never sends twice.

```
  drafted
     │  analyst review
  reviewed ───────────▶ withdrawn   (attribution reversed)
     │  outbox worker
  sent
     │  read receipt or reply
  acknowledged ───────▶ expired     (no reply by deadline)
     │  structured reply
  responded
     │  verification (stage 5)
  closed: mitigated · not ours · no action
```

```python
# Shapes: T overpasses of one site; W watch rules on that site
# P | data ~ Beta(1 + N_det, 1 + N_valid − N_det)
post = beta(1 + n_det, 1 + n_valid - n_det)              # scalars → distribution        proposed (G)
# alert ⇔ Pr(P > p₀) ≥ 0.9 ∨ Q̂ ≥ Q₀, per watch rule w
for w in db.watches.on(source_id, as_of=t):              # → W rows                      proposed (G)
    if post.sf(w.p0) >= 0.9 or q_hat >= w.q0:
        db.alerts.open(w, source_id, evidence=run.id)    # → row, state "raised"         proposed (G)
db.outbox.enqueue_alerts(channel="in_app")               # worker delivers exactly once   proposed (G)
```

For the later phase: MARS reaches governments through designated focal points and OGMP 2.0 companies directly ([UNEP](https://www.unep.org/topics/energy/methane/how-mars-works)), and the IEA reports that about 12% of its notifications received a response in 2025 ([IEA](https://www.iea.org/reports/responding-to-satellite-notifications-from-the-methane-alert-and-response-system)). Outbound notifications, if they come, will be judged on how easy replying is, not on how they are sent.

### Stage 5: feedback closes the loop (app 3 → app 1, app 2, stage 4)

**TL;DR.** Each dismissal or reply becomes a label or an attribution correction, and any claimed or suspected end of an event is verified by the overpasses that follow it.

**Problem.** A reply r has a type and, for a repair, a date tᵣ. After tᵣ the site has N′\_valid observable overpasses and N′\_det detections. If the site were still emitting at persistence P̂, the chance of seeing no plume at all would be (1 − P̂) to the power N′\_valid. The repair counts as verified when that chance drops below α.

```latex
\text{verified} \iff N'_{\mathrm{det}} = 0 \ \land\ (1 - \hat{P})^{N'_{\mathrm{valid}}} \le \alpha \iff N'_{\mathrm{valid}} \ge \frac{\log \alpha}{\log(1 - \hat{P})}
```

With P̂ = 0.5 and α = 0.05 that is 5 clear overpasses after the repair date.

| Reply | Becomes | Effect |
| --- | --- | --- |
| Repaired on tᵣ | Event end claim | Stage 4 persistence restarts at tᵣ; verification counter opens |
| Not our asset | Rejected attribution label | App 2 re-ranks without that operator link |
| No leak found | Re-review request | Detection goes back to the app 1 queue, flagged low confidence |
| Planned venting | Event cause annotation | Facility gets a cause; persistence still counts it |

Today these replies come from watchers annotating or dismissing alerts; operator replies arrive only with the outbound phase.

```python
# Shapes: N′_valid overpasses after tᵣ; one reply r
# verified ⇔ N′_det = 0 ∧ N′_valid ≥ log α / log(1 − P̂)
need = ceil(log(alpha) / log(1 - p_hat))                 # scalars → int               proposed (G)
feedback = db.feedback.record(n.id, kind="repaired", t_r=t_r)   # → row + label rows    proposed (G)
```

The loop is the reason the four apps share one database: a single reply touches a label (app 1), an attribution (app 2) and a notification state (app 3) in one transaction.

Stages 6 to 8 sit beside the loop rather than in it: stage 6 happens before stage 1, when new data is found, and stage 7 happens beside stage 2, when a researcher tries an algorithm outside the platform; stage 8 replays stages 1 and 3 with one input changed.

### Stage 6: an analyst finds, previews and ingests new scenes (shell explorer → titiler → workers)

**TL;DR.** Search a public catalog for EMIT methane scenes over the well pad, overlay them on the map without copying anything, and ingest the useful ones into a staging collection that is promoted after a look.

**Problem.** A public catalog exposes items i, each with a footprint Fᵢ, a time tᵢ and a validity footprint Vᵢ (where it could have seen a plume). The analyst asks for a box B around the site x and a window \[t₀, t₁\]. Ingesting is worth it when it sharpens a number the platform reports, so the value of a batch is how many valid overpasses it adds at the site.

```latex
I = \{\, i : F_i \cap B \ne \varnothing,\ t_i \in [t_0, t_1] \,\}, \qquad \Delta N_{\mathrm{valid}} = \left\lvert \{\, i \in I : x \in V_i,\ t_i \notin \mathcal{T}_x \,\} \right\rvert
```

Here 𝒯ₓ is the set of overpass times already in the collection. Stage 4's persistence posterior Beta(a, b) has the variance below, so the gain can be shown before ingesting.

```latex
\operatorname{Var}[P] = \frac{a b}{(a + b)^2 (a + b + 1)}, \qquad a = 1 + N_{\mathrm{det}}, \quad b = 1 + N_{\mathrm{valid}} - N_{\mathrm{det}}
```

With 5 detections in 10 valid overpasses the posterior sd of P is 0.139; ten more valid overpasses at the same rate bring it to 0.104.

```python
# Shapes: |I| candidate items; one site x; one staging collection
# I = {i : Fᵢ ∩ B ≠ ∅, tᵢ ∈ [t₀, t₁]}
items = api.get("/explore/search", catalog="nasa-cmr",          # → |I| STAC items          proposed (H)
                collection="EMITL2BCH4ENH", bbox=B, datetime=(t0, t1))   # collection id to verify
# preview: tiles read from the remote asset, nothing copied
layer = api.post("/explore/preview", item=items[0].href)       # → titiler /stac tile URL   proposed (H)
# ΔN_valid = |{i ∈ I : x ∈ Vᵢ, tᵢ ∉ 𝒯ₓ}|
gain = api.get("/explore/gain", items=items, site=x)          # |I| → () int, sd before/after   proposed (H)
# run a registered ETL with typed parameters
job = api.post("/etl/ingest_stac/run",                        # → job row, then a run row  proposed (H)
               params={"items": items.ids, "target": "staging/emit-ch4"})
api.post("/collections/staging/emit-ch4/promote")             # staging → collection       proposed (H)
```

Today every ingest is an engineer running a script with parameters in code. The payoff is that the same ETL an engineer schedules is the one an analyst runs from a form, with the same run tuple, so a trial ingest is never a second, untracked pipeline.

### Stage 7: a researcher tries a new segmenter beside the app (notebook → geoapps-client → api → app 4)

**TL;DR.** Pull the golden-set scenes and their labels to a laptop with a few calls, run a new segmenter, and push its masks back as a private layer to compare with production in the app.

**Problem.** The researcher has a candidate operator f mapping ΔΩ to a mask M̂. For each of S golden scenes s there is the analyst polygon Gₛ and the production mask Mₛ. The quick comparison is the paired IoU difference; the formal decision stays gate E2.

```latex
\Delta_s = \operatorname{IoU}(\hat{M}_s, G_s) - \operatorname{IoU}(M_s, G_s), \qquad \bar{\Delta} = \frac{1}{S} \sum_{s=1}^{S} \Delta_s, \qquad \mathrm{SE} = \frac{\operatorname{sd}(\Delta)}{\sqrt{S}}
```

```python
import geoapps_client as gx                                   # proposed (I)
# Shapes: S golden scenes; each scene H × W = N pixels; masks {0, 1}
gx.login()                                                    # device-code sign-in        proposed (I)
scenes = gx.label_sets.get("labels-2026Q4").golden()          # → S scenes + Gₛ            proposed (I)
for s in scenes:
    # ΔΩₛ, opened lazily through geotoolz-catalog
    dw = gx.open(s.asset("delta_omega"))                      # → (H, W) DataArray          proposed (I)
    # M̂ₛ = f(ΔΩₛ)
    m_hat = my_segment(dw)                                    # (H, W) → (H, W) {0, 1}       researcher's code
    gx.scratch.put(f"seg-try/{s.id}", m_hat)                  # → COG under scratch/<user>/  proposed (I)
# Δ̄ = (1/S) ∑ₛ [IoU(M̂ₛ, Gₛ) − IoU(Mₛ, Gₛ)]
report = gx.compare("seg-try", against="segment@v3", labels=scenes)   # S → table        proposed (I)
gx.show("seg-try", compare_with="segment@v3")                 # opens a swipe view in app 4 proposed (I)

# the other direction: the app's current view as data on disk
dets = gx.detections(bbox=B, as_of="2026-10-01")              # → GeoDataFrame, public GeoParquet   proposed (I)
gx.download("emit-ch4", bbox=B, datetime=(t0, t1), to="data/") # → local COGs, cached       proposed (I)
```

The app gives the reverse path too: an "Open in notebook" action copies a snippet with the current bounding box, time window and layers. A result that looks promising becomes a GeoBench run and then gate E2; nothing pushed from a notebook ever reaches the `nrt` stream.

### Stage 8: what if the wind product changes? (app 4 → registry → workers → sandbox)

**TL;DR.** Rerun the flux and the attribution of the Permian plume with a different wind product, in a private sandbox, and compare both with production without touching it.

**Problem.** The integrated mass enhancement IME is the methane mass over the plume mask M: the sum of ΔΩᵢ times the pixel area Aᵢ, times the molar mass m\_CH₄ = 0.016 kg mol⁻¹. L is a plume length scale in metres and U\_eff the effective wind speed in m s⁻¹, derived from the 10 m wind of the chosen product. With the retrieval and the mask held fixed, a new wind product changes only U\_eff, so the flux ratio is closed form.

```latex
Q = \frac{U_{\mathrm{eff}}}{L} \, \mathrm{IME}, \qquad \mathrm{IME} = m_{\mathrm{CH_4}} \sum_{i \in M} \Delta\Omega_i A_i, \qquad \frac{Q'}{Q} = \frac{U'_{\mathrm{eff}}}{U_{\mathrm{eff}}}
```

The attribution moves too: the new wind direction φ′ changes every weight wⱼ of stage 3 through cos(θⱼ − φ′), so the top candidate can change even when the flux barely does.

```python
# Shapes: one detection d with mask (N,); K candidate sources; one sandbox stream
# Q′ = (U′_eff / L) · IME, same mask, new wind product
run = api.post("/etl/estimate_flux/run",                       # → run row in the sandbox    proposed (J)
               params={"detection": d.id, "wind": "GEOS-FP"},
               stream="sandbox/<user>/wind-test")
# Q′ / Q = U′_eff / U_eff
diff = api.get("/compare", a="nrt", b=run.stream,              # → (Q, Q′, Q′/Q)            proposed (J)
               what="flux", detection=d.id)
# w′ⱼ with φ′ from the new wind; ranking before and after
rank = api.post("/etl/attribute/run",                          # (K,) → (K,) in the sandbox  proposed (J, F)
                params={"detection": d.id, "wind": "GEOS-FP"}, stream=run.stream)
```

Nothing here exists yet. The payoff is that production, an analyst's ingest and a researcher's what-if all run through the same registry; only the stream differs, so adopting a sandbox result means a promotion or a reprocessing run, never copying rows.

## Data placement

Files hold bytes and rows hold relationships: four kinds of data, four homes, and rows always point at files, never the reverse.

| Object | Lives in | Format | Written by | Read by | Changes |
| --- | --- | --- | --- | --- | --- |
| Satellite scenes (Tanager, EMIT, EnMAP, Sentinel-2, Landsat) | Object storage, sparse coverage | COG, or a reference only where the licence forbids a mirror | Ingestion workers | titiler, workers | Never; a reprocessed scene is a new key |
| Scene products (ΔΩ, masks, uncertainty) | Object storage | COG, one per stage | Retrieval and segmentation workers | titiler, apps 1 and 4 | Never; versioned by run |
| Dense cubes (wind, reanalysis, gridded L3/L4 fields) | Object storage | Zarr v3, chunked for both map tiles and time series | Ingestion and reanalysis workers | titiler (xarray backend), workers, browser via zarrita | Append along time |
| File catalog | PostgreSQL, `catalog` schema | pgSTAC items with footprint and per-scene validity mask | Ingestion workers | titiler, workers, api | Append; items are retired, not deleted |
| Reference layers (sources, facilities) | PostgreSQL, `ref` schema; released as GeoParquet | Rows with `valid` time ranges; snapshot id per release | Import jobs from inventories, analyst edits | All apps, workers | Slowly; every edit is a new row version |
| Relationship data (assets, operators, governments, ownership) | PostgreSQL, `attribution` schema | Rows with `tstzrange` validity | App 2 analysts, import jobs | Apps 2 and 3, workers | Edited with history |
| Workflow data (detections, labels, notifications, outbox, feedback) | PostgreSQL, one schema per app | Rows, append-only where possible | Workers, apps 1–4 | Apps 1–4 | Append; status changes are audited |
| Runs and provenance | PostgreSQL, `core` schema | One row per run with the full version tuple | Workers | Everything | Never |
| Public catalog | Object storage, public bucket | GeoParquet + stac-geoparquet index + PMTiles | Export worker, nightly | DuckDB, DuckDB-WASM, GeoLibre, notebooks | Replaced by dated snapshot |
| Staging collections (trial ingests) | Object storage staging/ prefix + pgSTAC collections staging/\* | COG, or reference-only items where the catalog licence says so | Registered ETLs run by analysts | Explorer in app 4 | Promoted into the collection, or expired after a set period (30 days to start) |
| Scratch layers (researcher outputs) | Object storage scratch/\<user>/ + a core.scratch\_layer row | COG or GeoParquet | geoapps-client | The owner and people they share it with | Expires; never exported |
| ETL registry and jobs | PostgreSQL, core schema | ETL name, version, parameter JSON schema; one job row per submission | Workers register ETLs; users submit jobs through the API | Shell forms, workers | Append |
| Public catalog list | PostgreSQL, ref schema | URL, kind, licence, mirror policy (full, crop or reference) | Engineers | Explorer, ETLs | Rarely |
| Sandbox runs (what-if reruns) | Object storage sandbox/\<user>/ + core.run rows with a sandbox stream | Same formats as production outputs | Registered ETLs run from app 4 | The owner in app 4 | Expires; never exported |
| Site observations (detections and non-detections) | PostgreSQL, monitor schema | One row per (site, overpass): observable or not, detection if any, run id | Monitoring pipelines | Persistence, apps 2–4 | Append |
| Pipelines, schedules and jobs | PostgreSQL, core schema | Pipeline definition, trigger, scope; one job per (step, input, version tuple) | geoapps-pipelines enqueues, workers update | App 4, platform operators | Append |

The version tuple on a run names the code version of every operator, the wind product, the source-database snapshot and the label set. Without the wind product in it, a switch from ERA5 to GEOS-FP silently changes every flux.

Incoming inventories arrive as GeoParquet and leave as GeoParquet, which matches the ingestion and production halves of the public catalog. In between they live in Postgres, because notifications, attributions and feedback hold foreign keys to them and analysts edit them under transactions.

**Sizing.** A global methane system at today's scale holds about 2 million scene-location rows, 20,000 plumes and 6,000 sources. Monitoring 6,000 sites on a 5-day revisit adds about 438,000 site rows per sensor per year. All of this is plain Postgres with indexes; the catalog and site-observation tables get monthly partitions once they reach tens of millions of rows, and pixels, not rows, dominate storage.

## Technology stack

Every technology named at the start survives the design constraints; the stack only adds the pieces between them (a generated API client, a vector tile server, a job queue).

| Layer | Choice | Role | Why, or the alternative |
| --- | --- | --- | --- |
| Frontend | React + TypeScript, built with Vite | Shell and apps 1–4 | GeoLibre and deck.gl are React-first, so components and a plugin path carry over; Svelte is lighter but leaves that ecosystem |
| Map | MapLibre GL JS + deck.gl | Basemap, vector, COG and Zarr layers | GeoLibre's own pair |
| In-browser data | DuckDB-WASM + Mosaic | GeoParquet queries, cross-filtered views | Queries go to the data, as in Embedding Atlas |
| API client | Generated with openapi-typescript | Typed calls from the shell | A broken contract fails the build (D1) |
| Backend | FastAPI + Pydantic | HTTP contract, auth, job submission | Python beside GeoStack |
| Data access | SQLAlchemy 2 + GeoAlchemy2 + Alembic | Models, queries, migrations | Async for the API, sync for workers |
| Database | PostgreSQL + PostGIS + pgSTAC + btree\_gist | Relations, workflow, file catalog | One person or a team (M1) |
| Raster serving | titiler (COG, pgSTAC mosaics) + titiler.xarray (Zarr) | Tiles and point values | Also FastAPI, so it mounts beside the API |
| Live vector tiles | Martin, or TiPg | PostGIS layers to MapLibre | Martin is written in Rust: a first Rust component to run and read before writing any |
| Jobs | Postgres job table (a library such as procrastinate), Dagster later | Pipelines (K) and app jobs | No new service until reanalysis needs one |
| Rasters on disk | COG for sparse scenes, Zarr v3 for dense cubes | Object storage | Range reads from browser and server alike |
| Tables on disk | GeoParquet in and out, PMTiles for maps | Reference data, exports, downloads | DuckDB reads it everywhere |
| Analytics | DuckDB over GeoParquet; DuckLake optional | App 4 and notebooks | Keeps heavy reads off Postgres |
| Compute | GeoStack (JAX, xarray, georeader) in workers | Steps 4–7 of the pipeline | Unchanged |
| Local install | Docker Compose | The one-person profile | Same images as the team profile |

Rust stays out of the core. TypeScript is used from day one in the shell; Rust enters later where it earns its place, such as a WASM kernel or a hot path in a worker.

## What exists today

Most of the compute already exists in GeoStack; what is missing is everything between a computed plume and a person acting on it. This inventory is drawn from the design chats of 28 Sep to 7 Oct 2026, not from a fresh read of the repos, so gate A0 starts with that read.

| Piece | Defined in | Used by | Verdict |
| --- | --- | --- | --- |
| Scene operators on `GeoTensor`, windowed COG reads | geotoolz, georeader | Workers for apps 1 and 2 | **Reuse.** Already pure operators; keep I/O in worker adapters |
| STAC-aware catalog queries | geotoolz-catalog | Workers, notebooks | **Reuse.** Point it at pgSTAC instead of a file catalog |
| xarray lane for Zarr cubes (wind, reanalysis) | xrtoolz | Workers (wind at plume origin, stage 3) | **Reuse.** Wind sampling is the one new function |
| Flux estimation and plume forward model | plumax | Workers (stage 1) | **Reuse.** Its version enters the run tuple |
| Persistence and total emission as a thinned point process | xtremax | Workers (stage 4, later) | **Reuse later.** The Beta model ships first; the point process replaces it once the mark-dependent thinning gap is closed |
| Benchmark runner, golden sets, scorers | pipekit-evaluate, GeoBench cards | App 4 promotion gate | **Reuse.** App 4 adds a compare view and a promote action, not a second evaluator |
| Plume detections backend and viewer | PVB / PVFE (FastAPI + Next.js on Azure App Service) | Seed for geoapps-db and the shell | **Reference only.** geoapps is an independent platform, so PVB informs the design but contributes no code, data or credentials |
| Entity vocabulary, persistence model, roll-up with uncertainty | Extreme-events framework pages 1–6 | Apps 2 and 3 | **Reuse as spec.** Detection → source → facility → asset → operator or government |
| Four-part split: products, labeling, attribution, reanalysis | GeoLibre stack architecture chat | This plan | **Reuse.** Parts 2 and 3 become apps 1 and 2; app 3 is new; reanalysis stays a worker concern |
| Readers for other people's catalogs: a read\_window protocol with georeader, rioxarray and odc-stac adapters | geotoolz-catalog (planned) | Workstreams H and I | Build, then reuse. The explorer's ingest and the client's gx.open both need it |
| Notebook map showing the same layers | GeoLibre Python package (geolibre.Map) | Workstream I | Reuse. It loads COG and GeoParquet URLs, so platform tiles and exports open in a notebook unchanged |
| Six-layer discovery pipeline: inventory, selection, raw, staging, raw products, downstream products | Extreme-events framework page 3 | Workstream K | Reuse as spec. Its layers become the discovery pipeline's steps |

Five things exist nowhere yet: the relational model for assets, operators and governments with time-bounded links; the notification state machine with its outbox; a shell that shows COG, Zarr and GeoParquet layers together; a registry that turns ETL scripts into forms; and a client that moves data and layers between a notebook and the app.

## Workstream A: one database, one data-access package

All relational data lives in one PostgreSQL + PostGIS instance, and one Python package, geoapps-db, owns its tables, migrations and queries.

Recommended: SQLAlchemy 2 typed models with GeoAlchemy2 for geometry, Alembic for migrations, and Pydantic schemas only at the API boundary. Alternative: SQLModel, which merges table and API classes; it is quicker to start but ties the public contract to the table layout.

| Object | Lives in | Name | Kind |
| --- | --- | --- | --- |
| Schemas | PostgreSQL | `core`, `catalog` (pgSTAC), `ref`, `review`, `attribution`, `notify` | Postgres schemas |
| Tables | geoapps-db `models/` | `Run`, `Detection`, `Label`, `LabelSet`, `Source`, `Facility`, `Asset`, `Org`, `OrgAsset`, `Attribution`, `Notification`, `Outbox`, `Feedback` | ORM classes |
| Queries | geoapps-db `repo/` | `sources.within`, `attributions.propose`, `notifications.open`, `feedback.record` | functions |
| Migrations | geoapps-db `migrations/` | one Alembic revision per change | scripts |

1. **Start from the extreme-events data model.** Pages 4 and 5 of that design already define detections, sources, facilities, assets and events; the first migration implements them.
2. **Write the spine before the apps.** `core.run`, `ref.source`, `ref.facility` and `review.detection` land first, because every later table points at them.
3. **Make time a column, not a convention.** Every link that can change (facility to source, asset to facility, org to asset) carries a `valid tstzrange`, and an exclusion constraint forbids two overlapping links of the same role.
4. **Never update in place.** Redraws, ownership changes and status changes add rows chained by `supersedes`, so history is a query. With the validity ranges of step 3 this also answers "what did we believe on date X": validity says when something was true in the world, row creation says when we recorded it.
5. **One role per process.** The API, each worker kind and the export job connect as separate Postgres roles with grants per schema.

```python
# Shapes: rows only; one OrgAsset row per (org, asset, role, validity window)
# Today: nothing; ownership lives in spreadsheets
# After:
class OrgAsset(Base):                                        # proposed (A)
    __tablename__ = "org_asset"; __table_args__ = (
        # no two operators of one asset over overlapping time
        ExcludeConstraint(("asset_id", "="), ("role", "="), ("valid", "&&"), using="gist"),
        {"schema": "attribution"})
    org_id:   Mapped[int] = mapped_column(ForeignKey("attribution.org.id"))
    asset_id: Mapped[int] = mapped_column(ForeignKey("attribution.asset.id"))
    role:     Mapped[str]                                    # operator | owner | government
    valid:    Mapped[Range[datetime]] = mapped_column(TSTZRANGE)   # [t_start, t_end)
    source:   Mapped[str]                                    # where the link came from
```

The exclusion constraint needs the `btree_gist` extension; it is the database, not the app, that refuses a second operator for the same window.

## Workstream B: the public catalog is a one-way GeoParquet export

Optional per instance: users, notebooks and GeoLibre read dated GeoParquet snapshots of validated data on object storage; nothing outside the platform queries Postgres, and nothing is written back. An instance holding private data simply never enables it.

| Object | Lives in | Name | Kind |
| --- | --- | --- | --- |
| Detections, sources, facilities | public bucket `catalog/<date>/` | `detections.parquet`, `sources.parquet`, `facilities.parquet` | GeoParquet, spatially sorted, with a bbox column |
| Scene index | same | `items.parquet` | stac-geoparquet |
| Map layers | same | `detections.pmtiles` | PMTiles |
| Current pointer | `catalog/latest.json` | the newest date | JSON |

1. **Export from views, not tables.** A `public_*` view per file fixes the published columns, so a schema change inside geoapps-db never leaks.
2. **Write dated, then flip.** Each run writes `catalog/<date>/`, validates it (gate B1), and only then moves `latest.json`.
3. **Index scenes with stac-geoparquet.** It converts between pgSTAC and GeoParquet, so the scene index is one call, not a new serializer.
4. **Accept inventories the same way.** Incoming facility inventories arrive as GeoParquet in `ingest/` and load through geoapps-db import jobs.

Recommended: plain dated GeoParquet for anything public. Alternative: DuckLake with Postgres as its catalog, which adds snapshots and time travel over Parquet; it suits internal analytics better than public release, because outside readers then need the DuckLake extension.

## Workstream C: rasters are served by titiler, not stored in the database

Sparse scene COGs and dense Zarr cubes stay on object storage, and one titiler app serves both; Postgres holds only their STAC items, footprints and validity masks.

| Object | Lives in | Name | Kind |
| --- | --- | --- | --- |
| Single scenes and products | titiler `/cog` | COG tiles, point and statistics endpoints | router |
| Scene mosaics by query | titiler-pgstac `/searches` | mosaic over pgSTAC items | router |
| Dense cubes | titiler.xarray `/md` | Zarr tiles by variable and time | router |
| Per-scene validity | pgSTAC item properties | clear, in-swath, above-limit footprint | geometry |

1. **Write COGs one way.** 512 px internal tiles, overviews, ZSTD or DEFLATE, nodata set; geotoolz and georeader already write them.
2. **Chunk Zarr for its main reader.** Map tiles want spatial chunks (time 1, 512 × 512); time series want long time chunks. Start with spatial chunks and add a rechunked copy only for the cubes app 4 plots as series.
3. **Store validity with the scene.** Persistence in stage 4 needs N\_valid, and that only exists if every ingested scene records where it could have seen a plume.
4. **Let the browser read small cubes.** zarrita.js can read a Zarr store directly into a deck.gl layer, which suits cubes small enough to fetch whole.

## Workstream D: one frontend shell hosts four apps

One React + TypeScript shell owns the map, layers, time and tables, styled after GeoLibre; apps 1–3 are routes that add panels and workflows to it.

GeoLibre is the reference for look and layer handling: React, TypeScript and MapLibre GL JS for the UI and map, deck.gl for GPU layers, DuckDB for queries in the browser, and a TypeScript plugin system. It streams remote GeoParquet and COG with no server, which is exactly how the public catalog of workstream B should feel.

| Object | Lives in | Name | Kind |
| --- | --- | --- | --- |
| Map, layer panel, time slider, attribute table | geoapps-web `shell/` | `MapView`, `LayerPanel`, `TimeBar`, `AttributeTable` | React components |
| Layer types | `shell/layers/` | `CogLayer`, `ZarrLayer`, `ParquetLayer`, `VectorTileLayer` | MapLibre or deck.gl layers |
| API client | `shell/api/` | types generated from the FastAPI OpenAPI schema | generated TypeScript |
| App 1 | `apps/review/` | review queue, verdicts, label editor, label sets | route |
| App 2 | `apps/attribution/` | candidate list, entity graph, as-of slider | route |
| App 3 | `apps/notify/` | notification board, reply form, verification view | route |
| App 4 | apps/research/ | explorer, catalog views, scratch layers, swipe compare, evaluation reports, promotion | route |

1. **Generate the client from FastAPI.** The OpenAPI schema is the contract; regenerating TypeScript types on every API change makes a broken contract a compile error.
2. **One layer per format.** COG and Zarr through titiler tiles, GeoParquet through DuckDB-WASM, live vector data through PostGIS vector tiles.
3. **Linked views for the catalog.** App 4's detection table, histograms and map cross-filter each other, the Mosaic pattern behind Apple's Embedding Atlas.
4. **The reply form needs no account.** Recipients of app 3 answer through a signed, single-use link, because a login wall is one more reason not to reply.

Recommended: an own shell that copies GeoLibre's patterns, because the apps need sign-in, multi-user writes and workflow panels that a local-first GeoLibre does not have. Alternative: build each app as a GeoLibre plugin that calls the API; that gives the GeoLibre look for free but ties every release to its plugin interface and its no-server model.

## Workstream E: app 1 gives a person the final say on every predicted plume

No predicted plume goes downstream until a person has validated it. Each verdict is a label that belongs to a scene and a geometry, never to a detection id, and only frozen label sets may train or judge a model.

| Object | Lives in | Name | Kind |
| --- | --- | --- | --- |
| Label | `review.label` | scene, polygon, verdict, analyst, time, optional detection hint | table |
| Label set | `review.label_set` | name, freeze time, content hash, split | table |
| Review queue | `review.queue` | detections plus sampled model-negative scenes, with a reason | view |
| Re-matching | geoapps-workers | `rematch_labels(old_run, new_run, tau)` | job |

### E1: labels survive reprocessing

1. **Anchor to (scene, geometry).** Stage 1's IoU rule carries labels to new detections; unmatched labels go to a report, not the bin.
2. **Pin analyst decisions.** A reprocessed detection never overwrites a confirmed or redrawn one; it is stored beside it and flagged "algorithm disagrees".

### E4: nothing predicted leaves without a verdict

1. **Status is a column.** Every detection carries `predicted`, `validated` or `rejected`; only a person's confirm or redraw sets `validated`.
2. **Downstream reads filter on it.** Attribution, notifications, persistence counts and the export query `validated` rows only, through views that cannot be widened by a parameter.
3. **The model ranks, it never decides.** Scores order the queue and batch obvious candidates for quick review; no score, however high, skips the verdict.
4. **Record who decided.** Each verdict stores the analyst, the time and the imagery they saw, so a notification can always cite the person behind it.

### E5: alerts point analysts at what matters first

1. **One score, stated openly.** Stage 1's π\_d ranks the queue; its inputs and weights show beside each item, so an analyst can see why it is near the top.
2. **Two kinds of alert.** High priority (π\_d ≥ π₀), and window closing (a plume that would trigger a notification and has less than δ left).
3. **In-app first, then the outbox.** Alerts land in an analyst inbox in app 1; email or chat delivery reuses workstream G's outbox with an internal audience.
4. **Late is not lost.** Detections past the window keep their place at reduced priority and are still validated, because they still count for persistence and labels.

### E3: review what the model did not show

1. **Sample for learning value.** The queue mixes low-confidence detections, new sensors and scenes with no detection at known emitters, because missed plumes are the rarest and most valuable labels.
2. **Record why a scene was queued.** The reason column lets recall be estimated from the sampled negatives instead of guessed.

## Workstream F: app 2 makes attribution a scored, time-aware proposal

Attribution is a ranked list of candidates that an analyst confirms, and every link it uses is valid only over a time window.

| Object | Lives in | Name | Kind |
| --- | --- | --- | --- |
| Candidate proposal | `attribution.attribution` | detection, source, score, method, source-db snapshot, wind product, status | table |
| Entity links | `attribution.facility_source`, `asset_facility`, `org_asset`, `org_facility` | each with `valid tstzrange` | tables |
| Organisations | `attribution.org` | operators, owners, governments, regulators, with focal points | table |
| Roll-up | `attribution.as_of(source_id, t)` | facility, asset, operator, government at time t | SQL function |

1. **Score, then confirm.** Stage 3's weights rank candidates; the analyst confirms one or marks "unknown source", and both outcomes are labels.
2. **Pin the inputs.** Each proposal names its source-database snapshot and wind product, so re-attribution is a rerun, not an argument.
3. **Keep conflicting inventories.** When two inventories disagree about a facility's operator, both links are stored with their provenance and one is marked preferred.
4. **Link governments to facilities directly.** The extreme-events vocabulary needs a government reachable without an asset, for facilities outside any reporting unit.

## Workstream G: app 3 runs watchlists and alerts now, outbound notifications later

Watchlists and alerts ship first; outbound notifications to operators or governments are a later phase that reuses the same rules, with audited states, an outbox and structured replies.

| Object | Lives in | Name | Kind |
| --- | --- | --- | --- |
| Notification | `notify.notification` | source, recipients, state, deadline, evidence snapshot | table |
| State history | `notify.transition` | from, to, by, time, reason | table |
| Outbox | `notify.outbox` | channel, payload, attempts, sent time | table |
| Feedback | `notify.feedback` | type, free text, repair date, links to labels and attributions | table |
| Response rate | `notify.response_rate` | by country, operator and quarter | view |
| Watch | notify.watch | user, target (site, facility, region or kind), condition | table |
| Alert | notify.alert | watch, evidence run, state (raised, seen, kept, dismissed), reason | table |

### G1 (later phase): states and the outbox

1. **Allow only listed transitions.** Stage 4's diagram is the whole state machine; a database check refuses any other move.
2. **Send from the outbox.** A worker sends, retries and marks rows sent, so a crash never sends twice and the API never blocks on email.
3. **Freeze the evidence.** The notification stores the detections, imagery links and attribution it was based on, so a later reprocessing cannot change what was sent.

### G2 (later phase): replies close the loop

1. **A form, not an inbox.** The reply link opens a short form whose choices are stage 5's reply types, plus free text and a repair date.
2. **One transaction per reply.** Recording feedback writes the label, the attribution change and the state transition together.
3. **Verify claimed repairs.** A repair claim opens stage 5's counter; the notification closes as mitigated only when the overpass condition holds.

### G3: watchlists and alerts first

1. **A watch is a rule.** A user watches a site, facility, region or event kind with a condition: any validated detection, persistence above p₀, flux above Q₀, or an event ending.
2. **Alerts read validated rows only.** Watch rules query the same validated views as everything downstream (E4).
3. **Dismissals are labels.** "Not a plume" sends the detection back to app 1's queue and "wrong source" sends the attribution back to app 2, which is the reinforcement loop.
4. **One outbox from day one.** In-app and email alerts go through `notify.outbox`, so the outbound phase later adds an audience, not a new system.

## Workstream H: ETLs become typed, callable jobs behind a catalog explorer

Every ETL is registered with a typed parameter schema, so the ETL an engineer schedules is the one an analyst runs from a form; trial ingests land in staging and are promoted or expire.

| Object | Lives in | Name | Kind |
| --- | --- | --- | --- |
| Public catalog list | `ref.public_catalog` | URL, kind (STAC API, static STAC, bucket), licence, mirror policy | table |
| ETL registry | geoapps-workers `etl/` + `core.etl` | `@etl(name, params, writes)` | decorator + table |
| Job | `core.job` | ETL, parameters, user, status, run id | table |
| Explorer | geoapps-web `explore/` | search panel, footprint layer, preview, gain, ingest form | route |
| Staging collection | pgSTAC `staging/<name>` | items with an expiry date | collection |

### H1: one registry for scheduled and user-run ETLs

1. **Declare once.** An ETL is a function with a Pydantic parameter model; the decorator records its name, version and what it writes.
2. **Forms from schemas.** The API lists registered ETLs with their JSON schemas, and the shell renders a form from each; nothing unregistered can run.
3. **Same run tuple.** A user-run job writes the same `core.run` row as a scheduled one, plus the user.
4. **Limits per role.** Analysts may run preview and ingest ETLs up to a size limit; heavier ones need an engineer's approval.

### H2: preview, then stage, then promote

1. **Preview reads in place.** titiler's STAC endpoint tiles a remote item by its URL, and the explorer overlays it beside the site's detections; nothing is copied.
2. **Show the gain.** Stage 6's ΔN\_valid and posterior sd turn "is it worth it" into a number before anything is ingested.
3. **Stage, then promote or expire.** Ingests land in a staging collection; promotion moves the items into the collection, where they count for persistence and the export.
4. **The licence decides the copy.** Each catalog's mirror policy (full, crop to site, reference only) is applied by the ingest ETL, never chosen per click.

```python
# Shapes: |I| items in; |I| COGs or references and |I| pgSTAC items out
# Today: a script with parameters in code, run by an engineer
items = search_emit(bbox=PERMIAN, start="2026-09-01")
for i in items: copy_to_blob(i); register(i)

# After: one registered ETL, run from a schedule or from the explorer's form
class IngestParams(BaseModel):                               # proposed (H)
    items: list[str]                                         # STAC item hrefs
    target: str                                              # "staging/emit-ch4"
    crop_to: Polygon | None = None                           # site box, when the licence asks

@etl(name="ingest_stac", params=IngestParams, writes=["catalog", "object_storage"])   # proposed (H)
def ingest_stac(p: IngestParams, ctx: RunContext) -> Run:
    # I → |I| assets copied or referenced, |I| pgSTAC items written through geoapps-db
    ...                                                      # arguments sketched
```

Recommended: a job table in Postgres that workers claim with `SELECT … FOR UPDATE SKIP LOCKED`, which needs no new service. Alternative: an orchestrator such as Prefect or Dagster whose deployments the API triggers; worth it once ETLs chain into multi-step pipelines with retries.

## Workstream I: a researcher client moves data and layers between a notebook and the app

geoapps-client is a small Python package over the API and the public catalog: a few helpers pull scenes, labels and detections, and results go back as private scratch layers.

| Object | Lives in | Name | Kind |
| --- | --- | --- | --- |
| Client | geoapps-client | `gx.login`, `gx.search`, `gx.open`, `gx.download`, `gx.detections`, `gx.label_sets` | functions |
| Scratch layers | `core.scratch_layer` + `scratch/<user>/` | `gx.scratch.put`, `gx.show`, `gx.compare` | functions + table |
| App to notebook | geoapps-web | "Open in notebook" snippet with box, time and layers | action |
| Notebook map | GeoLibre Python package | `geolibre.Map()` loaded with platform URLs | widget |

1. **Thin over the API.** The client wraps a Python client generated from the same OpenAPI schema as the TypeScript one, and opens arrays through geotoolz-catalog and xrtoolz, so results arrive as GeoTensor or xarray.
2. **Public reads need no sign-in.** `gx.detections` and catalog search read the public GeoParquet with DuckDB; labels, staging and scratch need a token.
3. **Device-code sign-in, signed downloads.** A notebook gets a user-scoped token; downloads come from short-lived signed URLs into a local cache.
4. **Scratch layers are private and temporary.** `gx.scratch.put` writes a COG or GeoParquet under the user's prefix and registers it; `gx.show` opens it in the user's app session, optionally as a swipe against a production layer.
5. **Open in notebook.** The app copies a snippet with the current view, so the trip from app to notebook is one paste.

Recommended: researchers run their code locally or on a shared JupyterHub and push results back. Alternative: register an experimental operator and run it on platform workers into a sandbox stream; worth it when scenes are too large to download.

## Workstream J: app 4 is where data is explored and algorithms are judged

App 4 is the analysis and research app: it hosts the catalog explorer and researchers' scratch layers, compares model versions on frozen label sets, and owns model promotion.

| Object | Lives in | Name | Kind |
| --- | --- | --- | --- |
| Explorer | `apps/research/explore` | search, preview, gain, ingest form (H) | route |
| Compare | `apps/research/compare` | scratch layers (I), swipe and side by side against production | route |
| Catalog views | `apps/research/catalog` | detection table, histograms and map, cross-filtered | route |
| Evaluation report | pipekit-evaluate run on a frozen label set | P, R, F1 and flux bias per model version | report |
| Operator registry | `core.operator` | name, version, git commit, gate report, status | table |

### J1: promotion needs a golden set

1. **Read labels, never write them.** App 4 reads frozen label sets from app 1; it cannot create or change a verdict.
2. **Promote through pipekit-evaluate.** Stage 2's gate runs on the golden set and the report is attached to the registry row; workers only run promoted versions.
3. **Promotion changes workload, not truth.** Every plume still needs a human verdict, so a new model changes what analysts see and how much they miss, never what is published. That is why this gate can sit with researchers.

### J2: viewing is part of research

1. **Predicted plumes are visible here, marked.** App 4 may show predicted and rejected detections for analysis, with their status always on screen; production views never do.
2. **Recall needs the negatives.** The model-negative scenes app 1 samples (E3) are what lets app 4 estimate recall, so both apps use that one sample.

### J3: app 4 reads every layer

1. **What exists and what could.** Ingested collections, staging collections and public catalog footprints from the explorer sit on one map and one time bar.
2. **Entities and outreach, read-only.** Sources, facilities, assets, operators and notifications with their states are visible; app 4 never edits them.
3. **Per-site time series.** For a chosen site: flux with σ over time, validated and predicted detections, valid overpasses, and stage 4's persistence posterior drawn as a band through time.
4. **Status always on screen.** Every layer says whether its rows are validated, predicted, staging, scratch or sandbox.

Who may see which layer is deferred to the authentication design; until then app 4 assumes an internal user.

### J4: what-if reruns go to a sandbox stream

1. **Rerun through the registry.** A what-if is a registered ETL or operator run with overridden parameters (wind product, segmentation threshold, ℓ and κ, the persistence prior), never ad hoc code on platform workers.
2. **One sandbox stream per user.** Outputs land in `sandbox/<user>/<name>` with their own run rows, and never touch `nrt`, labels, notifications or the export.
3. **Diff, then decide.** App 4 shows production and sandbox side by side for masks, fluxes, attribution rankings and persistence (stage 8).
4. **Same limits as ingest.** Sandbox runs share the per-role size limits of H1 and expire like scratch layers.

This replaces sub-decision E2 from the earlier draft: promotion moved from app 1 to app 4, and E2's gate is now J1.

## Workstream K: scheduled pipelines share one set of primitives

Discovery, monitoring, reanalysis and backfill are pipelines built from the same registered steps; they differ only in what triggers them, what scope they cover and which stream they may write.

| Family | Trigger | Scope | Writes to | Clock | What it adds |
| --- | --- | --- | --- | --- | --- |
| Discovery | Catalog poll or push event | Areas of interest, since the last poll | `nrt` | Minutes to hours after acquisition | New candidate plumes (stage 1) |
| Monitoring | Each overpass of a known site | The site list | `nrt` + `monitor` | Per overpass, every few days | Detections and non-detections, N\_valid, persistence (stage 4) |
| Reanalysis | Manual, per frozen version tuple | Archive region × time range | `reanalysis-<id>` | Rare, weeks of compute | A consistent record and re-matched labels |
| Backfill | Manual, per new site, sensor or area | The new ground, back in time | `nrt`, only where it has no rows | Occasional | History for things added late |

The split matters because each family answers a different question. Discovery asks what is new anywhere; monitoring asks what happened at the places we already watch, including when nothing did; reanalysis asks what the whole record says under one fixed set of versions. Backfill is a reanalysis that uses the current production tuple and only fills gaps.

| Primitive | Lives in | Name | Kind |
| --- | --- | --- | --- |
| Step | geoapps-workers `etl/` | any `@etl` function (H1), built from GeoStack operators | registered ETL |
| Scope | geoapps-pipelines | `Scope(aoi, sites, window, sensors)` | dataclass |
| Trigger | geoapps-pipelines | `CatalogPoll`, `SiteOverpass`, `Cron`, `Manual` | classes |
| Stream | `core.run.stream` | `nrt`, `reanalysis-<id>`, `sandbox/<user>/<name>` | column |
| Run | `core.run` | the full version tuple | table |
| Pipeline | geoapps-pipelines + `core.pipeline` | ordered steps + trigger + scope + stream | definition |

1. **One step registry.** Pipelines are ordered lists of registered ETLs; a step never knows which family runs it, and the same steps serve app 4's what-ifs (J4).
2. **Idempotent by key.** Each step's output is keyed by (step, input id, version tuple); rerunning a key is a no-op, so a crashed backfill resumes where it stopped.
3. **Monitoring writes non-detections.** For each overpass of a known site it records whether the site was observable and whether a plume was seen; those rows are what N\_valid counts.
4. **Reanalysis never overwrites.** It writes its own stream under one frozen tuple and re-matches labels by IoU (E1) while `nrt` keeps running.
5. **Everything enters as predicted.** Every family's new detections go to app 1's queue (E4, E5); reanalysis detections matched to an existing verdict inherit it.

```python
# Shapes: S registered steps per pipeline; one Scope per run; streams by name
# shared core: retrieval → ΔΩ, segmentation → M, estimation → Q ± σ_Q
core = [search, select, fetch, retrieve, segment, estimate]        # S registered ETLs (H)        proposed (K)

discovery = Pipeline(core + [score_sources],                       # what is new anywhere
                     trigger=CatalogPoll(every="30min"),
                     scope=Scope(aoi=AOIS, window="since_last"), stream="nrt")         # proposed (K)
# N_valid += observable(site, overpass); N_det += validated plume seen
monitoring = Pipeline(core + [coverage, persistence],              # what happened at known sites
                      trigger=SiteOverpass(sites=SITES),
                      scope=Scope(sites=SITES, window="overpass"), stream="nrt")      # proposed (K)
reanalysis = Pipeline(core + [coverage, persistence, rematch_labels],   # the whole record, one tuple
                      trigger=Manual(),
                      scope=Scope(aoi=AOIS, window=("2019-01-01", "2026-09-30")),
                      stream="reanalysis-2026a", versions=FROZEN_TUPLE)               # proposed (K)
```

Recommended: start with the Postgres job table and one small scheduler process that enqueues discovery polls and site overpasses, then adopt Dagster when reanalysis arrives, since partitioned runs and backfills are what it is built for. Alternative: Prefect from the start, if most pipelines end up event-driven rather than scheduled.

## Workstream L: every phenomenon is an event kind on a shared core

The core stores scenes, detections, events, coverage, entities, labels and runs without knowing what they measure; each phenomenon plugs in as an `EventKind` naming its operators, geometry, marks, linking rule, entities and policies.

| Kind | Data | Detection geometry | Marks | Linked into events by | Attributed to | Told |
| --- | --- | --- | --- | --- | --- | --- |
| Trace-gas plume (CH₄, CO₂, NO₂, SO₂) | Sparse hyperspectral and multispectral scenes, TROPOMI | Polygon + origin point | Flux Q ± σ\_Q | Same source over repeated overpasses | Source → facility → operator, government | Operator, government |
| Oil spill | Sentinel-1 SAR, optical | Polygon | Area, thickness class, estimated volume | Overlap and drift between scenes | Vessel (AIS), platform, pipeline | Coast guard, environment agency, operator |
| Flood | Sentinel-1 SAR and optical against a dry baseline | Polygon (water minus permanent water) | Area, depth where a DEM allows, exposure | Overlap within a basin over days | Basin, admin region | Civil protection |
| Heavy rain | Dense gridded precipitation (IMERG, radar, reanalysis) in Zarr | Polygon per time step, from a cube product | Accumulation, peak rate, return period | Contiguous in space and time | Basin, admin region | Civil protection, hydrological services |
| Tropical cyclone | Geostationary imagery, scatterometer, best-track and model fields | Polygon per snapshot (wind radii) + centre point | Max wind, central pressure, size | Snapshots of one system, linked by the kind's tracker | Landfall regions | Forecast and civil protection services |

None of the five bends the contract. A rain product reduces a cube to a footprint per time step, and a cyclone is an event with many snapshots between its start and end, the same object as a plume seen on many overpasses. How a detection is derived (a cube reduction, a tracker, xtremax return periods) is science inside the kind's steps; the app only sees snapshots grouped into events. This corrects the first version of this section, which treated rain masks and cyclone tracks as new geometry types.

```python
# Shapes: one kind; each detection is one snapshot with geometry G ∈ {Point, Polygon}
@dataclass(frozen=True)
class EventKind:                                 # proposed (L)
    name: str                                    # "ch4_plume", "oil_spill", "flood", ...
    sensors: tuple[str, ...]                     # collections it reads
    geometry: type[Geometry]                     # Point or Polygon; how it is derived lives in steps
    steps: tuple[Step, ...]                      # retrieve → detect → quantify, registered ETLs (H)
    marks: type[BaseModel]                       # what a detection measures, each with σ
    link: Linker                                 # detections → events: same site, overlap or track
    entities: tuple[str, ...]                    # node types it may be attributed to
    priority: Callable[[Detection], float]       # π_d for app 1's queue (E5)
    notify: NotifyRule | None                    # trigger and audience, or none
    publish: PublishPolicy                       # delay, coarsening, or internal only
```

1. **The core never names a phenomenon.** A detection row holds its kind, its geometry and its marks as JSON validated by the kind's model; views per kind give typed columns.
2. **Events are the shared unit.** A kind's linker groups detections into bounded episodes whose start and end are known only within an interval (extreme-events page 5); plume persistence is the plume kind's special case.
3. **Entities are a typed graph.** Facility, vessel, basin and admin region are node types with the time-bounded links of workstream A.
4. **Publication is part of the kind.** Licence limits, such as commercial imagery that may not be redistributed, and any embargo are declared per kind, not improvised.
5. **Adapt the plume pipeline per kind.** The pipeline is designed end to end with plumes, then each kind changes only the steps it must; most steps are shared.

The full pipeline, step by step, and what each kind changes: End-to-end pipeline

## Workstream M: one codebase runs from a laptop to a team, on your own data

geoapps ships as an app, not a dataset: an instance is configured with its data sources, storage, executors and users, and the same code runs as a single-user local install or a shared team deployment.

| Object | Lives in | Name | Kind |
| --- | --- | --- | --- |
| Instance configuration | `geoapps.toml` + environment | sources, storage URLs, executors, licences, users | file |
| Storage | object-store layer | local disk, S3, Azure Blob, GCS through obstore or fsspec | URLs |
| Executor | geoapps-pipelines | `LocalExecutor`, `DockerExecutor`, `BatchExecutor` | classes |
| Local profile | `compose.local.yml` | Postgres + PostGIS + pgSTAC, titiler, api, web, one worker | Docker Compose |
| Team profile | `deploy/` | the same services, managed Postgres, more workers | deployment |

### M1: Postgres in both profiles

1. **One database for one person or many.** Postgres serves a single researcher as well as a team; the local profile runs it in a container, so there is one schema and one migration path.
2. **Single-user mode only switches sign-in off.** Nothing else in the code branches on the profile.

### M2: bring your own data

1. **Sources are configuration.** Public STAC catalogs, private buckets and local folders are all collections with a licence and a mirror policy.
2. **Private data stays private.** titiler and signed URLs serve it, and exports (B) stay off unless the instance enables them.
3. **Licences belong to the instance owner.** The policy fields make each collection's terms explicit; the code enforces them, it does not choose them.

### M3: precomputed outputs, jobs sent to local or cloud compute

1. **Apps show precomputed results.** Nothing heavy runs inside a request.
2. **Jobs go to a configured executor.** The local machine, a container or cloud batch runs the same registered steps (K).
3. **On-the-fly work lives beside the app.** Companion notebooks and scripts use geoapps-client (I), opened from the app with the current view.

```toml
# geoapps.toml for a one-person local instance (example)
[database]
url = "postgresql://localhost:5432/geoapps"

[storage]
root = "file:///data/geoapps"        # or s3://…, az://…, gs://…

[[sources]]
name = "emit-ch4"
kind = "stac"
url = "https://cmr.earthdata.nasa.gov/stac/LPCLOUD"
mirror = "reference"

[[sources]]
name = "my-scenes"
kind = "folder"
url = "file:///data/scenes"
mirror = "full"

[executors]
default = "local"                    # or "docker", "batch"

[auth]
enabled = false                      # single user
```

## Testing and validation gates

Each workstream merges only when its truth tests pass, and stages 3 and 5 of the running example double as closed-form oracles.

| Gate | Workstream | Passes when |
| --- | --- | --- |
| A0 PVB read (retired) | A | Retired: geoapps is an independent platform, so there is no PVB schema to migrate |
| A1 Migration round trip | A | `alembic upgrade head` then `downgrade base` on an empty database leaves 0 schema differences |
| A2 No overlapping owners | A | Inserting 10,000 random operator links yields 0 overlapping rows for one (asset, role); every overlap raises an exclusion violation |
| A3 As-of oracle | A | On a synthetic history with 3 operator changes, `as_of` returns the right operator for 1,000 of 1,000 random dates |
| B1 Export parity | B | GeoParquet row counts equal the `public_*` view counts exactly, and a DuckDB bbox query returns the same ids as PostGIS for 100 random boxes |
| B2 Public isolation | B | The export role can read only `public_*` views; a query on any other schema fails |
| C1 COG tile parity | C | For 100 random native-zoom tiles, titiler values equal a direct windowed read of the COG with 0 difference |
| C2 Zarr tile parity | C | `/md` tiles equal an xarray selection of the same chunk to 1e-6 in float32 |
| D1 Contract | D | The TypeScript client regenerated from the OpenAPI schema compiles with 0 type errors in CI |
| D2 Phone width | D | Every app route renders at 380 px width with no horizontal scroll |
| E1 Label carry-over | E | Reprocessing with identical masks carries 100% of labels; a 1-pixel shift of a 20 × 20 mask (IoU = 380 / 420 ≈ 0.905) carries at τ = 0.5 |
| J1 Promotion | J | A version with lower F1 on the golden set is refused every time, and golden-set scenes and sites overlap training sets in 0 rows |
| F1 Scoring oracle | F | With ℓ = 500 m and κ = 4, a candidate directly downwind gets w = 0, and two upwind candidates at 500 m and 1,000 m have weight ratio e^1.5 ≈ 4.4817 to 1e-6 |
| F2 Reproducible attribution | F | Rerunning a proposal with the same snapshot and wind product returns identical scores, bit for bit |
| G1 Transitions | G | Exactly the transitions in stage 4's diagram succeed; every other ordered pair of states is refused by the database |
| G2 Exactly-once sending | G | Killing the outbox worker at random points over 1,000 sends records 1,000 sends and 0 duplicates |
| G3 Verification arithmetic | G | The overpass count needed is 5 for (P̂ = 0.5, α = 0.05) and 14 for (P̂ = 0.2, α = 0.05) |
| G4 Atomic replies | G | Over 1,000 injected failures, a reply writes its label, attribution change and transition all together or not at all |
| H1 Registry contract | H | Every registered ETL's parameter schema appears in the OpenAPI schema, and 100 invalid form submissions create 0 jobs |
| H2 Preview copies nothing | H | Previewing 50 remote items writes 0 objects to storage and 0 catalog rows |
| H3 Ingest parity | H | For 100 random windows of an ingested COG, values equal a windowed read of the remote source with 0 difference when no reprojection is applied |
| H4 Staging isolation | H | Staging items appear in 0 rows of the nrt stream, persistence counts and public exports until promoted; the same ingest run twice creates 0 duplicate items |
| H5 Gain oracle | H | For (N\_det, N\_valid) = (5, 10) and (10, 20) the explorer reports posterior sd 0.1387 and 0.1043 to 1e-4 |
| I1 Client parity | I | gx.open returns values equal to a direct windowed read with 0 difference, and gx.detections returns the same ids as the API for 100 random boxes |
| I2 Scratch isolation | I | A scratch layer appears in its owner's layer list, in 0 other users' lists and in 0 public exports |
| I3 Local cache | I | A second gx.download of the same box and window transfers 0 bytes |
| I4 Compare oracle | I | On synthetic masks with known overlaps, gx.compare reproduces the paired mean difference to 1e-9 |
| E4 Nothing unvalidated downstream | E | With 1,000 predicted and 0 validated detections, attribution, notifications, persistence counts and the export return 0 rows; validating one returns exactly 1 |
| J2 Read-only everywhere | J | The app 4 role can read every published view, and every write it attempts outside scratch, staging and sandbox is refused by the database |
| J3 Sandbox isolation | J | Sandbox runs appear in 0 rows of the nrt stream, label sets, notifications and public exports |
| J4 Wind-swap oracle | J | With the mask fixed and the effective wind scaled by c, the sandbox flux equals c times the production flux to 1e-6 relative error |
| E5 Priority and alerts | E | Two detections equal except for ages τ and τ + λ have priority ratio e^−1 ≈ 0.3679 to 1e-6, and a synthetic queue of 1,000 raises an alert for every item with n\_d = 1 and τ − a\_d ≤ δ (0 missed) |
| K1 Idempotent steps | K | Running the same discovery window twice creates 0 duplicate items, detections or jobs |
| K2 Non-detections counted | K | A synthetic site with 20 overpasses, 12 observable and 5 with validated plumes, yields N\_valid = 12 and N\_det = 5 exactly |
| K3 One tuple per reanalysis | K | Every row in a reanalysis stream carries the same version tuple (0 exceptions), and the nrt stream gains 0 rows during the run |
| K4 Resumable backfill | K | A backfill killed at a random step and restarted ends with the same rows, row for row, as an uninterrupted run |
| L1 Second kind, no core migration | L | Registering a second kind adds 0 migrations to the core, review and monitor schemas; only its entity types, views and operators are new |
| L2 Marks validated | L | Of 100 detections whose marks fail their kind's schema, 0 are stored |
| L3 Publication policy | L | For a kind with publication delay Δ and grid size g, the export holds 0 events younger than Δ and 0 coordinates finer than g; an internal-only kind exports 0 rows |
| G5 Watch rules fire exactly | G | A synthetic site crossing p₀ once gives each of its watchers exactly 1 alert, and predicted or rejected detections give 0 |
| M1 Same suite, both profiles | M | The full test suite passes on the local Compose profile and the team profile with 0 skipped tests |
| M2 Storage-agnostic steps | M | One pipeline run against local disk, S3 and Azure Blob URLs gives the same outputs with 0 code changes |
| M3 Executor parity | M | A registered step run by the local and the cloud batch executor gives outputs equal to 1e-6 for 10 fixed scenes |

## Sequencing and risks

The spine ships first, then the catalog explorer as the first slice: analysts can use it on day one, it proves workstreams A, C, D and H together, and it writes nothing to production until a promotion. This corrects the first draft, which made app 1's review queue the first slice; app 1 now ships in the same phase.

```
  phase 1   1a  A  spine + L event kinds
            1b  C  raster serving
            1c  K  discovery
      ◆  A1–A3 · C1, C2 · K1 · L2 · M1, M2
          │
  phase 2   2a  D  shell
            2b  B  exports
            2c  I  researcher client
      ◆  D1, D2 · B1, B2 · I1–I3
          │
  phase 3   3a  H  catalog explorer        ★ first slice
            3b  E  app 1 validation
            3c  J  app 4 research
      ◆  H1–H5 · E1, E4, E5 · J1–J4 · I4
          │
  phase 4   4a  F  app 2 attribution
            4b  K  monitoring
      ◆  F1, F2 · K2 · M3
          │
  phase 5   5a  G  app 3 watchlists and alerts
            5b  K  reanalysis and backfill
      ◆  G2, G3, G5 · K3, K4 · L1, L3
```

Same number means the work can run in parallel. The client (I) ships with the shell, because it needs only the API and the public catalog; app 3 waits for labels (E) and the as-of roll-up (F), because a dismissal writes to both.

- **Scope is four apps for a small team.** Building all four at once spreads one person over a platform, four UIs and a notification process. Fallback: ship the shell, app 4's explorer and app 1; apps 2 and 3 run as schema plus admin forms until those are in use.
- **Overlap with the day job.** A personal platform in the same domain as an employer's system can blur what belongs to whom. Fallback: only public data, your own repositories and your own credentials; nothing from PVB or UNEP infrastructure enters geoapps.
- **Imagery licences.** Commercial scenes may not be mirrored or published. Fallback: reference-only STAC items for those sensors, and only derived products in the public catalog.
- **Sensitive rows reach the public bucket.** Notifications and feedback name operators and governments. Fallback: export only from whitelisted `public_*` views, enforced by the export role (gate B2).
- **Reprocessing collides with analyst edits.** A new model version could silently replace a redrawn plume. Fallback: E1's pinning rule, and reprocessed output goes to a new stream.
- **Old scenes lack validity masks.** Without N\_valid, persistence is a detection count. Fallback: those sites show "detections only" and never trigger a persistence notification.
- **The frontend choice churns.** React versus Svelte, own shell versus GeoLibre plugin. Fallback: keep layers as plain MapLibre and deck.gl code, which moves into a GeoLibre plugin unchanged.
- **Learning Rust and TypeScript slows delivery.** Fallback: TypeScript from day one in the shell; Rust only later for a proven hot path such as tile serving.
- **User-run ETLs become a back door.** A form that runs code invites arbitrary parameters and runaway jobs. Fallback: only registered ETLs run, parameters are validated against their schema before a job exists (gate H1), and each role has a size limit.
- **Trial ingests fill the bucket.** Easy ingest means many half-used collections. Fallback: staging expires unless promoted, and the explorer shows the storage cost beside the gain.
- **Scratch layers leak into production.** A notebook result shown next to production can be mistaken for it. Fallback: scratch lives under a per-user prefix, is labelled as scratch in the layer panel, and never reaches an export or the `nrt` stream (gate I2).
- **Validation becomes the bottleneck.** If every plume needs a person, the queue grows with every new sensor. Fallback: the model ranks the queue by flux, site history and confidence, obvious candidates are reviewed in batches, and queue age is tracked like a service level.
- **What-if results are mistaken for production.** A sandbox flux shown beside a production one can be quoted as fact. Fallback: sandbox layers carry their stream name on every view and export path, and gate J3 keeps them out of everything public.
- **Alert fatigue.** Too many alerts and analysts stop reading them. Fallback: tune π₀ on the backlog so alerts stay a small share of the queue, and send the rest as a daily digest.
- **Monitoring misses overpasses.** If a catalog lags, N\_valid undercounts and persistence looks higher than it is. Fallback: monitoring reconciles against the catalog daily and marks missing overpasses unknown, never invalid.
- **The contract is fitted to plumes.** A contract designed around one kind quietly assumes its shape. Fallback: test it on paper against all five kinds in workstream L's table before the core schema freezes (gate L1).
- **Bring-your-own data arrives in any shape.** Users will point the app at formats and catalogs nobody tested. Fallback: every source needs an adapter for steps 2 to 4, and a source without one is refused when it is configured, not halfway through a pipeline.

## Questions to settle

These decide what gets built first; the first one is a gap in the brief.

- [x] **The problems.** Answered: any event that intermittent remote sensing can extract, including other gases, oil spills, floods, rain events and hurricanes. Workstream L turns these into event kinds; sensitive kinds such as conflict events are out of scope.
- [x] **Users per app.** Answered: from one person to a small team, on the same code (M1); outside users wait for the outbound phase and the authentication design.
- [x] **PVB and PVFE.** Answered: geoapps is your own platform, separate from UNEP, and PVB is a design reference only. The licence is still open; MIT would match GeoStack.
- [ ] **Scope of phenomena.** Methane only in v1, or the general event classes from the extreme-events pages from the start?
- [ ] **Sensors in v1.** Tanager, EMIT, EnMAP, Sentinel-2, Landsat: which ones, and which are reference-only?
- [ ] **What "algorithm improvement" covers.** Segmentation only, or retrieval and flux estimation too?
- [x] **Notification channels.** Answered: no outbound notifications yet; watchlists and alerts first, outbound later on the same rules.
- [x] **Hosting.** Answered: local or any cloud, per instance (M); the sign-in provider waits for the authentication design.
- [ ] **Frontend.** React (matches GeoLibre and deck.gl) or Svelte; own shell or GeoLibre plugins?
- [ ] **The first build.** Is the catalog explorer the right first slice, or is app 1's review queue or the notification board more urgent?
- [ ] **Which public catalogs first.** NASA CMR for EMIT, Earth Search for Sentinel-2 and Landsat, Planetary Computer, a commercial provider's STAC? Each needs a licence row.
- [ ] **Who may promote.** Can any analyst promote a staging collection, or only an engineer?
- [ ] **Where researchers run code.** Laptops only, a shared JupyterHub next to the data, or platform workers for big jobs?
- [ ] **Which ETLs are callable.** Ingest and preview only, or also retrieval and segmentation on demand for a chosen scene?
- [ ] **Who may validate.** Any trained analyst, or a second person before a plume can trigger a notification?
- [ ] **What happens to the backlog.** Do unreviewed predictions wait indefinitely, or expire and get re-queued when the site is seen again?
- [ ] **Layer visibility per role (deferred).** Which users may see which layers, for example notifications or commercial imagery? Parked until the authentication design.
- [ ] **The notification window τ.** How long after an overpass is a notification still useful: days, a week?
- [ ] **Analyst alert channels.** In-app only, or email or chat as well?
- [ ] **Reanalysis cadence.** Per model release, yearly, or on demand?
- [x] **The second event kind.** Answered: none singled out; the pipeline is designed with plumes and adapted per kind.
- [ ] **Validation granularity per kind.** Every snapshot (plumes, spills), once per event (a cyclone with hundreds of snapshots), or trusted without review when the source is authoritative (a best track)?

## Sources

- [GeoLibre 1.0 announcement](https://gishub.org/blog/geolibre/), Qiusheng Wu, 10 June 2026: architecture, formats, plugins.
- [DuckLake](https://ducklake.select/): Parquet storage with a SQL catalog, v1.0 in April 2026.
- [stac-geoparquet](https://github.com/stac-utils/stac-geoparquet): converts STAC items between JSON, GeoParquet and pgstac.
- [titiler.xarray](https://developmentseed.org/titiler/packages/xarray/): Zarr and NetCDF tiling for titiler.
- [How MARS works](https://www.unep.org/topics/energy/methane/how-mars-works), UNEP: detect, notify, act, track.
- [Responding to satellite notifications from MARS](https://www.iea.org/reports/responding-to-satellite-notifications-from-the-methane-alert-and-response-system), IEA: about 12% response rate in 2025.
- Design chats: [GeoLibre stack architecture](https://claude.ai/chat/fbff520b-5da6-45ce-b770-b00647ccfeb2), [Geosciences app stack](https://claude.ai/chat/d5d9ee82-9bb9-471c-a833-6ae1de4fe8c2), [GeoML package structure](https://claude.ai/chat/51798b67-4bbf-48b9-8800-a9cc4539f6c0), [GeoStack package structure](https://claude.ai/chat/86fc8f9c-a77b-4363-a669-e7110bea4217), [GeoModels package design](https://claude.ai/chat/aa0a54b4-bba0-4fcf-9ae5-0ac84b964099), [GeoBench design report](https://claude.ai/chat/63bbb5fa-6fee-49e0-8a55-a024f046514a).
