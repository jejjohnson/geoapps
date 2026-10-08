"""App 2: source → facility links, and the assets and orgs behind a facility, over time."""

from datetime import UTC, datetime
from typing import Any

import numpy as np
from geoalchemy2 import Geography
from geoalchemy2 import functions as gf
from sqlalchemy import cast, func, select
from sqlalchemy.dialects.postgresql import TIMESTAMP, Range
from sqlalchemy.orm import Session

from geoapps_core import (
    attribution_scale,
    bearing_deg,
    candidate_probabilities,
    haversine_m,
    wind_to_deg,
)
from geoapps_db.models import (
    Asset,
    Detection,
    Facility,
    FacilityAsset,
    FacilityGovernment,
    Org,
    OrgAsset,
    Source,
    SourceFacility,
)
from geoapps_db.repo._util import iso


def _at(when: datetime):
    return cast(when, TIMESTAMP(timezone=True))


def _open_from(t: datetime | None) -> Range:
    return Range(t, None, bounds="[)") if t else Range(None, None, bounds="[)")


# ── source → facility ───────────────────────────────────────────────────────
def propose_source_facilities(
    session: Session,
    source_id: int,
    *,
    radius_m: float | None = None,
    ell: float | None = None,
    kappa: float = 4.0,
    w0: float = 0.05,
    run_id: int | None = None,
) -> list[dict[str, Any]]:
    """Score facilities near a source; each becomes a proposed link for an analyst (F1).

    Wind comes from the source's most recent detection that carries u and v; with no
    wind the alignment term is dropped (κ = 0) and distance alone ranks candidates.

    The search radius r and length scale ℓ follow the scale of the source's finest
    detection (``attribution_scale``): a source seen only at km scale searches km-scale
    neighbourhoods and spreads its probability over more candidates.
    """
    finest = session.scalar(
        select(func.min(Detection.pixel_size_m)).where(
            Detection.source_id == source_id, Detection.status != "rejected"
        )
    )
    ell_auto, radius_auto = attribution_scale(finest)
    ell = ell if ell is not None else ell_auto
    radius_m = radius_m if radius_m is not None else radius_auto
    row = session.execute(
        select(gf.ST_X(Source.geom), gf.ST_Y(Source.geom)).where(Source.id == source_id)
    ).first()
    if row is None:
        raise LookupError(f"source {source_id} not found")
    lon, lat = row
    cands = session.execute(
        select(
            Facility.id,
            gf.ST_X(gf.ST_Centroid(Facility.geom)),
            gf.ST_Y(gf.ST_Centroid(Facility.geom)),
        )
        .join(Source, Source.id == source_id)
        .where(
            gf.ST_DWithin(cast(Facility.geom, Geography), cast(Source.geom, Geography), radius_m)
        )
    ).all()
    if not cands:
        return []
    marks = session.scalars(
        select(Detection.marks)
        .where(Detection.source_id == source_id, Detection.marks.has_key("wind_u_m_s"))
        .order_by(Detection.observed_at.desc())
        .limit(1)
    ).first()
    fids = [c[0] for c in cands]
    fx = np.array([c[1] for c in cands])  # (K,)
    fy = np.array([c[2] for c in cands])  # (K,)
    d = haversine_m(fx, fy, lon, lat)  # (K,) facility → source origin
    theta = bearing_deg(fx, fy, lon, lat)  # (K,)
    if marks and marks.get("wind_v_m_s") is not None:
        phi = float(wind_to_deg(marks["wind_u_m_s"], marks["wind_v_m_s"]))
        k = kappa
    else:
        phi, k = 0.0, 0.0
    p = candidate_probabilities(d, theta, phi, ell=ell, kappa=k, w0=w0)  # (K,)
    out = []
    for fid, dist, score in zip(fids, d, p, strict=True):
        link = SourceFacility(
            source_id=source_id,
            facility_id=fid,
            score=float(score),
            method="automatic",
            status="proposed",
            run_id=run_id,
        )
        session.add(link)
        session.flush()
        out.append(
            {"id": link.id, "facility_id": fid, "score": float(score), "distance_m": float(dist)}
        )
    return sorted(out, key=lambda r: -r["score"])


