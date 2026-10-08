// Basemaps. Streets and imagery come from public tile services the browser
// fetches directly; the offline one is Natural Earth 1:10m served by the app
// itself, so the map always has coasts, borders, rivers, roads and place names
// even with no network.
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

// plain concatenation: new URL() would percent-encode the {fontstack}/{range} tokens MapLibre needs
const asset = (path: string) => `${window.location.origin}${import.meta.env.BASE_URL}basemap/${path}`;

/** Natural Earth 1:10m, served from public/basemap/ (built by scripts/build-basemap.mjs). */
function offlineStyle(): StyleSpecification {
  const dark = prefersDark();
  const c = dark
    ? { sea: "#0f1c26", land: "#1b262c", urban: "#26323a", water: "#14303f", river: "#1f4a60", road: "#3b4a52",
        state: "#4a5b64", country: "#7c8c94", label: "#c9d3d8", halo: "#0f1c26", sea_label: "#5d8aa3" }
    : { sea: "#cfe0ea", land: "#f6f4ee", urban: "#e8e2d6", water: "#cfe0ea", river: "#9ec3d9", road: "#e2c9a0",
        state: "#b6aec0", country: "#8f8798", label: "#3b3f45", halo: "#ffffff", sea_label: "#5b86a3" };
  const geo = (file: string) => ({ type: "geojson" as const, data: asset(file) });
  const text = (font: string) => [font];
  return {
    version: 8,
    glyphs: asset("fonts/{fontstack}/{range}.pbf"),
    sources: {
      land: { ...geo("land.geojson"), attribution: "Natural Earth" },
      lakes: geo("lakes.geojson"),
      urban: geo("urban.geojson"),
      rivers: geo("rivers.geojson"),
      countries: geo("countries-lines.geojson"),
      states: geo("states-lines.geojson"),
      roads: geo("roads.geojson"),
      places: geo("places.geojson"),
      country_labels: geo("countries-labels.geojson"),
      sea_labels: geo("seas-labels.geojson"),
    },
    layers: [
      { id: "sea", type: "background", paint: { "background-color": c.sea } },
      { id: "land", type: "fill", source: "land", paint: { "fill-color": c.land } },
      { id: "urban", type: "fill", source: "urban", minzoom: 5, paint: { "fill-color": c.urban, "fill-opacity": 0.9 } },
      { id: "lakes", type: "fill", source: "lakes", paint: { "fill-color": c.water } },
      {
        id: "rivers", type: "line", source: "rivers", minzoom: 3,
        paint: { "line-color": c.river, "line-width": ["interpolate", ["linear"], ["zoom"], 3, 0.4, 8, 1.2, 12, 2] },
      },
      {
        id: "roads", type: "line", source: "roads", minzoom: 5,
        paint: {
          "line-color": c.road,
          "line-width": ["interpolate", ["linear"], ["zoom"], 5, ["match", ["get", "type"], "Major Highway", 0.8, 0.4], 10, ["match", ["get", "type"], "Major Highway", 2.5, 1.4]],
        },
      },
      {
        id: "states", type: "line", source: "states", minzoom: 2.5,
        paint: { "line-color": c.state, "line-width": ["interpolate", ["linear"], ["zoom"], 3, 0.4, 8, 1.1], "line-dasharray": [4, 2] },
      },
      {
        id: "countries", type: "line", source: "countries",
        paint: { "line-color": c.country, "line-width": ["interpolate", ["linear"], ["zoom"], 1, 0.6, 8, 1.6] },
      },
      {
        id: "sea-labels", type: "symbol", source: "sea_labels", maxzoom: 7,
        layout: { "text-field": ["get", "name"], "text-font": text("Noto Sans Italic"), "text-size": 12, "text-letter-spacing": 0.1, "text-max-width": 8 },
        paint: { "text-color": c.sea_label },
      },
      {
        id: "country-labels", type: "symbol", source: "country_labels", maxzoom: 7,
        filter: ["<=", ["get", "rank"], 5],
        layout: {
          "text-field": ["get", "name"], "text-font": text("Noto Sans Medium"), "text-transform": "uppercase",
          "text-size": ["interpolate", ["linear"], ["zoom"], 1, 9, 5, 13], "text-letter-spacing": 0.08, "text-max-width": 7,
          "symbol-sort-key": ["get", "rank"],
        },
        paint: { "text-color": c.country, "text-halo-color": c.halo, "text-halo-width": 1.2 },
      },
      {
        id: "places", type: "symbol", source: "places", minzoom: 2,
        // larger places first, and fewer of them when zoomed out
        filter: ["step", ["zoom"], ["<=", ["get", "rank"], 2], 4, ["<=", ["get", "rank"], 4], 6, ["<=", ["get", "rank"], 7], 8, true],
        layout: {
          "text-field": ["get", "name"], "text-font": text("Noto Sans Regular"),
          "text-size": ["interpolate", ["linear"], ["get", "rank"], 0, 14, 10, 11],
          "symbol-sort-key": ["get", "rank"], "text-variable-anchor": ["top", "bottom", "left", "right"], "text-radial-offset": 0.6,
          "icon-optional": true,
        },
        paint: { "text-color": c.label, "text-halo-color": c.halo, "text-halo-width": 1.4 },
      },
    ],
  };
}

export async function basemapStyle(id: BasemapId): Promise<string | StyleSpecification> {
  if (id === "streets") return STREETS;
  if (id === "satellite") return IMAGERY;
  return offlineStyle();
}

