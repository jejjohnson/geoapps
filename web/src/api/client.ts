// Typed API client. Types come from the generated OpenAPI schema
// (`npm run gen:api` after the backend changes), so a renamed field breaks the
// build instead of the page (gate D1).
import type { components } from "./schema";

type S = components["schemas"];
export type Feature = S["Feature"];
export type FeatureCollection = S["FeatureCollection"];
export type VerdictIn = S["VerdictIn"];
export type VerdictOut = S["VerdictOut"];
export type WatchIn = S["WatchIn"];
export type AlertOut = S["AlertOut"];
export type AlertPatch = S["AlertPatch"];
export type EtlOut = S["EtlOut"];
export type JobOut = S["JobOut"];
export type KindOut = S["KindOut"];
export type ClientConfig = S["ClientConfig"];
export type CatalogSource = S["CatalogSource"];
export type Stats = S["Stats"];

export type BBox = [number, number, number, number];

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

const USER_KEY = "geoapps.user";

export function getUser(): string {
  try {
    return localStorage.getItem(USER_KEY) || "local";
  } catch {
    return "local";
  }
}

export function setUser(user: string): void {
  try {
    localStorage.setItem(USER_KEY, user);
  } catch {
    /* storage unavailable: the name lasts for this page only */
  }
}

async function call<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(path, {
    method,
    headers: {
      "Content-Type": "application/json",
      // identity until auth exists (deferred); the API defaults to "local"
      "X-Geoapps-User": getUser(),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const j = await res.json();
      detail = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail);
    } catch {
      /* not JSON */
    }
    throw new ApiError(res.status, detail);
  }
  return (await res.json()) as T;
}

function qs(params: Record<string, string | number | undefined | null>): string {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null && v !== "") p.set(k, String(v));
  const s = p.toString();
  return s ? `?${s}` : "";
}

const bboxParam = (b?: BBox) => (b ? b.map((x) => x.toFixed(5)).join(",") : undefined);

export const api = {
  config: () => call<ClientConfig>("GET", "/api/config"),
  stats: () => call<Stats>("GET", "/api/stats"),
  kinds: () => call<KindOut[]>("GET", "/api/kinds"),

  // app 1: validation
  detections: (o: { status?: string; kind?: string; bbox?: BBox; limit?: number } = {}) =>
    call<FeatureCollection>("GET", `/api/detections${qs({ ...o, bbox: bboxParam(o.bbox) })}`),
  queue: (o: { kind?: string; limit?: number } = {}) => call<FeatureCollection>("GET", `/api/queue${qs(o)}`),
  verdict: (id: number, body: VerdictIn) => call<VerdictOut>("POST", `/api/detections/${id}/verdict`, body),
  sources: () => call<FeatureCollection>("GET", "/api/sources"),

  // app 3: watchlists and alerts
  watches: () => call<FeatureCollection>("GET", "/api/watches"),
  createWatch: (body: WatchIn) => call<{ id: number }>("POST", "/api/watches", body),
  alerts: () => call<AlertOut[]>("GET", "/api/alerts"),
  patchAlert: (id: number, body: AlertPatch) => call<AlertOut>("PATCH", `/api/alerts/${id}`, body),

  // app 4: callable ETLs and the catalog explorer
  etls: () => call<EtlOut[]>("GET", "/api/etl"),
  submitJob: (name: string, params: Record<string, unknown>) =>
    call<JobOut>("POST", `/api/etl/${encodeURIComponent(name)}/jobs`, { params }),
  job: (id: number) => call<JobOut>("GET", `/api/jobs/${id}`),
  search: (o: { source: string; bbox: BBox; collection?: string; start?: string; end?: string; limit?: number }) =>
    call<FeatureCollection>("GET", `/api/explore/search${qs({ ...o, bbox: bboxParam(o.bbox) })}`),
};

/** XYZ tile template for previewing one COG through titiler, never copying it. */
export function cogTileUrl(titiler: string, href: string, opts: { rescale?: string; bidx?: string } = {}): string {
  const p = new URLSearchParams({ url: href });
  if (opts.rescale) p.set("rescale", opts.rescale);
  if (opts.bidx) for (const b of opts.bidx.split(",")) p.append("bidx", b.trim());
  return `${titiler.replace(/\/$/, "")}/cog/tiles/WebMercatorQuad/{z}/{x}/{y}.png?${p.toString()}`;
}
