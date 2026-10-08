import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  api,
  getUser,
  setUser,
  type AlertOut,
  type BBox,
  type ClientConfig,
  type DatasetOut,
  type Feature,
  type FeatureCollection,
  type Stats,
} from "./api/client";
import { AlertsPanel } from "./components/AlertsPanel";
import { ExplorerPanel } from "./components/ExplorerPanel";
import { JobsPanel } from "./components/JobsPanel";
import { QueuePanel } from "./components/QueuePanel";
import { SourcePanel } from "./components/SourcePanel";
import { BASEMAPS, type BasemapId } from "./map/basemaps";
import { geometryBounds, MapView, STATUS_COLOR } from "./map/MapView";

const EMPTY: FeatureCollection = { type: "FeatureCollection", features: [] };
type Tab = "validate" | "sources" | "alerts" | "explore" | "jobs";
type Status = keyof typeof STATUS_COLOR;

const TABS: { id: Tab; label: string }[] = [
  { id: "validate", label: "Validate" },
  { id: "sources", label: "Sources" },
  { id: "alerts", label: "Watches" },
  { id: "explore", label: "Explore" },
  { id: "jobs", label: "Jobs" },
];

const BASEMAP_KEY = "geoapps.basemap";

function savedBasemap(): BasemapId {
  try {
    const v = localStorage.getItem(BASEMAP_KEY);
    if (v === "streets" || v === "satellite" || v === "offline") return v;
  } catch {
    /* storage unavailable */
  }
  return "streets";
}