def link_source_facility(
    session: Session,
    *,
    source_id: int,
    facility_id: int,
    decided_by: str,
    valid_from: datetime | None = None,
    method: str = "analyst",
    score: float | None = None,
    assertion_id: int | None = None,
) -> SourceFacility:
    """Confirm that a source sits on a facility from ``valid_from`` on.

    An earlier confirmed link of the same source is closed at ``valid_from`` and marked
    superseded; the exclusion constraint refuses any overlap that slips through.
    """
    now = datetime.now(UTC)
    prev = session.scalars(
        select(SourceFacility)
        .where(SourceFacility.source_id == source_id, SourceFacility.status == "confirmed")
        .with_for_update()
    ).all()
    new = SourceFacility(
        source_id=source_id,
        facility_id=facility_id,
        score=score,
        method=method,
        status="confirmed",
        decided_by=decided_by,
        decided_at=now,
        assertion_id=assertion_id,
        valid=_open_from(valid_from),
    )
    for p in prev:
        if valid_from is None or (p.valid.lower is not None and p.valid.lower >= valid_from):
            p.status = "superseded"
        else:
            p.valid = Range(p.valid.lower, valid_from, bounds="[)")
        new.supersedes_id = p.id
    session.flush()
    session.add(new)
    session.flush()
    return new


def decide_proposal(
    session: Session,
    link_id: int,
    *,
    confirm: bool,
    decided_by: str,
    valid_from: datetime | None = None,
) -> SourceFacility:
    link = session.get(SourceFacility, link_id)
    if link is None:
        raise LookupError(f"link {link_id} not found")
    if link.status != "proposed":
        raise ValueError(f"link {link_id} is already {link.status}")
    link.decided_by, link.decided_at = decided_by, datetime.now(UTC)
    if not confirm:
        link.status = "rejected"
        session.flush()
        return link
    link.status = "superseded"  # the proposal is kept; the confirmed link is a new row
    session.flush()
    return link_source_facility(
        session,
        source_id=link.source_id,
        facility_id=link.facility_id,
        decided_by=decided_by,
        valid_from=valid_from,
        method="automatic",
        score=link.score,
    )


def links_for_source(session: Session, source_id: int) -> list[dict[str, Any]]:
    rows = session.execute(
        select(SourceFacility, Facility.name)
        .join(Facility, Facility.id == SourceFacility.facility_id)
        .where(SourceFacility.source_id == source_id)
        .order_by(SourceFacility.created_at)
    ).all()
    return [
        {
            "id": link.id,
            "facility_id": link.facility_id,
            "facility": name,
            "score": link.score,
            "method": link.method,
            "status": link.status,
            "valid_from": iso(link.valid.lower),
            "valid_to": iso(link.valid.upper),
            "decided_by": link.decided_by,
        }
        for link, name in rows
    ]


# ── orgs, assets and roles ──────────────────────────────────────────────────
def add_org(session: Session, *, name: str, org_type: str, country: str | None = None) -> Org:
    org = Org(name=name, org_type=org_type, country=country)
    session.add(org)
    session.flush()
    return org


def add_asset(
    session: Session,
    *,
    name: str,
    asset_type: str,
    jurisdiction: str | None = None,
    reporting_id: str | None = None,
    government_id: int | None = None,
    valid_from: datetime | None = None,
) -> Asset:
    a = Asset(
        name=name,
        asset_type=asset_type,
        jurisdiction=jurisdiction,
        reporting_id=reporting_id,
        government_id=government_id,
        valid=_open_from(valid_from),
    )
    session.add(a)
    session.flush()
    return a


def link_facility_asset(
    session: Session,
    *,
    facility_id: int,
    asset_id: int,
    valid_from: datetime | None = None,
    assertion_id: int | None = None,
) -> FacilityAsset:
    fa = FacilityAsset(
        facility_id=facility_id,
        asset_id=asset_id,
        valid=_open_from(valid_from),
        assertion_id=assertion_id,
    )
    session.add(fa)
    session.flush()
    return fa


