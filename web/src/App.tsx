import { useCallback, useEffect, useMemo, useState } from "react";
import {
  api,
  getUser,
  setUser,
  type AlertOut,
  type BBox,
  type ClientConfig,
  type Feature,
  type FeatureCollection,
  type Stats,
} from "./api/client";
import { AlertsPanel } from "./components/AlertsPanel";
import { ExplorerPanel } from "./components/ExplorerPanel";
import { JobsPanel } from "./components/JobsPanel";
import { geometryBounds, MapView, STATUS_COLOR } from "./components/MapView";
import { QueuePanel } from "./components/QueuePanel";

const EMPTY: FeatureCollection = { type: "FeatureCollection", features: [] };
type Tab = "validate" | "alerts" | "explore" | "jobs";
type Status = keyof typeof STATUS_COLOR;

const TABS: { id: Tab; label: string }[] = [
  { id: "validate", label: "Validate" },
  { id: "alerts", label: "Watches" },
  { id: "explore", label: "Explore" },
  { id: "jobs", label: "Jobs" },
];

export function App() {
  const [tab, setTab] = useState<Tab>("validate");
  const [config, setConfig] = useState<ClientConfig | null>(null);
  const [stats, setStats] = useState<Stats | null>(null);
  const [detections, setDetections] = useState<FeatureCollection>(EMPTY);
  const [queue, setQueue] = useState<Feature[]>([]);
  const [sources, setSources] = useState<FeatureCollection>(EMPTY);
  const [watches, setWatches] = useState<FeatureCollection>(EMPTY);
  const [alerts, setAlerts] = useState<AlertOut[]>([]);
  const [scenes, setScenes] = useState<FeatureCollection>(EMPTY);
  const [cogTiles, setCogTiles] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [bounds, setBounds] = useState<BBox | null>(null);
  const [focus, setFocus] = useState<[number, number, number, number] | null>(null);
  const [shown, setShown] = useState<Record<Status, boolean>>({ predicted: true, validated: true, rejected: false });
  const [toast, setToast] = useState("");
  const [offline, setOffline] = useState<string | null>(null);
  const [user, setUserState] = useState(getUser());

  const refresh = useCallback(async () => {
    try {
      const [st, det, q, src, w, al] = await Promise.all([
        api.stats(),
        api.detections({ limit: 5000 }),
        api.queue({ limit: 200 }),
        api.sources(),
        api.watches(),
        api.alerts(),
      ]);
      setStats(st);
      setDetections(det);
      setQueue(q.features);
      setSources(src);
      setWatches(w);
      setAlerts(al);
      setOffline(null);
    } catch (e) {
      setOffline(String(e));
    }
  }, []);

  useEffect(() => {
    api.config().then(setConfig, () => undefined);
    void refresh();
  }, [refresh]);

  const changed = useCallback(
    (message: string) => {
      if (message) {
        setToast(message);
        setTimeout(() => setToast(""), 3000);
      }
      void refresh();
    },
    [refresh],
  );

  const visible = useMemo<FeatureCollection>(
    () => ({ ...detections, features: detections.features.filter((f) => shown[f.properties?.status as Status]) }),
    [detections, shown],
  );

  const select = useCallback(
    (id: number) => {
      setSelectedId(id);
      const f = detections.features.find((d) => d.id === id);
      const b = f && geometryBounds(f.geometry);
      if (b) setFocus(b);
    },
    [detections],
  );

  // the first queued plume is selected so an analyst can start with one key press
  useEffect(() => {
    if (tab === "validate" && selectedId === null && queue[0]) setSelectedId(queue[0].id as number);
  }, [tab, queue, selectedId]);

  return (
    <div className="app">
      <header className="top">
        <div className="brand">{config?.name ?? "geoapps"}</div>
        {stats && (
          <div className="stats">
            <span>
              <i style={{ background: STATUS_COLOR.predicted }} /> {stats.predicted} to validate
            </span>
            <span>
              <i style={{ background: STATUS_COLOR.validated }} /> {stats.validated} validated
            </span>
            <span>
              <i style={{ background: STATUS_COLOR.rejected }} /> {stats.rejected} rejected
            </span>
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
                {t.id === "validate" && queue.length > 0 && <span className="count">{queue.length}</span>}
                {t.id === "alerts" && alerts.some((a) => a.state === "raised") && (
                  <span className="count">{alerts.filter((a) => a.state === "raised").length}</span>
                )}
              </button>
            ))}
          </nav>
          {tab === "validate" && <QueuePanel queue={queue} selectedId={selectedId} onSelect={select} onChanged={changed} />}
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
            detections={visible}
            sources={sources}
            watches={watches}
            scenes={scenes}
            cogTiles={cogTiles}
            selectedId={selectedId}
            focus={focus}
            onSelect={(id) => {
              setSelectedId(id);
              setTab("validate");
            }}
            onBounds={setBounds}
          />
          <div className="legend">
            {(Object.keys(STATUS_COLOR) as Status[]).map((s) => (
              <label key={s}>
                <input type="checkbox" checked={shown[s]} onChange={(e) => setShown({ ...shown, [s]: e.target.checked })} />
                <i style={{ background: STATUS_COLOR[s] }} /> {s}
              </label>
            ))}
            {cogTiles && (
              <button className="link" onClick={() => setCogTiles(null)}>
                Hide preview
              </button>
            )}
          </div>
          {toast && <div className="toast">{toast}</div>}
        </section>
      </main>
    </div>
  );
}
