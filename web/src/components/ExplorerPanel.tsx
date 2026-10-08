import { useState } from "react";
import { api, cogTileUrl, type BBox, type ClientConfig, type Feature, type FeatureCollection } from "../api/client";

type Props = {
  config: ClientConfig | null;
  bounds: BBox | null;
  onScenes: (fc: FeatureCollection) => void;
  onPreview: (tiles: string | null) => void;
  onFocus: (f: Feature) => void;
};

/** App 4: see what a public catalog holds here, preview a scene through titiler, decide whether to ingest. */
export function ExplorerPanel({ config, bounds, onScenes, onPreview, onFocus }: Props) {
  const sources = config?.sources ?? [];
  const [source, setSource] = useState("");
  const [collection, setCollection] = useState("");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [items, setItems] = useState<Feature[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [previewing, setPreviewing] = useState<string | null>(null);
  const [rescale, setRescale] = useState("0,3000");

  const src = sources.find((s) => s.name === (source || sources[0]?.name));

  async function search() {
    if (!bounds || !src) return;
    setBusy(true);
    setError(null);
    try {
      const fc = await api.search({
        source: src.name,
        bbox: bounds,
        collection: collection || undefined,
        start: start ? new Date(start).toISOString() : undefined,
        end: end ? new Date(end).toISOString() : undefined,
        limit: 50,
      });
      setItems(fc.features);
      onScenes(fc);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  function preview(f: Feature, asset: string) {
    const href = (f.properties?.cog_assets as Record<string, string>)[asset];
    const key = `${f.id}/${asset}`;
    if (previewing === key) {
      setPreviewing(null);
      onPreview(null);
      return;
    }
    setPreviewing(key);
    onPreview(cogTileUrl(config!.titiler_url, href, { rescale }));
    onFocus(f);
  }

  if (!sources.length)
    return (
      <div className="panel-body">
        <p className="empty">
          No catalogs configured. Add a <code>[[sources]]</code> entry to <code>geoapps.toml</code> (see{" "}
          <code>geoapps.toml.example</code>) and restart the API.
        </p>
      </div>
    );

  return (
    <div className="panel-body">
      <div className="card">
        <label className="field">
          Catalog
          <select className="input" value={src?.name} onChange={(e) => setSource(e.target.value)}>
            {sources.map((s) => (
              <option key={s.name} value={s.name}>
                {s.name}
              </option>
            ))}
          </select>
        </label>
        {src?.description && <p className="hint">{src.description} · licence: {src.licence}</p>}
        <label className="field">
          Collection
          <select className="input" value={collection} onChange={(e) => setCollection(e.target.value)}>
            <option value="">{src?.collections.length ? "All configured" : "Any"}</option>
            {src?.collections.map((c) => (
              <option key={c}>{c}</option>
            ))}
          </select>
        </label>
        <div className="row">
          <label className="field">
            From
            <input className="input" type="date" value={start} onChange={(e) => setStart(e.target.value)} />
          </label>
          <label className="field">
            To
            <input className="input" type="date" value={end} onChange={(e) => setEnd(e.target.value)} />
          </label>
        </div>
        <label className="field">
          Preview stretch (min,max)
          <input className="input" value={rescale} onChange={(e) => setRescale(e.target.value)} />
        </label>
        <button className="btn" onClick={search} disabled={busy || !bounds}>
          {busy ? "Searching…" : "Search this view"}
        </button>
        {error && <p className="error">{error}</p>}
      </div>
      <ul className="list scenes">
        {items.map((f) => {
          const assets = Object.keys((f.properties?.cog_assets as Record<string, string>) ?? {});
          return (
            <li key={String(f.id)}>
              <button className="link mono" onClick={() => onFocus(f)}>
                {String(f.id)}
              </button>
              <div className="muted">
                {String(f.properties?.datetime ?? "").slice(0, 16).replace("T", " ")}
                {typeof f.properties?.cloud_cover === "number" && ` · ${f.properties.cloud_cover.toFixed(0)}% cloud`}
              </div>
              <div className="row wrap">
                {assets.slice(0, 8).map((a) => (
                  <button
                    key={a}
                    className={`btn btn-small ${previewing === `${f.id}/${a}` ? "btn-on" : ""}`}
                    onClick={() => preview(f, a)}
                  >
                    {a}
                  </button>
                ))}
                {!assets.length && <span className="muted">no COG assets</span>}
              </div>
            </li>
          );
        })}
      </ul>
      {items.length > 0 && (
        <p className="hint">Ingest is the next step: a callable ETL that crops, references or mirrors per the catalog's setting.</p>
      )}
    </div>
  );
}