def link_facility_government(
    session: Session,
    *,
    facility_id: int,
    org_id: int,
    role: str = "regulator",
    valid_from: datetime | None = None,
) -> FacilityGovernment:
    fg = FacilityGovernment(
        facility_id=facility_id, org_id=org_id, role=role, valid=_open_from(valid_from)
    )
    session.add(fg)
    session.flush()
    return fg


def set_asset_role(
    session: Session,
    *,
    asset_id: int,
    org_id: int,
    role: str,
    valid_from: datetime,
    share: float | None = None,
    assertion_id: int | None = None,
) -> OrgAsset:
    """Give an asset an operator or owner from ``valid_from``; the previous operator's range is closed there."""
    if role == "operator":
        for prev in session.scalars(
            select(OrgAsset)
            .where(
                OrgAsset.asset_id == asset_id,
                OrgAsset.role == "operator",
                OrgAsset.valid.op("@>")(_at(valid_from)),
            )
            .with_for_update()
        ):
            prev.valid = Range(prev.valid.lower, valid_from, bounds="[)")
        session.flush()
    oa = OrgAsset(
        asset_id=asset_id,
        org_id=org_id,
        role=role,
        share=share,
        valid=_open_from(valid_from),
        assertion_id=assertion_id,
    )
    session.add(oa)
    session.flush()
    return oa


def who_for_source(
    session: Session, source_id: int, at: datetime | None = None
) -> dict[str, Any] | None:
    """Source → facility → asset → operator, owners and governments, as of ``at`` (default now)."""
    at = at or datetime.now(UTC)
    t = _at(at)
    row = session.execute(
        select(Facility.id, Facility.name)
        .join(SourceFacility, SourceFacility.facility_id == Facility.id)
        .where(
            SourceFacility.source_id == source_id,
            SourceFacility.status == "confirmed",
            SourceFacility.valid.op("@>")(t),
        )
    ).first()
    if row is None:
        return None
    fid, fname = row
    asset = session.execute(
        select(Asset.id, Asset.name, Asset.asset_type, Asset.reporting_id, Asset.government_id)
        .join(FacilityAsset, FacilityAsset.asset_id == Asset.id)
        .where(FacilityAsset.facility_id == fid, FacilityAsset.valid.op("@>")(t))
    ).first()
    roles: list[dict[str, Any]] = []
    gov_ids: set[int] = set()
    if asset is not None:
        roles = [
            {
                "org_id": o.id,
                "org": o.name,
                "role": r.role,
                "share": r.share,
                "valid_from": iso(r.valid.lower),
                "valid_to": iso(r.valid.upper),
            }
            for r, o in session.execute(
                select(OrgAsset, Org)
                .join(Org, Org.id == OrgAsset.org_id)
                .where(OrgAsset.asset_id == asset.id, OrgAsset.valid.op("@>")(t))
                .order_by(OrgAsset.role)
            ).all()
        ]
        if asset.government_id:
            gov_ids.add(asset.government_id)
    gov_ids |= set(
        session.scalars(
            select(FacilityGovernment.org_id).where(
                FacilityGovernment.facility_id == fid, FacilityGovernment.valid.op("@>")(t)
            )
        ).all()
    )
    govs = (
        [
            {"org_id": o.id, "org": o.name, "org_type": o.org_type}
            for o in session.scalars(select(Org).where(Org.id.in_(gov_ids)))
        ]
        if gov_ids
        else []
    )
    return {
        "at": at.isoformat(),
        "facility": {"id": fid, "name": fname},
        "asset": None
        if asset is None
        else {
            "id": asset.id,
            "name": asset.name,
            "asset_type": asset.asset_type,
            "reporting_id": asset.reporting_id,
        },
        "operator": next((r for r in roles if r["role"] == "operator"), None),
        "owners": [r for r in roles if r["role"] == "owner"],
        "governments": govs,
    }
