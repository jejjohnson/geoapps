# Walkthroughs: one event kind at a time

Each walkthrough takes one kind of intermittent event from the satellite data to an alert, using the same platform and the same steps as the methane plume example ([`../04-running-example-methane.md`](../04-running-example-methane.md)).
They show what a kind plugs in, what it reuses unchanged, and what geoapps still lacks for it.

| Walkthrough | Snapshot | Linked into events by | Attributed to | Validated |
| --- | --- | --- | --- | --- |
| [Methane plumes](../04-running-example-methane.md) | outline + source point | same source, gap rule | source → facility → asset → operator, government | every snapshot |
| [Other trace gases](01-other-trace-gases.md) | outline + source point | same source, gap rule | source → facility (power plant, smelter, volcano) | every snapshot |
| [Oil spills](02-oil-spills.md) | slick outline | overlap after drift | vessel, platform, pipeline | every snapshot |
| [Floods](03-floods.md) | flood extent per pass | overlap within a basin | basin, admin region | per event, spot-checked |
| [Heavy rain](04-heavy-rain.md) | footprint per time step from a cube | contiguous in space and time | basin, admin region | per event, or trusted |
| [Tropical cyclones](05-tropical-cyclones.md) | centre + wind-radii polygon | the system's tracker | landfall regions | per event, or trusted best track |

Sensitive kinds, such as conflict events, are out of scope.

## The shape every walkthrough follows

1. **The problem**, with one running example.
2. **The snapshot**: geometry and marks, as the kind registers them.
3. **The data**: sensors, products and where public copies live.
4. **Steps 5–7** (retrieve, detect, quantify), the only science that changes; symbols are defined before each equation.
5. **Linking** snapshots into events, and how start and end are bounded.
6. **Validation**: what a person reviews, and how often.
7. **Attribution and watches**: which entities, and what a watch rule looks like.
8. **In geoapps today**: what already works and what has to be built.
9. **Open questions.**

Steps 1–4 (search, select, fetch, stage), 8 (store), 10–11 (review, queue), 13–14 (alert, feed back) and the retraining loop are the same for every kind ([`../02-end-to-end-pipeline.md`](../02-end-to-end-pipeline.md)).

## What all five need that geoapps does not have yet

The plume kind is the only one implemented, so it has shaped what exists. The other kinds share four gaps:

```
LINKERS          only "same source, gap rule" exists;
  │              overlap, overlap-with-drift,
  │              space-time contiguity and a
  │              tracker are still to build
  ▼
REGIONS          basins and admin regions as
  │              entities (geo.region in the
  │              framework, page 6), with
  │              validity ranges like the rest
  ▼
VALIDATION       per-event and trusted-source
  │              review, beside per-snapshot
  │              (the kind field exists, the
  │              queue only knows snapshots)
  ▼
CUBES            Zarr inputs through titiler.xarray
                 and cube-reduction steps, for rain
                 and anything gridded
```

Workstream L in the design plan owns these; each walkthrough says which of them it needs first.
