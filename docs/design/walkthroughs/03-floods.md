# Walkthrough: floods

Water where there is normally none, mapped pass by pass while it spreads and recedes.
Floods are attributed to places (a basin, a municipality), not to an emitter, and one flood is seen many times.

## 1. The problem

Civil protection needs to know which areas are under water, how deep, and how many people and buildings are affected; insurers and researchers need the same record afterwards.

**Running example: the May 2023 floods in Emilia-Romagna, Italy.** Two rounds of heavy rain in early and mid May made rivers across the region overflow; radar passes over the following days mapped the flooded plains.
The numbers below are illustrative, not measurements of that event.

## 2. The snapshot

```
kind        flood
geometry    Polygon or MultiPolygon: flood extent at one pass
marks       p, viability
            area_km2
            depth_mean_m, depth_max_m     where a DEM allows
            population_exposed            from a population grid
link        overlap within a basin over days
entities    basin, admin region
```

## 3. The data

| Input | Why | Public copies |
| --- | --- | --- |
| Sentinel-1 SAR | Through cloud, which floods usually come with | Copernicus Data Space; Earth Search; Planetary Computer |
| Sentinel-2, Landsat | Sharper water edges when clear | Earth Search; Planetary Computer |
| Permanent water reference | So a lake is not a flood | JRC Global Surface Water |
| Elevation | Depth | Copernicus DEM (GLO-30) |
| Population and buildings | Exposure | GHSL, WorldPop |
| Ready-made flood maps | Labels and cross-checks | Copernicus EMS rapid mapping; the GFM product of GloFAS |

## 4. Steps 5–7

**Retrieve.** On radar, open water is smooth and dark. Let σ⁰ᵢ be the VV backscatter of pixel i in dB and σ⁰_dry,ᵢ its value in a dry reference period. On optical scenes, let G and NIR be green and near-infrared reflectance:

```
# Shapes: N pixels
# dᵢ = σ⁰ᵢ − σ⁰_dry,ᵢ                       change from the dry reference, dB, (N,)
# NDWIᵢ = (Gᵢ − NIRᵢ) / (Gᵢ + NIRᵢ)          optical water index, (N,)
```

**Detect.** Let Wᵢ ∈ {0, 1} be the water mask from a segmenter on d (or NDWI), and Pᵢ ∈ {0, 1} the permanent-water mask:

```
# Fᵢ = Wᵢ ∧ ¬Pᵢ                              flood = water that is not normally water, (N,)
# extent = connected components of F, merged per basin
```

Radar misses water under vegetation and in built-up areas (double bounce makes them bright), so the extent is a lower bound there and `viability` carries it.

**Quantify.** Let zᵢ be ground elevation and h the water-surface elevation, estimated from the elevations along the flood edge (a FwDET-style method):

```
# Shapes: N flooded pixels; E edge pixels
# h(x) ≈ interpolation of z over the edge pixels               water surface, (E,) → (N,)
# depthᵢ = max(h(xᵢ) − zᵢ, 0)                                  m, (N,)
# exposed = ∑ᵢ Fᵢ · popᵢ                                       people, (N,) → ()
```

## 5. Linking: overlap within a basin

Two extents belong to one flood if they overlap and lie in the same river basin within a few days.
Let G_t and G_{t′} be extents at passes t < t′ and B(G) the basins an extent touches:

```
# same flood ⇔ B(G_t) ∩ B(G_{t′}) ≠ ∅  ∧  area(G_t ∩ G_{t′}) > 0  ∧  t′ − t ≤ Δ_max
```

The flood's start lies between the last dry pass and the first wet one; its end, between the last wet pass and the first pass at normal extent. The peak extent is the largest snapshot, and the event's footprint is the union.

## 6. Validation

Reviewing every pass of a large flood is wasteful: the extents overlap and change slowly. A per-event review with spot checks fits better. An analyst confirms the event and checks the peak snapshot plus a sample of the others; Copernicus EMS maps, where they exist, are a second opinion.

## 7. Attribution and watches

A flood is attributed to the basins and admin regions it covers, each valid over time (municipal boundaries change too), not to a responsible party.
A heavy-rain event in the same basin a few days earlier is its likely cause (see the [heavy rain walkthrough](04-heavy-rain.md)); that is a link between two events, not an attribution to an entity.

A typical watch: "any validated flood touching these municipalities, or exposing more than 1,000 people".

## 8. In geoapps today

- **Works now:** polygon snapshots, provenance, watches on areas.
- **To add:** the `flood` kind; the overlap-within-basin linker; basins and admin regions as entities with validity ranges; per-event validation in the queue; an importer for existing flood maps (EMS, GFM) as a fast first source of real extents.
- **Watch out:** extents of hundreds of km² with fine edges are heavy as GeoJSON; the map layer will need vector tiles (Martin or TiPg) sooner than for plumes.

## 9. Open questions

- One event per basin, or one per hydrological episode spanning several basins?
- Event-to-event links (rain causes flood): a table of its own, or a relation in the entity graph?
- Which population grid, and which year of it, for exposure, given that it changes each release?
