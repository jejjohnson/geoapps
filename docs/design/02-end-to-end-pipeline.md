# End-to-end pipeline: plumes first, then every kind

Companion to [01-design-plan.md](01-design-plan.md) (tab 2 of the design doc).

## Summary

One pipeline of 14 steps carries a scene from a public catalog to an alert, and every event kind runs the same steps. Only five steps are kind-specific: retrieve, detect, quantify, propose sources and link into events. Plumes are designed in full below, and the last section lists what each other kind swaps.

Steps 1 to 10 run on workers with no person involved. Step 11 is a human verdict in app 1. Steps 12 to 14 only ever read validated rows.

## At a glance

```
  PUBLIC CATALOGS  (STAC APIs, provider APIs)
        │
   1  search     new items in the AOIs since the last poll
   2  select     quality, licence, mirror policy
   3  acquire    copy, crop or reference → raw COG
   4  prepare    radiance, cloud and water masks
        │
   5  retrieve   ΔΩ ± σ                        ◀ kind
   6  detect     probability map, mask, polygons   ◀ kind
   7  quantify   Q ± σ_Q, wind from Zarr        ◀ kind
   8  coverage   validity footprint → site rows
   9  propose    candidate sources, scores         ◀ kind
        │
  10  queue      status predicted, priority π, alerts
        │
  11  validate   a person confirms, redraws, rejects (app 1)
        │        ── validated rows only below ──
  12  link       detections → events, persistence  ◀ kind
  13  watch      watch rules → alerts (app 3)
  14  export     nightly GeoParquet, PMTiles
        │
  loop  verdicts + dismissals → label sets
        → retrain → promote (app 4) → steps 5–7
```

Each step is a registered ETL keyed by (step, input, version tuple), so the same steps serve discovery, monitoring, reanalysis, backfill and app 4's what-ifs.

## Steps

Each row is one registered step: what goes in and out, where the output lives, and what it is built from.

| Step | In → out | Stored as | Built from | Status |
| --- | --- | --- | --- | --- |
| 1 Search | AOIs, last poll time → new STAC items | pgSTAC items, inventory stream | geotoolz-catalog, pystac-client | proposed (K) |
| 2 Select | items → items worth acquiring | job rows with a reason | `ref.public_catalog` policy, quality flags | proposed (H, K) |
| 3 Acquire | item → raw scene, crop or reference | `raw/` COG + catalog item | georeader windowed reads | proposed (K) |
| 4 Prepare | raw scene → radiance cube, cloud and water masks | `staging/` COG | geotoolz operators | proposed (K) |
| 5 Retrieve | radiance (B, H, W) → ΔΩ, σ_ΔΩ (H, W) | `products/` COG | matched filter now, rtmx later | proposed (K) |
| 6 Detect | ΔΩ + context → probability map, masks, polygons | `products/` COG + `review.detection` rows | segmenter, promoted version (J1) | proposed (E, J) |
| 7 Quantify | ΔΩ, mask, wind → Q ± σ_Q and S samples | detection marks | plumax IME, xrtoolz wind from Zarr | proposed (K) |
| 8 Coverage | scene validity → one row per watched site | `monitor` site rows | geotoolz masks | proposed (K) |
| 9 Propose | detection, source snapshot, wind → K scored candidates | `attribution.attribution`, status proposed | stage 3 scoring | proposed (F) |
| 10 Queue | detection → status predicted, priority π_d, alerts | `review.queue` | E5 priority | proposed (E) |
| 11 Validate | predicted → validated, redrawn or rejected | `review.label` | app 1 | proposed (E) |
| 12 Link | validated detections → events, persistence | events + `monitor` | kind's linker; xtremax later | proposed (L) |
| 13 Watch | events, persistence → alerts | `notify.alert` | watch rules (G3) | proposed (G) |
| 14 Export | validated views → public files | public bucket | stac-geoparquet, PMTiles | proposed (B) |

No step exists as a platform job yet; the building blocks in the fourth column are the GeoStack pieces each step wraps, and their exact entry points still need the code audit.

## The science steps for plumes (5 → 7)

Steps 5 to 7 turn radiance into a column map, a mask and a flux with uncertainty; everything else in the pipeline is plumbing around them.

**Step 5, retrieve.** Each pixel has a radiance spectrum x ∈ ℝᴮ over B shortwave-infrared bands. The background mean μ ∈ ℝᴮ and covariance Σ ∈ ℝᴮˣᴮ are estimated from cloud-free pixels of the same scene. The target signature t = μ ⊙ k scales the unit methane absorption spectrum k (per mol m⁻²), taken from a radiative transfer model. The matched filter gives the column enhancement and its noise level.

```latex
\widehat{\Delta\Omega} = \frac{t^\top \Sigma^{-1} (x - \mu)}{t^\top \Sigma^{-1} t}, \qquad \sigma_{\Delta\Omega} = \left(t^\top \Sigma^{-1} t\right)^{-1/2}
```

**Step 6, detect.** A segmentation network f_θ maps the enhancement map and a few context bands to a per-pixel plume probability. Connected components above 0.5 become masks M_c, and each detection's p_d is the calibrated probability of its component. Only a promoted model version runs here (J1).

**Step 7, quantify.** Stage 8 of the design plan defines IME and Q. Uncertainty is carried as S Monte Carlo samples, drawing the enhancement within σ_ΔΩ, the wind within its product spread, and L within its estimate; the samples are kept, because aggregation up to facilities and regions needs them.

```latex
Q^{(s)} = \frac{U_{\mathrm{eff}}^{(s)}}{L^{(s)}} \, m_{\mathrm{CH_4}} \sum_{i \in M_c} \Delta\Omega_i^{(s)} A_i, \qquad \hat{Q} = \frac{1}{S} \sum_{s=1}^{S} Q^{(s)}, \qquad \sigma_Q^2 = \frac{1}{S - 1} \sum_{s=1}^{S} \left(Q^{(s)} - \hat{Q}\right)^2
```

