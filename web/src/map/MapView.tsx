import maplibregl, { type GeoJSONSource, type MapGeoJSONFeature, type MapMouseEvent } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { useEffect, useRef } from "react";
import type { BBox, FeatureCollection } from "../api/client";
import { basemapStyle, type BasemapId } from "./basemaps";

export const STATUS_COLOR = { predicted: "#d97706", validated: "#059669", rejected: "#9ca3af" } as const;

const DATA_LAYERS = [
  "scenes-line",
  "watches-fill",
  "watches-line",
  "facilities",
  "det-fill",
  "det-line",
  "det-point",
  "sources",
  "det-selected",
  "det-selected-point",
  "source-selected",
];

type Props = {
  basemap: BasemapId;
  detections: FeatureCollection;
  sources: FeatureCollection;
  facilities: FeatureCollection;
  watches: FeatureCollection;
  scenes: FeatureCollection;
  cogTiles: string | null;
  selectedId: number | null;
  selectedSourceId: number | null;
  focus: [number, number, number, number] | null;
  onSelect: (id: number) => void;
  onSelectSource: (id: number) => void;
  onBounds: (b: BBox) => void;
  onBasemapFailed: (id: BasemapId) => void;
};

const empty = (): GeoJSON.FeatureCollection => ({ type: "FeatureCollection", features: [] });
const asGeo = (fc: FeatureCollection) => fc as unknown as GeoJSON.FeatureCollection;

