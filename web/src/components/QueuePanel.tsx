import { useEffect, useState } from "react";
import { api, ApiError, type Feature } from "../api/client";

type Props = {
  queue: Feature[];
  selectedId: number | null;
  onSelect: (id: number) => void;
  onOpenSource: (id: number) => void;
  onChanged: (message: string) => void;
};

const fmt = (x: unknown, digits = 0) => (typeof x === "number" ? x.toFixed(digits) : "—");

function ageHours(iso: unknown): string {
  if (typeof iso !== "string") return "—";
  const h = (Date.now() - new Date(iso).getTime()) / 3.6e6;
  return h < 48 ? `${h.toFixed(0)} h` : `${(h / 24).toFixed(1)} d`;
}

/** App 1: the analyst's validation queue, highest priority first. A human verdict is final. */
export function QueuePanel({ queue, selectedId, onSelect, onOpenSource, onChanged }: Props) {
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const idx = queue.findIndex((f) => f.id === selectedId);
  const current = idx >= 0 ? queue[idx] : null;

  async function decide(verdict: "confirm" | "reject") {
    if (!current || busy) return;
    setBusy(true);
    setError(null);
    try {
      const out = await api.verdict(current.id as number, { verdict, note: note || null });
      setNote("");
      const next = queue[idx + 1] ?? queue[idx - 1];
      if (next) onSelect(next.id as number);
      onChanged(
        verdict === "confirm"
          ? `Plume ${current.id} validated${out.alerts_raised ? `, ${out.alerts_raised} alert(s) raised` : ""}`
          : `Plume ${current.id} rejected`,
      );
    } catch (e) {
      setError(e instanceof ApiError && e.status === 409 ? "Someone already reviewed this plume." : String(e));
      onChanged("");
    } finally {
      setBusy(false);
    }
  }

  // keyboard: j / k move, c confirms, r rejects (ignored while typing a note)
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement).tagName === "INPUT" || (e.target as HTMLElement).tagName === "TEXTAREA") return;
      if (e.key === "j" && queue[idx + 1]) onSelect(queue[idx + 1].id as number);
      else if (e.key === "k" && queue[idx - 1]) onSelect(queue[idx - 1].id as number);
      else if (e.key === "c") void decide("confirm");
      else if (e.key === "r") void decide("reject");
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  return (
    <div className="panel-body">
      {current ? (
        <div className="card">
          <div className="card-head">
            <strong>Plume {current.id}</strong>
            <span className="pill pill-predicted">predicted</span>
          </div>
          <dl className="marks">
            <dt>Flux</dt>
            <dd>
              {current.properties?.q_kg_h == null
                ? "not quantified"
                : `${fmt(current.properties?.q_kg_h)} ± ${fmt(current.properties?.q_sigma_kg_h)} kg/h`}
            </dd>
            <dt>Sensor</dt>
            <dd>{String(current.properties?.sensor ?? "—")}</dd>
            <dt>Observed</dt>
            <dd>{String(current.properties?.observed_at ?? "").slice(0, 16).replace("T", " ")} UTC</dd>
            <dt>Probability</dt>
            <dd>{fmt(current.properties?.p, 2)}</dd>
            <dt>Viability</dt>
            <dd>{fmt(current.properties?.viability, 2)}</dd>
            <dt>Priority</dt>
            <dd>{fmt(current.properties?.priority, 3)}</dd>
            <dt>Age</dt>
            <dd>{ageHours(current.properties?.observed_at)}</dd>
            <dt>Scene</dt>
            <dd className="mono ellipsis">{String(current.properties?.scene_id ?? "—")}</dd>
            {current.properties?.source_id != null && (
              <>
                <dt>Source</dt>
                <dd>
                  <button className="link" onClick={() => onOpenSource(current.properties!.source_id as number)}>
                    #{String(current.properties.source_id)} history →
                  </button>
                </dd>
              </>
            )}
          </dl>
          <input
            className="input"
            placeholder="Note (optional)"
            value={note}
            onChange={(e) => setNote(e.target.value)}
          />
          <div className="row">
            <button className="btn btn-confirm" disabled={busy} onClick={() => decide("confirm")}>
              Confirm <kbd>c</kbd>
            </button>
            <button className="btn btn-reject" disabled={busy} onClick={() => decide("reject")}>
              Reject <kbd>r</kbd>
            </button>
          </div>
          {error && <p className="error">{error}</p>}
          <p className="hint">
            <kbd>j</kbd>/<kbd>k</kbd> next and previous. Redraw is in the API; drawing on the map comes next.
          </p>
        </div>
      ) : (
        <p className="empty">
          {queue.length ? "Pick a plume from the list or the map." : "Nothing to validate. Import plumes from the Jobs tab."}
        </p>
      )}
      <ol className="list">
        {queue.map((f) => (
          <li key={f.id} className={f.id === selectedId ? "sel" : ""} onClick={() => onSelect(f.id as number)}>
            <span className="mono">#{f.id}</span>
            <span>{f.properties?.q_kg_h == null ? "—" : `${fmt(f.properties?.q_kg_h)} kg/h`}</span>
            <span className="muted">{ageHours(f.properties?.observed_at)}</span>
            <span className="prio">{fmt(f.properties?.priority, 2)}</span>
          </li>
        ))}
      </ol>
    </div>
  );
}