export function App() {
  const [tab, setTab] = useState<Tab>("validate");
  const [config, setConfig] = useState<ClientConfig | null>(null);
  const [stats, setStats] = useState<Stats | null>(null);
  const [detections, setDetections] = useState<FeatureCollection>(EMPTY);
  const [queue, setQueue] = useState<Feature[]>([]);
  const [sources, setSources] = useState<FeatureCollection>(EMPTY);
  const [facilities, setFacilities] = useState<FeatureCollection>(EMPTY);
  const [watches, setWatches] = useState<FeatureCollection>(EMPTY);
  const [alerts, setAlerts] = useState<AlertOut[]>([]);
  const [datasets, setDatasets] = useState<DatasetOut[]>([]);
  const [scenes, setScenes] = useState<FeatureCollection>(EMPTY);
  const [cogTiles, setCogTiles] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [selectedSourceId, setSelectedSourceId] = useState<number | null>(null);
  const [bounds, setBounds] = useState<BBox | null>(null);
  const [focus, setFocus] = useState<[number, number, number, number] | null>(null);
  const [shown, setShown] = useState<Record<Status, boolean>>({ predicted: true, validated: true, rejected: false });
  const [basemap, setBasemap] = useState<BasemapId>(savedBasemap);
  const [toast, setToast] = useState("");
  const [offline, setOffline] = useState<string | null>(null);
  const [user, setUserState] = useState(getUser());
  const fitted = useRef(false);

  const refresh = useCallback(async () => {
    try {
      const [st, det, q, src, fac, w, al, ds] = await Promise.all([
        api.stats(),
        api.detections({ limit: 50000 }),
        api.queue({ limit: 200 }),
        api.sources(),
        api.facilities(),
        api.watches(),
        api.alerts(),
        api.datasets(),
      ]);
      setStats(st);
      setDetections(det);
      setQueue(q.features);
      setSources(src);
      setFacilities(fac);
      setWatches(w);
      setAlerts(al);
      setDatasets(ds);
      setOffline(null);
      // the first time there is data, show all of it
      if (!fitted.current && det.features.length) {
        const b = geometryBounds(det.features.map((f) => f.geometry));
        if (b) setFocus(b);
        fitted.current = true;
      }
    } catch (e) {
      setOffline(String(e));
    }
  }, []);

  useEffect(() => {
    api.config().then(setConfig, () => undefined);
    void refresh();
  }, [refresh]);

  const say = useCallback((message: string) => {
    setToast(message);
    setTimeout(() => setToast(""), 3500);
  }, []);

  const changed = useCallback(
    (message: string) => {
      if (message) say(message);
      void refresh();
    },
    [refresh, say],
  );

  const chooseBasemap = (id: BasemapId) => {
    setBasemap(id);
    try {
      localStorage.setItem(BASEMAP_KEY, id);
    } catch {
      /* storage unavailable */
    }
  };

  const visible = useMemo<FeatureCollection>(
    () => ({ ...detections, features: detections.features.filter((f) => shown[f.properties?.status as Status]) }),
    [detections, shown],
  );

  const select = useCallback(
    (id: number) => {
      setSelectedId(id);
      const f = detections.features.find((d) => d.id === id);
      if (f?.properties?.source_id) setSelectedSourceId(f.properties.source_id as number);
      const b = f && geometryBounds(f.geometry);
      if (b) setFocus(b);
    },
    [detections],
  );

  const selectSource = useCallback(
    (id: number | null) => {
      setSelectedSourceId(id);
      if (id == null) return;
      const s = sources.features.find((f) => f.id === id);
      const b = s && geometryBounds(s.geometry);
      if (b) setFocus(b);
    },
    [sources],
  );

  // the first queued plume is selected so an analyst can start with one key press
  useEffect(() => {
    if (tab === "validate" && selectedId === null && queue[0]) setSelectedId(queue[0].id as number);
  }, [tab, queue, selectedId]);

  const credits = datasets.filter((d) => d.n_detections > 0);

  return (
    <div className="app">
      <header className="top">
        <div className="brand">{config?.name ?? "geoapps"}</div>
        {stats && (
          <div className="stats">
            <span>
              <i style={{ background: STATUS_COLOR.predicted }} /> {stats.predicted.toLocaleString()} to validate
            </span>
            <span>
              <i style={{ background: STATUS_COLOR.validated }} /> {stats.validated.toLocaleString()} validated
            </span>
            <span>
              <i style={{ background: STATUS_COLOR.rejected }} /> {stats.rejected.toLocaleString()} rejected
            </span>
            <span>{stats.sources.toLocaleString()} sources</span>
            <span>{stats.alerts} alerts</span>
            {stats.queued_jobs > 0 && <span>{stats.queued_jobs} jobs queued</span>}
          </div>
        )}
        <label className="user">
          as
          <input
            className="input input-small"
            value={user}
            onChange={(e) => setUserState(e.target.value)}
            onBlur={() => {
              setUser(user || "local");
              void refresh();
            }}
          />
        </label>
      </header>
      {offline && (
        <div className="banner">
          Can't reach the API ({offline}). Start it with <code>uv run geoapps-api</code> or <code>docker compose up</code>.
        </div>
      )}
      <main className="body">
        <aside className="side">
          <nav className="tabs" role="tablist">
            {TABS.map((t) => (
              <button
                key={t.id}
                role="tab"
                aria-selected={tab === t.id}
                className={tab === t.id ? "tab on" : "tab"}
                onClick={() => setTab(t.id)}
              >
                {t.label}
                {t.id === "validate" && queue.length > 0 && <span className="count">{queue.length >= 200 ? "200+" : queue.length}</span>}
                {t.id === "alerts" && alerts.some((a) => a.state === "raised") && (
                  <span className="count">{alerts.filter((a) => a.state === "raised").length}</span>
                )}
              </button>
            ))}
          </nav>
          {tab === "validate" && (
            <QueuePanel
              queue={queue}
              selectedId={selectedId}
              onSelect={select}
              onOpenSource={(id) => {
                selectSource(id);
                setTab("sources");
              }}
              onChanged={changed}
            />
          )}
          {tab === "sources" && (
            <SourcePanel
              sources={sources.features}
              selectedSourceId={selectedSourceId}
              onSelectSource={selectSource}
              onSelectDetection={(id) => {
                select(id);
              }}
              onChanged={changed}
            />
          )}
          {tab === "alerts" && <AlertsPanel alerts={alerts} bounds={bounds} onChanged={changed} onFocusDetection={select} />}
          {tab === "explore" && (
            <ExplorerPanel
              config={config}
              bounds={bounds}
              onScenes={setScenes}
              onPreview={setCogTiles}
              onFocus={(f) => {
                const b = geometryBounds(f.geometry);
                if (b) setFocus(b);
              }}
            />
          )}
          {tab === "jobs" && <JobsPanel onChanged={changed} />}
        </aside>
        <section className="mapwrap">
          <MapView
            basemap={basemap}
            detections={visible}
            sources={sources}
            facilities={facilities}
            watches={watches}
            scenes={scenes}
            cogTiles={cogTiles}
            selectedId={selectedId}
            selectedSourceId={selectedSourceId}
            focus={focus}
            onSelect={(id) => {
              select(id);
              const f = detections.features.find((d) => d.id === id);
              setTab(f?.properties?.status === "predicted" ? "validate" : "sources");
            }}
            onSelectSource={(id) => {
              selectSource(id);
              setTab("sources");
            }}
            onBounds={setBounds}
            onBasemapFailed={(id) => {
              if (id !== "offline") {
                chooseBasemap("offline");
                say(`${BASEMAPS.find((b) => b.id === id)?.label} basemap unavailable; showing the offline map`);
              }
            }}
          />
          <div className="basemaps" role="radiogroup" aria-label="Basemap">
            {BASEMAPS.map((b) => (
              <button
                key={b.id}
                role="radio"
                aria-checked={basemap === b.id}
                className={basemap === b.id ? "seg on" : "seg"}
                onClick={() => chooseBasemap(b.id)}
              >
                {b.label}
              </button>
            ))}
          </div>
          <div className="legend">
            <div className="row wrap">
              {(Object.keys(STATUS_COLOR) as Status[]).map((s) => (
                <label key={s}>
                  <input type="checkbox" checked={shown[s]} onChange={(e) => setShown({ ...shown, [s]: e.target.checked })} />
                  <i style={{ background: STATUS_COLOR[s] }} /> {s}
                </label>
              ))}
              <span className="muted">
                <i className="ring" /> source
              </span>
              {cogTiles && (
                <button className="link" onClick={() => setCogTiles(null)}>
                  Hide preview
                </button>
              )}
            </div>
            {credits.length > 0 && (
              <div className="credits">
                {credits.map((d) => (
                  <span key={d.id}>
                    {d.attribution ?? d.name} · {d.licence}
                  </span>
                ))}
              </div>
            )}
          </div>
          {toast && <div className="toast">{toast}</div>}
        </section>
      </main>
    </div>
  );
}