export function MapView(p: Props) {
  const el = useRef<HTMLDivElement>(null);
  const map = useRef<maplibregl.Map | null>(null);
  const ready = useRef(false);
  const latest = useRef(p);
  latest.current = p;

  // the data layers live on top of whichever basemap is loaded, and are re-added after a switch
  function addDataLayers(m: maplibregl.Map) {
    for (const id of ["detections", "sources", "facilities", "watches", "scenes"])
      if (!m.getSource(id)) m.addSource(id, { type: "geojson", data: empty() });
    const statusColor: maplibregl.ExpressionSpecification = [
      "match", ["get", "status"],
      "validated", STATUS_COLOR.validated,
      "rejected", STATUS_COLOR.rejected,
      STATUS_COLOR.predicted,
    ];
    const isPoint: maplibregl.FilterSpecification = ["==", ["geometry-type"], "Point"];
    const isArea: maplibregl.FilterSpecification = ["!=", ["geometry-type"], "Point"];
    // radius grows with flux; an unquantified plume draws at the size of a 300 kg/h one
    const radius: maplibregl.ExpressionSpecification = [
      "interpolate", ["linear"], ["sqrt", ["coalesce", ["get", "q_kg_h"], 300]],
      0, 3, 30, 5, 100, 9, 250, 15,
    ];
    m.addLayer({ id: "scenes-line", type: "line", source: "scenes", paint: { "line-color": "#6366f1", "line-width": 1.2, "line-dasharray": [2, 2] } });
    m.addLayer({ id: "watches-fill", type: "fill", source: "watches", paint: { "fill-color": "#2563eb", "fill-opacity": 0.06 } });
    m.addLayer({ id: "watches-line", type: "line", source: "watches", paint: { "line-color": "#2563eb", "line-width": 1.5, "line-dasharray": [3, 2] } });
    m.addLayer({
      id: "facilities", type: "circle", source: "facilities", minzoom: 8,
      paint: { "circle-radius": 3, "circle-color": "#6b7280", "circle-stroke-color": "#fff", "circle-stroke-width": 1 },
    });
    m.addLayer({ id: "det-fill", type: "fill", source: "detections", filter: isArea, paint: { "fill-color": statusColor, "fill-opacity": 0.35 } });
    m.addLayer({ id: "det-line", type: "line", source: "detections", filter: isArea, paint: { "line-color": statusColor, "line-width": 1 } });
    m.addLayer({
      id: "det-point", type: "circle", source: "detections", filter: isPoint,
      paint: {
        "circle-radius": radius,
        "circle-color": statusColor,
        "circle-opacity": 0.75,
        "circle-stroke-color": "#ffffff",
        "circle-stroke-width": 0.8,
      },
    });
    // a source is a ring around its plumes, sized by how often it was seen
    m.addLayer({
      id: "sources", type: "circle", source: "sources",
      paint: {
        "circle-radius": ["+", 6, ["*", 2.5, ["sqrt", ["coalesce", ["get", "n_detections"], 0]]]],
        "circle-color": "rgba(0,0,0,0)",
        "circle-stroke-color": "#111827",
        "circle-stroke-width": 1.2,
        "circle-stroke-opacity": 0.7,
      },
    });
    m.addLayer({ id: "det-selected", type: "line", source: "detections", filter: ["all", isArea, ["==", ["id"], -1]], paint: { "line-color": "#111827", "line-width": 3 } });
    m.addLayer({
      id: "det-selected-point", type: "circle", source: "detections", filter: ["all", isPoint, ["==", ["id"], -1]],
      paint: { "circle-radius": ["+", radius, 3], "circle-color": "rgba(0,0,0,0)", "circle-stroke-color": "#111827", "circle-stroke-width": 3 },
    });
    m.addLayer({
      id: "source-selected", type: "circle", source: "sources", filter: ["==", ["id"], -1],
      paint: {
        "circle-radius": ["+", 9, ["*", 2.5, ["sqrt", ["coalesce", ["get", "n_detections"], 0]]]],
        "circle-color": "rgba(0,0,0,0)",
        "circle-stroke-color": "#2563eb",
        "circle-stroke-width": 3,
      },
    });
  }

  function sync() {
    const m = map.current;
    if (!m || !ready.current || !m.getSource("detections")) return;
    const cur = latest.current;
    (m.getSource("detections") as GeoJSONSource).setData(asGeo(cur.detections));
    (m.getSource("sources") as GeoJSONSource).setData(asGeo(cur.sources));
    (m.getSource("facilities") as GeoJSONSource).setData(asGeo(cur.facilities));
    (m.getSource("watches") as GeoJSONSource).setData(asGeo(cur.watches));
    (m.getSource("scenes") as GeoJSONSource).setData(asGeo(cur.scenes));
    const sel = cur.selectedId ?? -1;
    m.setFilter("det-selected", ["all", ["!=", ["geometry-type"], "Point"], ["==", ["id"], sel]]);
    m.setFilter("det-selected-point", ["all", ["==", ["geometry-type"], "Point"], ["==", ["id"], sel]]);
    m.setFilter("source-selected", ["==", ["id"], cur.selectedSourceId ?? -1]);
    syncCog();
  }

  // the COG preview is a raster layer under every data layer, replaced whenever the URL changes
  function syncCog() {
    const m = map.current;
    if (!m || !ready.current) return;
    if (m.getLayer("cog")) m.removeLayer("cog");
    if (m.getSource("cog")) m.removeSource("cog");
    const url = latest.current.cogTiles;
    if (!url) return;
    m.addSource("cog", { type: "raster", tiles: [url], tileSize: 256 });
    m.addLayer({ id: "cog", type: "raster", source: "cog", paint: { "raster-opacity": 0.85 } }, DATA_LAYERS.find((l) => m.getLayer(l)));
  }

  useEffect(() => {
    const m = new maplibregl.Map({
      container: el.current!,
      style: { version: 8, sources: {}, layers: [{ id: "bg", type: "background", paint: { "background-color": "#dce8ee" } }] },
      center: [10, 25],
      zoom: 1.4,
      attributionControl: { compact: true },
    });
    map.current = m;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    if (import.meta.env.DEV) (window as any).__geoappsMap = m; // for debugging in the console
    m.addControl(new maplibregl.NavigationControl({ visualizePitch: false }), "top-right");
    m.addControl(new maplibregl.ScaleControl({ unit: "metric" }), "top-left");

    const emitBounds = () => {
      const b = m.getBounds();
      latest.current.onBounds([b.getWest(), b.getSouth(), b.getEast(), b.getNorth()]);
    };

    // every style load (the first one and each basemap switch) gets the data layers back
    m.on("style.load", () => {
      addDataLayers(m);
      ready.current = true;
      sync();
    });

    const pick = (e: MapMouseEvent) => {
      const layers = ["det-point", "det-fill", "sources"].filter((l) => m.getLayer(l));
      const hits: MapGeoJSONFeature[] = m.queryRenderedFeatures(e.point, { layers });
      const det = hits.find((h) => h.layer.id !== "sources");
      const src = hits.find((h) => h.layer.id === "sources");
      if (det && typeof det.id === "number") latest.current.onSelect(det.id);
      else if (src && typeof src.id === "number") latest.current.onSelectSource(src.id);
    };
    m.on("click", pick);
    m.on("mousemove", (e) => {
      const layers = ["det-point", "det-fill", "sources"].filter((l) => m.getLayer(l));
      m.getCanvas().style.cursor = m.queryRenderedFeatures(e.point, { layers }).length ? "pointer" : "";
    });
    m.on("load", emitBounds);
    m.on("moveend", emitBounds);

    return () => {
      ready.current = false;
      m.remove();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // switching basemaps: if a remote style can't be fetched, fall back and say so
  useEffect(() => {
    const m = map.current;
    if (!m) return;
    let failed = false;
    const onError = (e: { error?: Error }) => {
      const msg = String(e.error?.message ?? e.error ?? "");
      if (!failed && /fetch|load|style/i.test(msg) && !m.isStyleLoaded()) {
        failed = true;
        latest.current.onBasemapFailed(p.basemap);
      }
    };
    m.on("error", onError);
    let cancelled = false;
    // always apply, even when the previous style never finished loading (the failed case)
    void basemapStyle(p.basemap).then((style) => !cancelled && m.setStyle(style, { diff: false }));
    return () => {
      cancelled = true;
      m.off("error", onError);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [p.basemap]);

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(sync, [p.detections, p.sources, p.facilities, p.watches, p.scenes, p.selectedId, p.selectedSourceId]);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(syncCog, [p.cogTiles]);

  useEffect(() => {
    if (p.focus && map.current) {
      const [w, s, e, n] = p.focus;
      map.current.fitBounds([[w, s], [e, n]], { padding: 80, maxZoom: 13, duration: 600 });
    }
  }, [p.focus]);

  return <div ref={el} className="map" />;
}

/** [w, s, e, n] of any GeoJSON geometry (or list of them), for fitting the map. */
export function geometryBounds(g: unknown): [number, number, number, number] | null {
  let w = Infinity, s = Infinity, e = -Infinity, n = -Infinity;
  const walk = (c: unknown): void => {
    if (Array.isArray(c) && typeof c[0] === "number") {
      const [x, y] = c as number[];
      w = Math.min(w, x); e = Math.max(e, x); s = Math.min(s, y); n = Math.max(n, y);
    } else if (Array.isArray(c)) c.forEach(walk);
  };
  const geoms = Array.isArray(g) ? g : [g];
  for (const one of geoms) walk((one as { coordinates?: unknown } | null)?.coordinates);
  if (!Number.isFinite(w)) return null;
  // a single point gets a small box so fitBounds has something to fit
  const pad = 0.02;
  return w === e && s === n ? [w - pad, s - pad, e + pad, n + pad] : [w, s, e, n];
}
