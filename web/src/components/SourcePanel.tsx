import { Fragment, useEffect, useMemo, useState } from "react";
import { api, type Feature, type Proposal, type SourceDetail } from "../api/client";
import { STATUS_COLOR } from "../map/MapView";

type Props = {
  sources: Feature[];
  selectedSourceId: number | null;
  onSelectSource: (id: number | null) => void;
  onSelectDetection: (id: number) => void;
  onChanged: (message: string) => void;
};

const day = (iso?: string | null) => (iso ? iso.slice(0, 10) : "—");
const kgh = (x?: number | null) => (typeof x === "number" ? `${Math.round(x).toLocaleString()} kg/h` : "—");

/** One flux per detection along time: a strip, so a source's history reads at a glance. */
function FluxStrip({ detail, onPick }: { detail: SourceDetail; onPick: (id: number) => void }) {
  const dets = detail.detections;
  if (!dets.length) return null;
  const t = dets.map((d) => new Date(d.observed_at).getTime());
  const t0 = Math.min(...t), t1 = Math.max(...t);
  const qmax = Math.max(1, ...dets.map((d) => d.q_kg_h ?? 0));
  const W = 300, H = 64, pad = 6;
  const x = (ti: number) => (t1 === t0 ? W / 2 : pad + ((ti - t0) / (t1 - t0)) * (W - 2 * pad));
  const y = (q: number | null | undefined) => H - pad - ((q ?? 0) / qmax) * (H - 2 * pad);
  return (
    <svg className="strip" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Flux of each detection over time">
      {detail.events.map((e) => (
        <rect
          key={e.id}
          x={x(new Date(e.t_b).getTime()) - 3}
          width={Math.max(6, x(new Date(e.t_c).getTime()) - x(new Date(e.t_b).getTime()) + 6)}
          y={2}
          height={H - 4}
          rx={3}
          className="strip-event"
        />
      ))}
      <line x1={pad} x2={W - pad} y1={H - pad} y2={H - pad} className="strip-axis" />
      {dets.map((d, i) => (
        <circle
          key={d.id}
          cx={x(t[i])}
          cy={y(d.q_kg_h)}
          r={d.q_kg_h == null ? 2.5 : 3.5}
          fill={STATUS_COLOR[d.status as keyof typeof STATUS_COLOR] ?? "#999"}
          onClick={() => onPick(d.id)}
        >
          <title>{`${day(d.observed_at)} · ${kgh(d.q_kg_h)} · ${d.status}`}</title>
        </circle>
      ))}
    </svg>
  );
}

