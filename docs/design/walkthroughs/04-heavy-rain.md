# Walkthrough: heavy rain

Rain is not detected in a scene; it is read out of a dense space-time cube of precipitation.
The kind's work is reducing that cube to footprints per time step, and saying how rare each one is.

## 1. The problem

Hydrological services and civil protection want to know where rain was extreme, how extreme (a return period), and which basins it fell on; the same events explain floods a few days later.

**Running example: the rain behind the May 2023 Emilia-Romagna floods** (see the [flood walkthrough](03-floods.md)). Two multi-day rain episodes fell on already saturated ground in the first half of May. The numbers below are illustrative.

## 2. The snapshot

```
kind        heavy_rain
geometry    Polygon or MultiPolygon: the footprint at one time step
marks       p, viability
            accumulation_mm               over the kind's window D
            peak_rate_mm_h
            return_period_yr, return_period_ci   from the extreme-value fit
link        contiguous in space and time
entities    basin, admin region
```

## 3. The data

| Input | Grid | Public copies |
| --- | --- | --- |
| IMERG (GPM) | 0.1°, 30 min, global | NASA GES DISC |
| ERA5 total precipitation | 0.25°, hourly, reanalysis | Copernicus Climate Data Store |
| Radar composites | ~1 km, 5–15 min, national | National weather services, where open |

All of these are cubes, stored as Zarr and read in chunks; no scene search, no retrieval (step 5 is skipped).

## 4. Steps 5–7

**Detect: reduce the cube.** Let P(x, t) be the precipitation rate (mm h⁻¹) at grid cell x and time t, and D the accumulation window (e.g. 24 h).

```
# Shapes: T time steps; X grid cells; D window length in steps
# A_D(x, t) = ∑_{k=0}^{D−1} P(x, t − k) Δt                accumulation, mm, (T, X) → (T, X)
```

Let F_x be the distribution of annual maxima of A_D at cell x, fitted as a generalized extreme value (GEV) law with location μ_x, scale σ_x and shape ξ_x on a long record (xtremax does this in GeoStack). The return period of an accumulation a is

```
# F_x(a) = exp(−[1 + ξ_x (a − μ_x) / σ_x]^(−1/ξ_x))        GEV distribution function
# T_x(a) = 1 / (1 − F_x(a))                                years, (T, X) → (T, X)
```

The footprint at time t is every cell above a threshold, in rarity or in amount:

```
# S_t = {x : T_x(A_D(x, t)) ≥ T₀  ∨  A_D(x, t) ≥ a₀}       e.g. T₀ = 10 years
# snapshots at t = connected components of S_t, each a polygon, (X,) → C_t polygons
```

**Quantify.** Each snapshot carries its maximum accumulation, its peak rate and its largest return period, with the GEV fit's uncertainty as the interval. Return periods beyond the length of the record are extrapolations, and the interval shows it.

## 5. Linking: contiguous in space and time

A rain event is a connected region of the space-time cube: snapshots at consecutive time steps that overlap belong together.

```
# Shapes: the boolean cube S, (T, X)
# events = 3-D connected components of S (time as the third axis)
# event start and end = first and last t in its component
```

Because the cube has no gaps in time, the bounds are tight: t_a and t_b are one step apart, so are t_c and t_d.

## 6. Validation

A gridded product is not a model's guess about a scene, so per-snapshot review makes little sense. Two options, set per kind: review once per event (does this look like a real storm and not a product artefact?), or trust the product and skip review, recording the decision as a provider label.

## 7. Attribution and watches

Attributed to basins and admin regions, as for floods. A rain event and the flood that follows in the same basin are linked as cause and effect.

A typical watch: "any 24-hour accumulation with a return period above 20 years in these basins".

## 8. In geoapps today

- **Works now:** storing polygons per time step, events and their bounds, provenance, watches on areas.
- **To add:** the `heavy_rain` kind; Zarr inputs through titiler.xarray for the map; the cube-reduction step (xtremax for the GEV fits); the space-time contiguity linker; per-event or trusted validation; basins and admin regions as entities.
- **Watch out:** a long storm at 30-minute steps makes hundreds of snapshots; the queue must show events, not every step.

## 9. Open questions

- Which window D, or several (1 h, 24 h, 72 h) as separate kinds or as marks?
- Fit the GEV per cell, or pool neighbouring cells for stability?
- Store snapshots at every time step, or only at the event's peak and a few summary times?
