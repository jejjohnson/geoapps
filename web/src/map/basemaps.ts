// Basemaps. Streets and imagery come from public tile services the browser
// fetches directly; the offline one is Natural Earth, bundled with the app, so
// the map always has land, sea and borders even with no network.
import type { StyleSpecification } from "maplibre-gl";

export type BasemapId = "streets" | "satellite" | "offline";

export const BASEMAPS: { id: BasemapId; label: string }[] = [
  { id: "streets", label: "Streets" },
  { id: "satellite", label: "Imagery" },
  { id: "offline", label: "Offline" },
];

// Any MapLibre style URL works here; the default needs no key.
const STREETS = import.meta.env.VITE_BASEMAP_STYLE ?? "https://tiles.openfreemap.org/styles/positron";

// Sentinel-2 cloudless by EOX (CC BY-NC-SA 4.0 for the 2018+ mosaics), a fit for plume work.
const IMAGERY_TILES =
  import.meta.env.VITE_IMAGERY_TILES ??
  "https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless-2021_3857/default/g/{z}/{y}/{x}.jpg";

const IMAGERY: StyleSpecification = {
  version: 8,
  sources: {
    imagery: {
      type: "raster",
      tiles: [IMAGERY_TILES],
      tileSize: 256,
      maxzoom: 15,
      attribution:
        '<a href="https://s2maps.eu" target="_blank" rel="noopener">Sentinel-2 cloudless</a> by EOX IT Services GmbH (contains modified Copernicus Sentinel data 2021)',
    },
  },
  layers: [
    { id: "bg", type: "background", paint: { "background-color": "#0b1d2a" } },
    { id: "imagery", type: "raster", source: "imagery" },
  ],
};

function prefersDark(): boolean {
  try {
    return window.matchMedia("(prefers-color-scheme: dark)").matches;
  } catch {
    return false;
  }
}

let offlineCache: Promise<StyleSpecification> | null = null;

/** Natural Earth 1:50m land and borders, loaded on first use (≈ 0.7 MB). */
function offlineStyle(): Promise<StyleSpecification> {
  offlineCache ??= (async () => {
    const [{ feature, mesh }, topo] = await Promise.all([
      import("topojson-client"),
      import("world-atlas/countries-50m.json"),
    ]);
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const t = (topo as any).default ?? topo;
    const countries = feature(t, t.objects.countries) as unknown as GeoJSON.FeatureCollection;
    const borders = mesh(t, t.objects.countries, (a: unknown, b: unknown) => a !== b) as unknown as GeoJSON.Geometry;
    const coast = mesh(t, t.objects.countries, (a: unknown, b: unknown) => a === b) as unknown as GeoJSON.Geometry;
    const dark = prefersDark();
    return {
      version: 8,
      sources: {
        countries: { type: "geojson", data: countries, attribution: "Natural Earth" },
        borders: { type: "geojson", data: { type: "Feature", properties: {}, geometry: borders } },
        coast: { type: "geojson", data: { type: "Feature", properties: {}, geometry: coast } },
      },
      layers: [
        { id: "sea", type: "background", paint: { "background-color": dark ? "#0f1c26" : "#dce8ee" } },
        { id: "land", type: "fill", source: "countries", paint: { "fill-color": dark ? "#1d2a30" : "#f4f2ec" } },
        { id: "coast", type: "line", source: "coast", paint: { "line-color": dark ? "#3a4d57" : "#a9bcc6", "line-width": 0.8 } },
        {
          id: "borders",
          type: "line",
          source: "borders",
          paint: { "line-color": dark ? "#4b5d66" : "#b9b3a6", "line-width": 0.7, "line-dasharray": [3, 2] },
        },
      ],
    } satisfies StyleSpecification;
  })();
  return offlineCache;
}

export async function basemapStyle(id: BasemapId): Promise<string | StyleSpecification> {
  if (id === "streets") return STREETS;
  if (id === "satellite") return IMAGERY;
  return offlineStyle();
}