/** Apps 2 and 4: one source's history, its events, and who is behind it. */
export function SourcePanel({ sources, selectedSourceId, onSelectSource, onSelectDetection, onChanged }: Props) {
  const [detail, setDetail] = useState<SourceDetail | null>(null);
  const [proposals, setProposals] = useState<Proposal[] | null>(null);
  const [filter, setFilter] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setProposals(null);
    setError(null);
    if (selectedSourceId == null) return setDetail(null);
    api.source(selectedSourceId).then(setDetail, (e) => setError(String(e)));
  }, [selectedSourceId]);

  const ranked = useMemo(() => {
    const f = filter.trim().toLowerCase();
    return sources
      .filter((s) => !f || [s.properties?.name, s.properties?.country, s.properties?.sector].some((v) => String(v ?? "").toLowerCase().includes(f)))
      .sort((a, b) => Number(b.properties?.n_detections ?? 0) - Number(a.properties?.n_detections ?? 0))
      .slice(0, 300);
  }, [sources, filter]);

  async function propose() {
    if (!detail) return;
    try {
      setProposals(await api.propose(detail.id));
    } catch (e) {
      setError(String(e));
    }
  }

  async function decide(p: Proposal, confirm: boolean) {
    try {
      await api.decide(p.id, confirm, detail?.first_seen ?? undefined);
      setDetail(await api.source(detail!.id));
      setProposals((ps) => ps?.filter((x) => x.id !== p.id) ?? null);
      onChanged(confirm ? "Attribution confirmed" : "Proposal rejected");
    } catch (e) {
      setError(String(e));
    }
  }

  if (detail)
    return (
      <div className="panel-body">
        <button className="link" onClick={() => onSelectSource(null)}>
          ← All sources
        </button>
        <div className="card">
          <div className="card-head">
            <strong>{detail.name}</strong>
            <span className="pill">{detail.status}</span>
          </div>
          <dl className="marks">
            <dt>Country</dt>
            <dd>{detail.country ?? "—"}</dd>
            <dt>Sector</dt>
            <dd>{detail.sector ?? "—"}</dd>
            <dt>Seen</dt>
            <dd>
              {day(detail.first_seen)} → {day(detail.last_seen)}
            </dd>
            <dt>Detections</dt>
            <dd>{detail.detections.length}</dd>
            {detail.xrefs.map((x) => (
              <Fragment key={`${x.provider}/${x.record_id}`}>
                <dt>{x.provider}</dt>
                <dd className="mono">{x.record_id}</dd>
              </Fragment>
            ))}
          </dl>
          <FluxStrip detail={detail} onPick={onSelectDetection} />
          <p className="hint">Each dot is a detection (height = flux); shaded spans are events.</p>
        </div>

        <div className="card">
          <div className="card-head">
            <strong>Events</strong>
            <span className="muted">{detail.events.length}</span>
          </div>
          {detail.events.length === 0 && <p className="hint">Events are chained from validated detections only.</p>}
          <table className="table">
            <tbody>
              {detail.events.map((e) => (
                <tr key={e.id}>
                  <td>
                    {day(e.t_b)}
                    {e.t_c !== e.t_b && <> → {day(e.t_c)}</>}
                  </td>
                  <td>{e.n_detections}×</td>
                  <td>{kgh(e.q_mean_kg_h)}</td>
                  <td>
                    <span className={`pill pill-${e.status === "open" ? "raised" : "seen"}`}>{e.status}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="hint">With no clear looks recorded, an event closes after 30 days without a plume.</p>
        </div>

        <div className="card">
          <div className="card-head">
            <strong>Who is behind it</strong>
          </div>
          {detail.who ? (
            <dl className="marks">
              <dt>Facility</dt>
              <dd>{String(detail.who.facility.name)}</dd>
              <dt>Asset</dt>
              <dd>{detail.who.asset ? String(detail.who.asset.name) : "—"}</dd>
              <dt>Operator</dt>
              <dd>{detail.who.operator ? String(detail.who.operator.org) : "—"}</dd>
              <dt>Government</dt>
              <dd>{detail.who.governments.map((g) => String(g.org)).join(", ") || "—"}</dd>
            </dl>
          ) : (
            <p className="hint">Not attributed yet. Facilities come from an inventory import or an analyst.</p>
          )}
          <button className="btn" onClick={propose}>
            Find nearby facilities
          </button>
          {proposals && proposals.length === 0 && <p className="hint">No facility within 2 km.</p>}
          {proposals?.map((p) => (
            <div key={p.id} className="row spread">
              <span>
                #{p.facility_id} · {Math.round(p.distance_m)} m · p = {p.score.toFixed(2)}
              </span>
              <span className="row">
                <button className="btn btn-small" onClick={() => decide(p, true)}>
                  Confirm
                </button>
                <button className="btn btn-small" onClick={() => decide(p, false)}>
                  Reject
                </button>
              </span>
            </div>
          ))}
          {error && <p className="error">{error}</p>}
        </div>
      </div>
    );

  return (
    <div className="panel-body">
      <input className="input" placeholder="Filter by name, country or sector" value={filter} onChange={(e) => setFilter(e.target.value)} />
      {sources.length === 0 && <p className="empty">No sources yet. Import plumes from the Jobs tab.</p>}
      <ol className="list">
        {ranked.map((s) => (
          <li key={String(s.id)} onClick={() => onSelectSource(s.id as number)}>
            <span className="mono">{String(s.properties?.name)}</span>
            <span className="muted ellipsis">{String(s.properties?.country ?? "")}</span>
            <span className="prio">{String(s.properties?.n_detections ?? 0)}</span>
          </li>
        ))}
      </ol>
      {error && <p className="error">{error}</p>}
    </div>
  );
}
