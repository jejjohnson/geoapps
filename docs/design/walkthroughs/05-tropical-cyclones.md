# Walkthrough: tropical cyclones

One system, followed for days: hundreds of snapshots between its start and its end.
That is the same object as a plume seen on many overpasses; the differences are that the snapshots come every few hours and that the linking is done by a tracker.

## 1. The problem

Forecast and civil protection services want each system's track, intensity and size over time, and where it made landfall and how strong it was then; researchers want the archive.

**Running example: Hurricane Ian, September 2022.** It formed in the Caribbean, crossed western Cuba, and made landfall in south-west Florida on 28 September at major-hurricane strength. The numbers below are illustrative.

## 2. The snapshot

```
kind        tropical_cyclone
geometry    Polygon: the 34-kt wind radii as a four-quadrant shape
origin      Point: the centre
marks       p, viability
            vmax_kt, vmax_sigma_kt     maximum sustained wind
            mslp_hpa                   minimum sea-level pressure
            r34_km                     34-kt radius per quadrant (NE, SE, SW, NW)
            rmw_km                     radius of maximum wind
            category                   on a chosen scale, e.g. Saffir–Simpson
link        tracker: snapshots of one system
entities    landfall regions (admin regions, coasts)
```

## 3. The data

| Input | Why | Public copies |
| --- | --- | --- |
| Best tracks (IBTrACS) | The reference archive: centre, intensity and radii every 3–6 h | NOAA NCEI |
| Geostationary imagery (GOES, Himawari, Meteosat) | Structure and intensity estimates between best-track times | NOAA, JMA, EUMETSAT open data |
| Scatterometer winds (ASCAT) | Surface wind radii | EUMETSAT, NOAA |
| Model and reanalysis fields | Steering flow, environment | ERA5 (Copernicus Climate Data Store) |

A best track is an authoritative, already-reviewed product; geoapps can import it as a trusted source.

## 4. Steps 5–7

For a best-track import, steps 5–7 are skipped: each record already is a snapshot.
For the platform's own estimates between best-track times:

**Detect.** Find the centre in a geostationary scene: a deep-convection pattern and, where scatterometer winds exist, the minimum wind and the curl maximum.

**Quantify.** Let r be distance from the centre, θ the bearing, and R34(θ) the radius at which the wind falls to 34 kt in direction θ, given per quadrant q ∈ {NE, SE, SW, NW}.
The snapshot's polygon is the four quarter-discs joined:

```
# Shapes: 4 quadrants; K arc samples per quadrant
# boundary(θ) = centre + R34(q(θ)) · (sin θ, cos θ),  θ ∈ [0°, 360°)     (4K, 2) vertices
# polygon = the closed ring through those vertices                       a quadrant with R34 = 0 collapses to the centre
```

The intensity marks come from the scheme used (a Dvorak-style estimate from imagery, or scatterometer winds), each with its uncertainty.

## 5. Linking: the tracker

Snapshots from a best track already carry the storm's identifier, so linking is exact.
For the platform's own detections, a tracker joins snapshots by predicted motion. Let c_k be the centre at time t_k and v_k the storm's motion vector:

```
# Shapes: one track with K snapshots; M candidate centres at t_{k+1}
# ĉ_{k+1} = c_k + v_k (t_{k+1} − t_k)                       predicted centre
# next = argmin_m ‖c_m − ĉ_{k+1}‖  if  ‖c_m − ĉ_{k+1}‖ ≤ r_gate   nearest within a gate, (M,) → index
# v_{k+1} = (c_{k+1} − c_k) / (t_{k+1} − t_k)
```

The event starts at genesis (the first snapshot meeting the tropical-cyclone criteria) and ends at dissipation or extratropical transition; with snapshots every few hours the bounds are tight.

## 6. Validation

Per event, not per snapshot: a person reviews the track as a whole. Imported best tracks are trusted and recorded as provider labels, as the Eye on Methane import does with `accept_provider_validation`.

## 7. Attribution and watches

Attributed to the regions the system affects: the admin regions inside its 34-kt swath, and the landfall region with the intensity at landfall.
The swath is the union of every snapshot's polygon over the event.

A typical watch: "any system whose 34-kt swath reaches these coastal municipalities", fired on the first snapshot that does so.

## 8. In geoapps today

- **Works now:** polygon snapshots with a centre as origin, events with many detections, provider labels for trusted sources, watches on areas.
- **To add:** the `tropical_cyclone` kind; an IBTrACS importer (the fastest way to a real archive); the tracker as a linker; per-event validation; admin regions as entities; a track view in the shell (a line through the centres, coloured by intensity).
- **Watch out:** a watch should fire once per system, not once per snapshot; alerts need an "event" scope next to today's "detection" scope.

## 9. Open questions

- Which intensity scale per basin? Saffir–Simpson, or each basin's own warning centre's scale.
- Keep both the best track and the platform's own estimates as two sources for one event, or as two events linked by a relation?
- Should landfall be a mark on the event or its own derived record?