```python
# Shapes: B bands; H × W = N pixels; C plume components; S Monte Carlo samples; B_ctx context bands
# μ = mean(x), Σ = cov(x) over cloud-free background pixels
mu, Sigma = background_stats(x, valid=~cloud)              # (B, H, W) → (B,), (B, B)          GeoStack, name to verify
# t = μ ⊙ k
t = mu * k_ch4                                             # (B,), (B,) → (B,)
# ΔΩ̂ = tᵀ Σ⁻¹ (x − μ) / (tᵀ Σ⁻¹ t)
dw = matched_filter(x, mu, Sigma, t)                       # (B, H, W) → (H, W) mol m⁻²        GeoStack, name to verify
# σ_ΔΩ = (tᵀ Σ⁻¹ t)^(−1/2)
dw_sigma = mf_sigma(Sigma, t)                              # (B, B), (B,) → ()
# P(plume)ᵢ = f_θ(ΔΩ̂, context)ᵢ
prob = segmenter(dw, context)                              # (H, W), (B_ctx, H, W) → (H, W)   promoted version (J1)
# M_c = connected components of {i : P(plume)ᵢ > 0.5}
masks = components(prob > 0.5)                             # (H, W) → (C, H, W) {0, 1}
# Q⁽ˢ⁾ = (U_eff⁽ˢ⁾ / L⁽ˢ⁾) · m_CH₄ ∑_{i∈M_c} ΔΩ⁽ˢ⁾ᵢ Aᵢ
q = ime_flux(dw, dw_sigma, masks, wind, n_samples=S)       # → (C, S) kg h⁻¹                  plumax, name to verify
# Q̂ = mean over s, σ_Q = sd over s
q_hat, q_sigma = q.mean(-1), q.std(-1, ddof=1)             # (C, S) → (C,), (C,)
```

Today these pieces live in GeoStack and plumax as library code; the pipeline adds only the step wrappers, the run tuple and the storage of each output.

## Clocks

The four pipeline families run different slices of the same 14 steps, and only step 11 ever needs a person.

| Family | Steps it runs | Trigger | Where a person comes in |
| --- | --- | --- | --- |
| Discovery | 1–10 | Catalog poll | Step 11 for every new detection |
| Monitoring | 1–10 for known sites, step 8 even when nothing is detected, then 12 | Each overpass of a watched site | Step 11 for any new detection |
| Reanalysis | 3–10 and 12 over the archive, in its own stream | Manual, per frozen version tuple | Step 11 only for detections that match no existing verdict |
| Backfill | 1–10 and 12 for new ground | Manual, per new site, sensor or area | Step 11 for every new detection |

## Fitting the other kinds

Each kind swaps the five kind-specific steps and keeps the rest; a kind that reads a ready-made product skips step 5 rather than changing the pipeline.

| Kind | 5 Retrieve | 6 Detect | 7 Quantify | 9 Propose | 12 Link |
| --- | --- | --- | --- | --- | --- |
| Other gases (CO₂, NO₂, SO₂) | Same matched filter with that gas's absorption, or a TROPOMI L2 column as input | Same segmenter, retrained per gas | IME or cross-sectional flux; lifetime correction for NO₂ | Same source graph: power plants, smelters, volcanoes | Per source, as for methane |
| Oil spill | SAR backscatter contrast instead of a gas column | Segmenter on SAR, with a look-alike filter for calm water | Area, thickness class, volume | Vessels (AIS), platforms, pipelines | Overlap and drift between passes |
| Flood | Water index or SAR backscatter against a dry reference | Water minus permanent water | Area, depth from a DEM, exposure | Basin, admin region | Overlap within a basin over days |
| Heavy rain | Skipped: the input is a precipitation product in Zarr | Footprint where accumulation exceeds a threshold or return period | Accumulation, peak rate, return period (xtremax) | Basin, admin region | Contiguous in space and time |
| Tropical cyclone | Skipped, or an intensity product | Centre and wind radii per snapshot | Max wind, central pressure, size | Landfall regions | The snapshots of one system, joined by the tracker |

Steps 1–4, 8, 10, 11, 13 and 14 and the retrain loop are unchanged for every kind. Steps 3 and 4 vary with the sensor (SAR calibration and speckle filtering, for example), not with the kind, so every kind using a sensor shares them.

## Design constraints

These answers fix the data model and the technology choices; build-order details (first sensor, areas of interest) are left to the build.

| Question | Answer | What it decides |
| --- | --- | --- |
| How many people write at once? | One person to a small team | Postgres in both cases; the local profile runs it in a container (M1) |
| Public or private data? | Both; each instance brings its own | Sources are configuration; titiler and signed URLs serve private data; exports are off by default (M2, B) |
| Compute on demand or precomputed? | Precomputed, with jobs sent to local or cloud compute | Executors in configuration; on-the-fly work in companion notebooks (M3, I) |
| What did we believe on date X? | Covered by the current design | Validity ranges plus append-only rows; no separate history tables (A) |
| How big is a year? | Small at first; a global methane system today holds about 2 M scene-location rows, 20 k plumes and 6 k sources | Plain Postgres with indexes; monthly partitions for the catalog and site observations at tens of millions of rows |
| Aggregation in SQL or in Python? | Python, in jobs and notebooks, following from the compute answer | Monte Carlo samples stay in files beside each detection; the database holds Q̂ and σ_Q |
| Web only, or desktop too? | Web only | One web build; the local profile on localhost covers a lone researcher, offline included, and a desktop shell stays possible later |
