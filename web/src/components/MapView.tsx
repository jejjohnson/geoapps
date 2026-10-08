import maplibregl, { type GeoJSONSource, type MapMouseEvent } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { useEffect, useRef } from "react";
import type { BBox, FeatureCollection } from "../api/client";

// Any MapLibre style works; the default needs no key. Set VITE_BASEMAP_STYLE to swap it.
const BASEMAP = import.meta.env.VITE_BASEMAP_STYLE ?? "https://tiles.openfreemap.org/styles/positron";

// Used when the basemap can't be fetched (offline, blocked): the data layers still work.
const BLANK: maplibregl.StyleSpecification = {
  version: 8,
  sources: {},
  layers: [{ id: "bg", type: "background", paint: { "background-color": "#e9ecef" } }],
};

export const STATUS_COLOR = { predicted: "#d97706", validated: "#059669", rejected: "#9ca3af" } as const;

const VECTOR_LAYERS = ["scenes-line", "watches-fill", "watches-line", "det-fill", "det-line", "det-selected", "sources"];

type Props = {
  detections: FeatureCollection;
  sources: FeatureCollection;
  watches: FeatureCollection;
  scenes: FeatureCollection;
  cogTiles: string | null;
  selectedId: number | null;
  focus: [number, number, number, number] | null;
  onSelect: (id: number) => void;
  onBounds: (b: BBox) => void;
};

export function MapView(p: Props) {
  const el = useRef<HTMLDivElement>(null);
  const map = useRef<maplibregl.Map | null>(null);
  const ready = useRef(false);
  const latest = useRef(p);
  latest.current = p;

  useEffect(() => {
    const m = new maplibregl.Map({
      container: el.current!,
      style: BASEMAP,
      center: [-103.45, 31.95], // the Permian demo pads
      zoom: 9,
      attributionControl: { compact: true },
    });
    map.current = m;
    m.addControl(new maplibregl.NavigationControl({ visualizePitch: false }), "top-right");
    m.addControl(new maplibregl.ScaleControl({ unit: "metric" }), "top-left");

    const emitBounds = () => {
      const b = m.getBounds();
      latest.current.onBounds([b.getWest(), b.getSouth(), b.getEast(), b.getNorth()]);
    };

    let fellBack = false;
    m.on("error", (e) => {
      if (!ready.current && !fellBack && !m.isStyleLoaded()) {
        fellBack = true;
        console.warn("basemap unavailable, using a blank background", e.error);
        m.setStyle(BLANK);
      }
    });

    m.on("load", () => {
      for (const id of ["detections", "sources", "watches", "scenes"]) m.addSource(id, { type: "geojson", data: { type: "FeatureCollection", features: [] } });
      m.addLayer({ id: "scenes-line", type: "line", source: "scenes", paint: { "line-color": "#6366f1", "line-width": 1.2, "line-dasharray": [2, 2] } });
      m.addLayer({ id: "watches-fill", type: "fill", source: "watches", paint: { "fill-color": "#2563eb", "fill-opacity": 0.06 } });
      m.addLayer({ id: "watches-line", type: "line", source: "watches", paint: { "line-color": "#2563eb", "line-width": 1.5, "line-dasharray": [3, 2] } });
      const statusColor: maplibregl.ExpressionSpecification = [
        "match", ["get", "status"],
        "validated", STATUS_COLOR.validated,
        "rejected", STATUS_COLOR.rejected,
        STATUS_COLOR.predicted,
      ];
      m.addLayer({ id: "det-fill", type: "fill", source: "detections", paint: { "fill-color": statusColor, "fill-opacity": 0.35 } });
      m.addLayer({ id: "det-line", type: "line", source: "detections", paint: { "line-color": statusColor, "line-width": 1 } });
      m.addLayer({ id: "det-selected", type: "line", source: "detections", filter: ["==", ["id"], -1], paint: { "line-color": "#111827", "line-width": 3 } });
      m.addLayer({
        id: "sources", type: "circle", source: "sources",
        paint: { "circle-radius": 4, "circle-color": "#111827", "circle-stroke-color": "#fff", "circle-stroke-width": 1.5 },
      });

      m.on("click", "det-fill", (e: MapMouseEvent & { features?: maplibregl.MapGeoJSONFeature[] }) => {
        const id = e.features?.[0]?.id;
        if (typeof id === "number") latest.current.onSelect(id);
      });
      m.on("mouseenter", "det-fill", () => (m.getCanvas().style.cursor = "pointer"));
      m.on("mouseleave", "det-fill", () => (m.getCanvas().style.cursor = ""));
      ready.current = true;
      sync();
      emitBounds();
    });
    m.on("moveend", emitBounds);
    return () => {
      ready.current = false;
      m.remove();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function sync() {
    const m = map.current;
    if (!m || !ready.current) return;
    const cur = latest.current;
    (m.getSource("detections") as GeoJSONSource).setData(cur.detections as unknown as GeoJSON.FeatureCollection);
    (m.getSource("sources") as GeoJSONSource).setData(cur.sources as unknown as GeoJSON.FeatureCollection);
    (m.getSource("watches") as GeoJSONSource).setData(cur.watches as unknown as GeoJSON.FeatureCollection);
    (m.getSource("scenes") as GeoJSONSource).setData(cur.scenes as unknown as GeoJSON.FeatureCollection);
    m.setFilter("det-selected", ["==", ["id"], cur.selectedId ?? -1]);
  }

  useEffect(sync, [p.detections, p.sources, p.watches, p.scenes, p.selectedId]);

  // the COG preview is a raster layer under every vector layer, replaced whenever the URL changes
  useEffect(() => {
    const m = map.current;
    if (!m || !ready.current) return;
    if (m.getLayer("cog")) m.removeLayer("cog");
    if (m.getSource("cog")) m.removeSource("cog");
    if (!p.cogTiles) return;
    m.addSource("cog", { type: "raster", tiles: [p.cogTiles], tileSize: 256 });
    m.addLayer({ id: "cog", type: "raster", source: "cog", paint: { "raster-opacity": 0.85 } }, VECTOR_LAYERS.find((l) => m.getLayer(l)));
  }, [p.cogTiles]);

  useEffect(() => {
    if (p.focus && map.current) {
      const [w, s, e, n] = p.focus;
      map.current.fitBounds([[w, s], [e, n]], { padding: 80, maxZoom: 14, duration: 600 });
    }
  }, [p.focus]);

  return <div ref={el} className="map" />;
}

/** [w, s, e, n] of any GeoJSON geometry, for fitting the map to it. */
export function geometryBounds(g: unknown): [number, number, number, number] | null {
  let w = Infinity, s = Infinity, e = -Infinity, n = -Infinity;
  const walk = (c: unknown): void => {
    if (Array.isArray(c) && typeof c[0] === "number") {
      const [x, y] = c as number[];
      w = Math.min(w, x); e = Math.max(e, x); s = Math.min(s, y); n = Math.max(n, y);
    } else if (Array.isArray(c)) c.forEach(walk);
  };
  walk((g as { coordinates?: unknown } | null)?.coordinates);
  return Number.isFinite(w) ? [w, s, e, n] : null;
}
