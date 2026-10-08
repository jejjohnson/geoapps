import { useEffect, useState } from "react";
import { api, type EtlOut, type JobOut } from "../api/client";

type Props = { onChanged: (message: string) => void };

type Prop = { type?: string; default?: unknown; description?: string };

function defaults(schema: Record<string, unknown>): Record<string, unknown> {
  const props = (schema.properties ?? {}) as Record<string, Prop>;
  return Object.fromEntries(Object.entries(props).flatMap(([k, v]) => ("default" in v ? [[k, v.default]] : [])));
}

/** Callable ETLs: every registered step, its parameters, and the jobs you submit. */
export function JobsPanel({ onChanged }: Props) {
  const [etls, setEtls] = useState<EtlOut[]>([]);
  const [name, setName] = useState("");
  const [params, setParams] = useState("{}");
  const [jobs, setJobs] = useState<JobOut[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.etls().then((list) => {
      setEtls(list);
      // a fresh install has no data, so offer the public plume import first
      const first = list.find((e) => e.name === "import_mars_plumes") ?? list[0];
      if (first) {
        setName(first.name);
        setParams(JSON.stringify(defaults(first.params_schema), null, 2));
      }
    }, (e) => setError(String(e)));
  }, []);

  // poll unfinished jobs until the worker has run them
  useEffect(() => {
    if (!jobs.some((j) => j.state === "queued" || j.state === "running")) return;
    const t = setInterval(async () => {
      const fresh = await Promise.all(jobs.map((j) => (j.state === "done" || j.state === "failed" ? j : api.job(j.id))));
      setJobs(fresh);
      if (fresh.some((j, i) => j.state !== jobs[i].state && j.state === "done")) onChanged("Job finished");
    }, 1500);
    return () => clearInterval(t);
  }, [jobs, onChanged]);

  const etl = etls.find((e) => e.name === name);

  function pick(n: string) {
    setName(n);
    const e = etls.find((x) => x.name === n);
    if (e) setParams(JSON.stringify(defaults(e.params_schema), null, 2));
  }

  async function submit() {
    setError(null);
    let parsed: Record<string, unknown>;
    try {
      parsed = JSON.parse(params || "{}");
    } catch {
      setError("Parameters are not valid JSON.");
      return;
    }
    try {
      const job = await api.submitJob(name, parsed);
      setJobs((js) => [job, ...js]);
    } catch (e) {
      setError(String(e)); // a 422 here means no job was created (gate H1)
    }
  }

  return (
    <div className="panel-body">
      <div className="card">
        <label className="field">
          Step
          <select className="input" value={name} onChange={(e) => pick(e.target.value)}>
            {etls.map((e) => (
              <option key={e.name} value={e.name}>
                {e.name}
              </option>
            ))}
          </select>
        </label>
        {etl && (
          <p className="hint">
            {etl.description} · v{etl.version}
            {etl.writes.length > 0 && <> · writes {etl.writes.join(", ")}</>}
          </p>
        )}
        <label className="field">
          Parameters (JSON)
          <textarea className="input mono" rows={6} value={params} onChange={(e) => setParams(e.target.value)} />
        </label>
        <button className="btn" onClick={submit} disabled={!name}>
          Submit job
        </button>
        {error && <p className="error">{error}</p>}
        {!etls.length && !error && <p className="hint">No steps registered yet. Start a worker; it registers its steps.</p>}
      </div>
      <ul className="list">
        {jobs.map((j) => (
          <li key={j.id} className="job">
            <div className="row spread">
              <span className="mono">
                #{j.id} {j.etl}
              </span>
              <span className={`pill pill-${j.state}`}>{j.state}</span>
            </div>
            {j.error && <div className="error mono">{j.error}</div>}
            {j.result && (
              <div className="muted mono">
                {JSON.stringify(Object.fromEntries(Object.entries(j.result).filter(([k]) => k !== "log")))}
              </div>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
