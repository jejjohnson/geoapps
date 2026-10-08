# Walkthrough: oil spills

A slick on the sea surface, seen mostly by radar, that moves between passes.
The two new ideas are look-alikes (calm water that looks like oil) and drift: the same spill is in a different place on the next pass.

## 1. The problem

Spills come from vessels discharging bilge water, from platforms and pipelines, and from natural seeps.
Coast guards and environment agencies want to know where a slick is, how big it is, whether it is growing, and where it came from.

**Running example (illustrative).** A Sentinel-1 pass at 06:00 shows a 12 km dark streak along a shipping lane; a second pass 12 hours later shows a wider, fainter patch 20 km to the north-east.

## 2. The snapshot

```
kind        oil_spill
geometry    Polygon (the slick outline)
marks       p, viability
            area_km2, area_sigma_km2
            thickness_class            appearance class, e.g. sheen, metallic, true colour
            volume_m3, volume_sigma_m3
            wind_speed_m_s             at the time of the pass
link        overlap after drift
entities    vessel, platform, pipeline
```

## 3. The data

| Sensor | Why | Public copies |
| --- | --- | --- |
| Sentinel-1 C-band SAR (GRD, ~10 m) | Day and night, through cloud; oil damps capillary waves and looks dark | Copernicus Data Space; Earth Search and Planetary Computer (STAC) |
| Sentinel-2, Landsat (optical) | Confirms thickness and colour when the sky is clear | Earth Search, Planetary Computer |
| AIS vessel positions | Which ship was where, for attribution | Commercial or national feeds; not public at full resolution |

## 4. Steps 5–7

**Retrieve: radar contrast.** Let σ⁰ᵢ be the calibrated backscatter of pixel i (in dB) and σ̄⁰ᵢ the background backscatter around it (a local median over a window much larger than a slick).
The contrast is

```
# Shapes: H × W = N pixels
# cᵢ = σ̄⁰ᵢ − σ⁰ᵢ                           dB, positive where the sea is darker than around it, (N,)
```

**Detect.** A segmenter on c and the wind field proposes dark patches; a look-alike classifier then separates oil from low-wind areas, rain cells, algae and ship wakes.
Wind decides what is detectable at all: with too little wind the whole sea is dark, and with too much the slick breaks up. Let U be the 10 m wind speed; a scene's viability v falls to zero outside a window [U_min, U_max] (roughly 2–3 to 10–12 m s⁻¹ in the literature):

```
# vᵢ = 1 if U_min ≤ Uᵢ ≤ U_max else 0        per pixel; the scene's v is its mean over the sea, (N,) → ()
```

**Quantify.** Let A be the slick area (m²) and h_k the thickness assigned to appearance class k (from an appearance code such as the Bonn Agreement's), with A_k the area in class k:

```
# V = ∑ₖ A_k h_k                                volume, m³; each h_k is a range, so V is too
```

Radar alone rarely gives the thickness class; without optical support V is a wide range, and the marks say so.

## 5. Linking: overlap after drift

Two snapshots belong to one spill if the earlier slick, moved by the sea and the wind over the time between passes, overlaps the later one.
Let p be a point of the earlier outline, u_c the surface current, u_w the 10 m wind, α the wind-drift factor (about 0.03), and Δt the time between passes:

```
# Shapes: earlier outline G₁ with P vertices; later outline G₂
# p′ = p + (u_c + α u_w) Δt                    advect every vertex, (P, 2) → (P, 2)
# same spill ⇔ IoU(G₁′, G₂) ≥ τ_link           IoU as in gate E1, with a looser τ_link
```

The event's start lies between the last clear pass without the slick and the first with it; its end, between the last pass with it and the first clear pass without it, exactly the t_a … t_d bounds of the data model.

## 6. Validation

Every snapshot: look-alikes are common and a false alarm sends a boat out. The reviewer sees the radar scene, the wind field and any optical scene of the same day side by side.

## 7. Attribution and watches

Candidates are the vessels whose AIS tracks passed upwind of the slick's head in the hours before the first pass, plus platforms and pipelines under or near it.
The same scoring idea as plume attribution applies: distance from the slick's origin and alignment with the drift backwards in time.

A typical watch: "any validated spill inside this marine protected area, or within 10 km of this coast".

## 8. In geoapps today

- **Works now:** polygons, marks validation, per-snapshot review, watches on areas, provenance.
- **To add:** the `oil_spill` kind; the overlap-with-drift linker (it needs current and wind fields, so Zarr inputs); vessels as an entity type with time-stamped positions; the look-alike classifier as a registered step.
- **Watch out:** AIS licences usually forbid redistribution, which the kind's publication policy must say.

## 9. Open questions

- Which current and wind products for drift: a global ocean model, or regional ones where they exist?
- Are natural seeps sources (persistent, like a methane source) or spills? Probably sources, with their own events.
- Does a slick that splits in two make two events or one?
