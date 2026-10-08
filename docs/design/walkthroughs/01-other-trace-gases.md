# Walkthrough: other trace gases (CO₂, NO₂, SO₂)

The closest kind to methane: a plume from a point source, seen from space, quantified as a flux, attributed to a facility.
What changes is the gas's spectroscopy, its lifetime in the atmosphere, and the sensors that can see it.

## 1. The problem

Power plants, steel works and smelters emit CO₂ and NO₂; smelters and volcanoes emit SO₂.
Regulators and researchers want to know how much a given facility emits, whether it matches what was reported, and whether it changes after a retrofit or a shutdown.

**Running example (illustrative numbers).** A coal power plant seen by TROPOMI on a clear day: an NO₂ plume stretches 60 km downwind under a 5 m s⁻¹ wind.
The same plant is visible to a CO₂-sensitive imaging spectrometer twice a month.

## 2. The snapshot

```
kind        no2_plume, so2_plume, co2_plume   (one kind per gas)
geometry    Polygon outline, Point origin
marks       p, viability               as for methane
            flux_kg_s, flux_sigma_kg_s  emission rate and its uncertainty
            lifetime_h                  NO₂, SO₂ only: the chemical lifetime used
            wind_u_m_s, wind_v_m_s
link        same_source, gap rule
entities    source → facility → asset → operator, government
```

One kind per gas keeps marks honest: an NO₂ flux carries a lifetime assumption that a CO₂ flux does not.
Units change too: a power plant's CO₂ is naturally in kt per day, its NO₂ in kg s⁻¹; marks store SI units and the UI converts.

## 3. The data

| Gas | Sensors | Product | Public copies |
| --- | --- | --- | --- |
| NO₂ | TROPOMI (Sentinel-5P), daily, ~5.5 × 3.5 km | L2 tropospheric column | Copernicus Data Space; NASA GES DISC |
| SO₂ | TROPOMI, OMI | L2 column | Copernicus Data Space; NASA GES DISC |
| CO₂ | OCO-2/3 (narrow swaths), EMIT, imaging spectrometers | L2 XCO₂, or radiance for a matched filter | NASA GES DISC, LP DAAC |

Coarse TROPOMI pixels see city- and plant-scale plumes; fine-scale imaging spectrometers see individual stacks.
A kind that reads an L2 column skips step 5 (retrieval) and starts at detection.

## 4. Steps 5–7

**Retrieve (fine-scale sensors).** The methane matched filter carries over with the gas's absorption target.
Let x ∈ ℝᴮ be a pixel's radiance over B bands, μ and Σ the background mean and covariance, and k ∈ ℝᴮ the gas's unit absorption spectrum.

```
# Shapes: B bands; N pixels
# t = μ ⊙ k                                   target signature, (B,)
# ΔΩ̂ᵢ = tᵀ Σ⁻¹ (xᵢ − μ) / (tᵀ Σ⁻¹ t)          enhancement per pixel, (N,)
```

**Detect.** The same segmenter as methane, retrained per gas: CO₂ enhancements are small against a large background, NO₂ plumes are long and diffuse.

**Quantify: cross-sectional flux.** Let Ω(s, n) be the column enhancement (kg m⁻²) at distance s downwind and n across the plume, u the wind speed along the plume (m s⁻¹), and τ the gas's chemical lifetime (s).
The flux through a transect at distance s is

```
# Shapes: S transects downwind; Nₙ samples across each
# F(s) = u ∑ₙ Ω(s, n) Δn                                    kg s⁻¹, one per transect, (S,)
```

NO₂ and SO₂ decay on the way, so the flux at the source is larger than the flux observed downwind:

```
# E(s) = F(s) · exp(s / (u τ))                              lifetime correction, (S,)
# Ê = median over s of E(s),   σ_E from the spread over s and the τ, u uncertainties
```

CO₂ is inert on these scales (no correction), but it rides on a background of about 420 ppm, so the background estimate dominates the uncertainty.

## 5. Linking

Same as methane: detections at one source chain into events by the gap rule, split at a clear look.
For a power plant, an "event" is a period of operation; the gap rule's G should follow the sensor's revisit and the plant's duty cycle, not methane's 30 days.

## 6. Validation

Every snapshot, as for methane. Common false positives differ: urban NO₂ backgrounds, cloud edges, and for SO₂, volcanic plumes far from any industrial source (which are real, but attributed to a volcano, not a facility).

## 7. Attribution and watches

The source → facility → asset → operator chain is the same.
Facility registries change: power-plant databases list units, capacities and fuels, so a facility can carry `facility_type = "coal power plant"` and a capacity in `attrs`.
Volcanoes are facilities of type `volcano` with no operator, linked to a government.

A typical watch: "any validated NO₂ plume at facilities in this country above 1 kg s⁻¹".

## 8. In geoapps today

- **Works now:** the data model, validation, events by gap rule, attribution and watches, unchanged.
- **To add:** one `register_kind` per gas with its marks; an importer for TROPOMI L2 columns (or a plume list); unit-aware display; the cross-sectional flux operator in GeoStack (plumax).
- **Watch out:** the watch rule's `min_q_kg_h` field is methane-shaped; watches should compare against the kind's own flux mark.

## 9. Open questions

- One kind per gas, or one `trace_gas_plume` kind with the gas as a mark? (One per gas keeps the marks schema strict.)
- Which lifetime τ for NO₂: fixed per season and latitude, or fitted per plume?
- CO₂ and NO₂ from the same plant: link them as two kinds at one source, or as one multi-gas event?
