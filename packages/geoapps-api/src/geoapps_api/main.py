"""FastAPI application: the contract the shell and geoapps-client both use.

Routes (all under /api):
    health, stats, config, kinds                  instance basics
    detections, queue, detections/{id}/verdict    app 1, validation (E)
    sources, sources/{id}, facilities, sensors    reference layers and one source's history
    events                                        episodes chained from validated detections
    sources/{id}/propose, attributions/{id}       app 2, attribution proposals and decisions (F)
    datasets                                      provenance and licences, for map credits
    watches, alerts, feedback                     app 3, watchlists and alerts (G3)
    etl, etl/{name}/jobs, jobs/{id}               registered steps and jobs (H1, K)
    explore/search                                catalog explorer, search only (H2)

Single-user mode (auth disabled) takes the user name from the ``X-Geoapps-User``
header, defaulting to "local". Sign-in arrives with the authentication design.
"""

import os
from collections.abc import Iterator
from datetime import datetime
from typing import Annotated, Any

import jsonschema
from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session

from geoapps_api import schemas as S
from geoapps_core import kinds as all_kinds
from geoapps_core.config import InstanceConfig, load_config
from geoapps_db import repo, session_scope

app = FastAPI(
    title="geoapps",
    version="0.0.1",
    description="Validation, attribution, watchlists and research over remote-sensing events.",
    openapi_url="/api/openapi.json",
    docs_url="/api/docs",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("GEOAPPS_CORS_ORIGINS", "http://localhost:5173").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── dependencies ────────────────────────────────────────────────────────────
def get_session() -> Iterator[Session]:
    with session_scope() as session:
        yield session


def get_config() -> InstanceConfig:
    return load_config()


def current_user(x_geoapps_user: Annotated[str | None, Header()] = None) -> str:
    return (x_geoapps_user or "local").strip()[:128] or "local"


DB = Annotated[Session, Depends(get_session)]
Cfg = Annotated[InstanceConfig, Depends(get_config)]
User = Annotated[str, Depends(current_user)]


def parse_bbox(bbox: str | None) -> tuple[float, float, float, float] | None:
    if not bbox:
        return None
    try:
        west, south, east, north = (float(v) for v in bbox.split(","))
    except ValueError:
        raise HTTPException(422, "bbox must be west,south,east,north") from None
    return west, south, east, north


# ── basics ──────────────────────────────────────────────────────────────────
@app.get("/api/health")
def health(session: DB) -> dict[str, Any]:
    session.execute(text("select 1"))
    return {"status": "ok"}


@app.get("/api/stats", response_model=S.Stats)
def stats(session: DB):
    return repo.counts(session)


@app.get("/api/config", response_model=S.ClientConfig)
def client_config(cfg: Cfg):
    return S.ClientConfig(
        name=cfg.name,
        titiler_url=cfg.titiler_url,
        auth_enabled=cfg.auth.enabled,
        sources=[S.CatalogSource(**s.model_dump()) for s in cfg.sources],
    )


@app.get("/api/kinds", response_model=list[S.KindOut])
def list_kinds():
    return [
        S.KindOut(
            name=k.name,
            title=k.title,
            geometry=k.geometry,
            validation=k.validation,
            entities=list(k.entities),
            marks_schema=k.marks.model_json_schema(),
        )
        for k in all_kinds()
    ]


# ── app 1: validation ───────────────────────────────────────────────────────
@app.get("/api/detections", response_model=S.FeatureCollection)
def detections(
    session: DB,
    status: Annotated[str | None, Query(pattern="^(predicted|validated|rejected)$")] = None,
    kind: str | None = None,
    source_id: int | None = None,
    bbox: str | None = None,
    limit: Annotated[int, Query(ge=1, le=50000)] = 20000,
):
    return repo.detections_geojson(
        session, status=status, kind=kind, source_id=source_id, bbox=parse_bbox(bbox), limit=limit
    )


@app.get("/api/queue", response_model=S.FeatureCollection)
def validation_queue(
    session: DB, kind: str | None = None, limit: Annotated[int, Query(ge=1, le=500)] = 50
):
    return repo.queue(session, kind=kind, limit=limit)


@app.post("/api/detections/{detection_id}/verdict", response_model=S.VerdictOut)
def verdict(detection_id: int, body: S.VerdictIn, session: DB, user: User):
    try:
        res = repo.record_verdict(
            session,
            detection_id,
            verdict=body.verdict,
            analyst=user,
            geometry=body.geometry,
            note=body.note,
        )
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from None
    except repo.NotReviewable as exc:
        raise HTTPException(409, str(exc)) from None
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    return S.VerdictOut(label_id=res.label_id, status=res.status, alerts_raised=res.alerts_raised)


@app.get("/api/sources", response_model=S.FeatureCollection)
def sources(session: DB):
    return repo.sources_geojson(session)


@app.get("/api/sources/{source_id}", response_model=S.SourceDetail)
def source(source_id: int, session: DB):
    out = repo.source_detail(session, source_id)
    if out is None:
        raise HTTPException(404, f"source {source_id} not found")
    return out


@app.get("/api/facilities", response_model=S.FeatureCollection)
def facilities(session: DB):
    return repo.facilities_geojson(session)


@app.get("/api/sensors", response_model=list[S.SensorOut])
def sensors(session: DB):
    return repo.list_sensors(session)


@app.get("/api/events", response_model=list[S.EventOut])
def events(
    session: DB,
    status: Annotated[str | None, Query(pattern="^(open|closed)$")] = None,
    limit: Annotated[int, Query(ge=1, le=5000)] = 500,
):
    return repo.list_events(session, status=status, limit=limit)


@app.get("/api/datasets", response_model=list[S.DatasetOut])
def datasets(session: DB):
    return repo.list_datasets(session)


# ── app 2: attribution ──────────────────────────────────────────────────────
@app.post("/api/sources/{source_id}/propose", response_model=list[S.Proposal])
def propose(source_id: int, session: DB, radius_m: Annotated[float, Query(gt=0, le=20000)] = 2000):
    try:
        return repo.propose_source_facilities(session, source_id, radius_m=radius_m)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from None


@app.post("/api/attributions/{link_id}", response_model=S.AttributionLink)
def decide(link_id: int, body: S.DecisionIn, session: DB, user: User):
    try:
        link = repo.decide_proposal(
            session, link_id, confirm=body.confirm, decided_by=user, valid_from=body.valid_from
        )
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from None
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from None
    return next(lk for lk in repo.links_for_source(session, link.source_id) if lk["id"] == link.id)


# ── app 3: watchlists and alerts ────────────────────────────────────────────
@app.get("/api/watches", response_model=S.FeatureCollection)
def watches(session: DB, user: User, mine: bool = True):
    return repo.watches_geojson(session, owner=user if mine else None)


@app.post("/api/watches", response_model=S.WatchOut, status_code=201)
def create_watch(body: S.WatchIn, session: DB, user: User):
    if body.geometry.get("type") != "Polygon":
        raise HTTPException(422, "a watch area must be a Polygon")
    try:
        w = repo.create_watch(
            session,
            owner=user,
            name=body.name,
            geometry=body.geometry,
            kind=body.kind,
            min_q_kg_h=body.min_q_kg_h,
        )
    except KeyError as exc:
        raise HTTPException(422, str(exc)) from None
    return S.WatchOut(id=w.id)


@app.get("/api/alerts", response_model=list[S.AlertOut])
def alerts(session: DB, user: User, mine: bool = True):
    return repo.list_alerts(session, owner=user if mine else None)


@app.patch("/api/alerts/{alert_id}", response_model=S.AlertOut)
def patch_alert(alert_id: int, body: S.AlertPatch, session: DB, user: User):
    try:
        repo.set_alert_state(session, alert_id, body.state, body.reason, by=user)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from None
    return next(a for a in repo.list_alerts(session) if a["id"] == alert_id)


@app.get("/api/feedback", response_model=list[S.FeedbackOut])
def feedback(session: DB):
    return repo.list_feedback(session)


# ── registered steps and jobs ───────────────────────────────────────────────
@app.get("/api/etl", response_model=list[S.EtlOut])
def etls(session: DB):
    return repo.list_etls(session)


@app.post("/api/etl/{name}/jobs", response_model=S.JobOut, status_code=202)
def submit_job(name: str, body: S.JobIn, session: DB, user: User):
    """Validate parameters against the step's schema before any job exists (gate H1)."""
    step = repo.get_etl(session, name)
    if step is None:
        raise HTTPException(404, f"no registered step named {name!r}")
    try:
        jsonschema.validate(body.params, step.params_schema)
    except jsonschema.ValidationError as exc:
        raise HTTPException(422, f"invalid parameters: {exc.message}") from None
    job = repo.enqueue_job(session, etl=name, params=body.params, submitted_by=user)
    return repo.get_job(session, job.id)


@app.get("/api/jobs/{job_id}", response_model=S.JobOut)
def job(job_id: int, session: DB):
    out = repo.get_job(session, job_id)
    if out is None:
        raise HTTPException(404, f"job {job_id} not found")
    return out


# ── explorer: search public catalogs without copying anything (H2) ──────────
@app.get("/api/explore/search", response_model=S.FeatureCollection)
def explore_search(
    cfg: Cfg,
    source: str,
    bbox: str,
    collection: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
):
    from pystac_client import Client  # imported lazily: only the explorer needs it

    try:
        src = cfg.source(source)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from None
    collections = [collection] if collection else src.collections or None
    dt = None
    if start or end:
        dt = f"{start.isoformat() if start else '..'}/{end.isoformat() if end else '..'}"
    try:
        search = Client.open(src.url).search(
            bbox=parse_bbox(bbox), collections=collections, datetime=dt, max_items=limit
        )
        items = list(search.items())
    except Exception as exc:  # the remote catalog is outside our control
        raise HTTPException(502, f"catalog {source!r} failed: {exc}") from None
    feats = []
    for it in items:
        cogs = {
            k: a.href
            for k, a in it.assets.items()
            if (a.media_type or "").startswith("image/tiff")
            or a.href.lower().endswith((".tif", ".tiff"))
        }
        feats.append(
            {
                "type": "Feature",
                "id": it.id,
                "geometry": it.geometry,
                "properties": {
                    "collection": it.collection_id,
                    "datetime": it.datetime.isoformat() if it.datetime else None,
                    "cloud_cover": it.properties.get("eo:cloud_cover"),
                    "cog_assets": cogs,
                    "source": src.name,
                    "licence": src.licence,
                },
            }
        )
    return {"type": "FeatureCollection", "features": feats}


def serve() -> None:
    import uvicorn

    uvicorn.run(
        "geoapps_api.main:app",
        host=os.environ.get("GEOAPPS_API_HOST", "0.0.0.0"),
        port=int(os.environ.get("GEOAPPS_API_PORT", "8000")),
        reload=bool(os.environ.get("GEOAPPS_API_RELOAD")),
    )


def dump_openapi() -> None:
    """Write the OpenAPI schema the web client's types are generated from."""
    import json
    import sys

    path = sys.argv[1] if len(sys.argv) > 1 else "web/openapi.json"
    with open(path, "w") as f:
        json.dump(app.openapi(), f, indent=2)
        f.write("\n")
    print(f"wrote {path}")
