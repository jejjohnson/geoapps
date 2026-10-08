import { useState } from "react";
import { api, type AlertOut, type BBox } from "../api/client";

type Props = {
  alerts: AlertOut[];
  bounds: BBox | null;
  onChanged: (message: string) => void;
  onFocusDetection: (id: number) => void;
};

const REASONS = ["not a plume", "wrong source", "below my threshold", "already known"];

/** App 3: watches over an area, and the alerts a validated plume raises on them. */
export function AlertsPanel({ alerts, bounds, onChanged, onFocusDetection }: Props) {
  const [name, setName] = useState("");
  const [minQ, setMinQ] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function watchView() {
    if (!bounds) return;
    const [w, s, e, n] = bounds;
    setError(null);
    try {
      await api.createWatch({
        name: name || "My view",
        kind: "ch4_plume",
        min_q_kg_h: minQ ? Number(minQ) : null,
        geometry: { type: "Polygon", coordinates: [[[w, s], [e, s], [e, n], [w, n], [w, s]]] },
      });
      setName("");
      onChanged("Watch created over the current view");
    } catch (e) {
      setError(String(e));
    }
  }

  async function patch(a: AlertOut, state: "seen" | "kept" | "dismissed", reason?: string) {
    await api.patchAlert(a.id, { state, reason: reason ?? null });
    onChanged(state === "dismissed" ? `Alert dismissed: ${reason}` : `Alert marked ${state}`);
  }

  return (
    <div className="panel-body">
      <div className="card">
        <div className="card-head">
          <strong>Watch this view</strong>
        </div>
        <input className="input" placeholder="Name" value={name} onChange={(e) => setName(e.target.value)} />
        <input
          className="input"
          placeholder="Minimum flux, kg/h (optional)"
          inputMode="decimal"
          value={minQ}
          onChange={(e) => setMinQ(e.target.value)}
        />
        <button className="btn" onClick={watchView} disabled={!bounds}>
          Create watch
        </button>
        {error && <p className="error">{error}</p>}
        <p className="hint">Only validated plumes raise alerts. Outbound notifications come later; alerts land here.</p>
      </div>
      {alerts.length === 0 && <p className="empty">No alerts yet.</p>}
      <ul className="list alerts">
        {alerts.map((a) => (
          <li key={a.id} className={`alert alert-${a.state}`}>
            <div className="row spread">
              <button className="link" onClick={() => onFocusDetection(a.detection.id as number)}>
                Plume #{String(a.detection.id)}
              </button>
              <span className={`pill pill-${a.state}`}>{a.state}</span>
            </div>
            <div className="muted">
              {a.watch.name as string} · {Math.round(Number(a.detection.q_kg_h ?? 0))} kg/h
            </div>
            {a.state !== "dismissed" && a.state !== "kept" && (
              <div className="row wrap">
                <button className="btn btn-small" onClick={() => patch(a, "kept")}>
                  Keep
                </button>
                <select
                  className="input input-small"
                  value=""
                  onChange={(e) => e.target.value && patch(a, "dismissed", e.target.value)}
                >
                  <option value="">Dismiss because…</option>
                  {REASONS.map((r) => (
                    <option key={r}>{r}</option>
                  ))}
                </select>
              </div>
            )}
            {a.reason && <div className="muted">“{a.reason}”</div>}
          </li>
        ))}
      </ul>
    </div>
  );
}
