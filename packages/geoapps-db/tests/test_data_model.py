"""The data model's rules (docs/design/03-data-model.md), each against real PostGIS."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from geoapps_db import repo
from geoapps_db.models import Event, Feedback, LabelSetMember, SourceFacility

T0 = datetime(2026, 9, 1, tzinfo=UTC)


def day(n: float) -> datetime:
    return T0 + timedelta(days=n)


def pt(lon=-103.48, lat=31.87):
    return {"type": "Point", "coordinates": [lon, lat]}


def plume(session, source_id, t, q=1000.0, s=300.0, **kw):
    return repo.add_detection(
        session,
        kind="ch4_plume",
        geometry=pt(),
        marks={"q_kg_h": q, "q_sigma_kg_h": s, "p": 0.9, **kw},
        observed_at=t,
        source_id=source_id,
        now=day(400),
    )


def test_point_detection_allowed_line_refused(session):
    src = repo.add_source(session, "S-1", -103.48, 31.87)
    det = plume(session, src.id, day(0))
    assert det.status == "predicted"
    with pytest.raises(ValueError, match="LineString"):
        repo.add_detection(
            session,
            kind="ch4_plume",
            geometry={"type": "LineString", "coordinates": [[0, 0], [1, 1]]},
            marks={"p": 0.5},
            observed_at=day(0),
        )


def test_dataset_same_bytes_registered_once(session):
    a, created = repo.register_dataset(session, name="d", sha256="ab" * 32, licence="CC BY 4.0")
    b, again = repo.register_dataset(session, name="d", sha256="ab" * 32)
    assert created and not again and a.id == b.id
    c, new = repo.register_dataset(session, name="d", sha256="cd" * 32)
    assert new and c.id != a.id


def test_source_for_record_uses_xref(session):
    sid, created = repo.source_for_record(
        session, provider="p", record_id="USA123", lon=-103.5, lat=31.9, sector="Oil and Gas"
    )
    again, created2 = repo.source_for_record(
        session, provider="p", record_id="USA123", lon=0, lat=0
    )
    assert created and not created2 and sid == again
    assert repo.xrefs_for(session, "source", sid) == [
        {"provider": "p", "record_id": "USA123", "match_score": None}
    ]


def test_events_chain_by_gap_and_close(session):
    """Validated detections on days 0, 5, 9 and 60 make two events; rejected ones never count."""
    src = repo.add_source(session, "S-1", -103.48, 31.87)
    dets = [
        plume(session, src.id, day(d), q=q, s=s)
        for d, q, s in [
            (0, 980, 310),
            (5, 1400, 600),
            (9, 1100, 400),
            (60, 900, 300),
            (62, 5000, 100),
        ]
    ]
    for d in dets[:4]:
        repo.record_verdict(session, d.id, verdict="confirm", analyst="eman", rechain=False)
    repo.record_verdict(session, dets[4].id, verdict="reject", analyst="eman", rechain=False)
    repo.rechain_events(session, src.id, now=day(70))
    events = repo.events_for_source(session, src.id)
    assert [e["n_detections"] for e in events] == [3, 1]
    first, second = events
    assert (
        first["status"] == "closed" and second["status"] == "open"
    )  # day 60 is < 30 days before day 70
    assert (
        first["t_a"] is None and first["t_d"] is None
    )  # no observations: bounds unknown, not zero
    assert first["q_mean_kg_h"] == pytest.approx(1080, abs=15)  # inverse-variance mean
    # the source's history follows its non-rejected detections
    repo.refresh_source_seen(session, [src.id])
    session.refresh(src)
    assert src.first_seen == day(0) and src.last_seen == day(60)  # day 62 was rejected


def test_clear_look_bounds_and_splits_events(session):
    src = repo.add_source(session, "S-1", -103.48, 31.87)
    loc = repo.add_location(
        session,
        name="L-231",
        by="eman",
        source_id=src.id,
        area={
            "type": "Polygon",
            "coordinates": [
                [
                    [-103.49, 31.86],
                    [-103.47, 31.86],
                    [-103.47, 31.88],
                    [-103.49, 31.88],
                    [-103.49, 31.86],
                ]
            ],
        },
    )
    for d in (0, 5, 9):
        det = plume(session, src.id, day(d))
        repo.record_verdict(session, det.id, verdict="confirm", analyst="eman", rechain=False)
        repo.add_observation(
            session,
            location_id=loc.id,
            observed_at=day(d),
            valid_fraction=0.95,
            detection_id=det.id,
            detection_limit=200,
        )
    for d in (-2, 7, 12):  # clear looks: before, between, after
        repo.add_observation(
            session,
            location_id=loc.id,
            observed_at=day(d),
            valid_fraction=0.9,
            detection_limit=200,
        )
    repo.add_observation(
        session, location_id=loc.id, observed_at=day(3), valid_fraction=0.1
    )  # cloudy: ignored
    repo.rechain_events(session, src.id, now=day(13))
    a, b = repo.events_for_source(session, src.id)
    assert (a["t_a"], a["t_b"], a["t_c"], a["t_d"]) == (
        day(-2).isoformat(),
        day(0).isoformat(),
        day(5).isoformat(),
        day(7).isoformat(),
    )
    assert (
        b["t_b"] == day(9).isoformat()
        and b["t_d"] == day(12).isoformat()
        and b["status"] == "closed"
    )

    p = repo.persistence(session, loc.id)
    assert (p["n_valid"], p["n_det"]) == (6, 3)  # the cloudy look does not count
    assert p["mean"] == pytest.approx(0.5)
    # looks that could not see a 100 kg/h plume say nothing about one
    assert repo.persistence(session, loc.id, threshold=100)["n_valid"] == 0


def test_location_lifecycle_is_history(session):
    loc = repo.add_location(
        session,
        name="L",
        by="eman",
        area={"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]},
    )
    repo.set_location_status(session, loc.id, "monitored", by="eman", reason="first plume")
    repo.set_location_status(session, loc.id, "paused", by="eman", reason="repair reported")
    from geoapps_db.models import LocationStatus

    rows = session.scalars(
        select(LocationStatus.status)
        .where(LocationStatus.location_id == loc.id)
        .order_by(LocationStatus.id)
    ).all()
    assert rows == ["candidate", "monitored", "paused"]


def test_one_confirmed_facility_per_source_at_a_time(session):
    src = repo.add_source(session, "S-1", -103.48, 31.87)
    f1 = repo.add_facility(session, name="Well Pad 17-B", lon=-103.481, lat=31.871)
    f2 = repo.add_facility(session, name="Well Pad 17-C", lon=-103.49, lat=31.87)
    repo.link_source_facility(
        session, source_id=src.id, facility_id=f1.id, decided_by="eman", valid_from=day(0)
    )
    # re-attribution from day 30 closes the first link there instead of overlapping it
    repo.link_source_facility(
        session, source_id=src.id, facility_id=f2.id, decided_by="eman", valid_from=day(30)
    )
    links = repo.links_for_source(session, src.id)
    assert [(lk["facility"], lk["valid_to"]) for lk in links] == [
        ("Well Pad 17-B", day(30).isoformat()),
        ("Well Pad 17-C", None),
    ]
    # the database itself refuses an overlap the app did not close
    session.add(
        SourceFacility(source_id=src.id, facility_id=f1.id, status="confirmed", method="analyst")
    )
    with pytest.raises(IntegrityError):
        session.flush()


def test_who_operated_on_a_date(session):
    """Framework page 4: Lease 45-1123 sold on 1 August; who operated on 14 July and 14 September?"""
    src = repo.add_source(session, "S-0931", -103.48, 31.87)
    fac = repo.add_facility(session, name="Well Pad 17-B", lon=-103.481, lat=31.871)
    texas = repo.add_org(
        session, name="Railroad Commission of Texas", org_type="regulator", country="US"
    )
    pee = repo.add_org(session, name="Permian Example Energy", org_type="company")
    mro = repo.add_org(session, name="Mesa Ridge Operating", org_type="company")
    lease = repo.add_asset(
        session,
        name="Lease 45-1123",
        asset_type="lease",
        jurisdiction="Texas, US",
        reporting_id="45-1123",
        government_id=texas.id,
    )
    repo.link_facility_asset(
        session, facility_id=fac.id, asset_id=lease.id, valid_from=datetime(2019, 3, 1, tzinfo=UTC)
    )
    repo.link_source_facility(
        session,
        source_id=src.id,
        facility_id=fac.id,
        decided_by="eman",
        valid_from=datetime(2026, 7, 1, tzinfo=UTC),
    )
    repo.set_asset_role(
        session,
        asset_id=lease.id,
        org_id=pee.id,
        role="operator",
        valid_from=datetime(2019, 3, 1, tzinfo=UTC),
    )
    repo.set_asset_role(
        session,
        asset_id=lease.id,
        org_id=mro.id,
        role="operator",
        valid_from=datetime(2026, 8, 1, tzinfo=UTC),
    )
    repo.set_asset_role(
        session,
        asset_id=lease.id,
        org_id=mro.id,
        role="owner",
        share=1.0,
        valid_from=datetime(2026, 8, 1, tzinfo=UTC),
    )

    july = repo.who_for_source(session, src.id, at=datetime(2026, 7, 14, tzinfo=UTC))
    sept = repo.who_for_source(session, src.id, at=datetime(2026, 9, 14, tzinfo=UTC))
    assert july["operator"]["org"] == "Permian Example Energy" and july["owners"] == []
    assert sept["operator"]["org"] == "Mesa Ridge Operating"
    assert [o["org"] for o in sept["owners"]] == ["Mesa Ridge Operating"]
    assert sept["governments"] == [
        {"org_id": texas.id, "org": "Railroad Commission of Texas", "org_type": "regulator"}
    ]
    # before the source was attributed there is no answer, not a guess
    assert repo.who_for_source(session, src.id, at=datetime(2026, 6, 1, tzinfo=UTC)) is None


def test_two_operators_refused_by_database(session):
    a = repo.add_org(session, name="A", org_type="company")
    b = repo.add_org(session, name="B", org_type="company")
    lease = repo.add_asset(session, name="L", asset_type="lease")
    from sqlalchemy.dialects.postgresql import Range

    from geoapps_db.models import OrgAsset

    session.add(
        OrgAsset(
            org_id=a.id, asset_id=lease.id, role="operator", valid=Range(day(0), None, bounds="[)")
        )
    )
    session.add(
        OrgAsset(
            org_id=b.id, asset_id=lease.id, role="operator", valid=Range(day(10), None, bounds="[)")
        )
    )
    with pytest.raises(IntegrityError):
        session.flush()


def test_propose_scores_downwind_facility_low(session):
    """F1 through the database: with wind blowing east, the facility upwind (west) wins."""
    src = repo.add_source(session, "S-1", -103.48, 31.87)
    upwind = repo.add_facility(session, name="west", lon=-103.484, lat=31.87)
    downwind = repo.add_facility(session, name="east", lon=-103.476, lat=31.87)
    repo.add_facility(session, name="far", lon=-103.0, lat=31.87)  # outside the radius
    plume(session, src.id, day(0), wind_u_m_s=4.0, wind_v_m_s=0.0)
    props = repo.propose_source_facilities(session, src.id, radius_m=2000)
    assert [p["facility_id"] for p in props] == [upwind.id, downwind.id]
    assert props[1]["score"] < 1e-6 < props[0]["score"]
    confirmed = repo.decide_proposal(
        session, props[0]["id"], confirm=True, decided_by="eman", valid_from=day(0)
    )
    assert confirmed.status == "confirmed" and confirmed.method == "automatic"


def test_dismissal_becomes_feedback(session):
    src = repo.add_source(session, "S-1", -103.48, 31.87)
    repo.create_watch(
        session,
        owner="eman",
        name="all",
        geometry={
            "type": "Polygon",
            "coordinates": [[[-104, 31], [-103, 31], [-103, 32], [-104, 32], [-104, 31]]],
        },
    )
    det = plume(session, src.id, day(0))
    repo.record_verdict(session, det.id, verdict="confirm", analyst="eman")
    alert = repo.list_alerts(session, owner="eman")[0]
    repo.set_alert_state(session, alert["id"], "dismissed", "wrong source", by="eman")
    fb = session.scalars(select(Feedback)).all()
    assert [(f.about, f.about_id, f.kind) for f in fb] == [("alert", alert["id"], "wrong source")]


def test_label_set_freezes_membership(session):
    src = repo.add_source(session, "S-1", -103.48, 31.87)
    for d in range(3):
        det = plume(session, src.id, day(d))
        repo.record_verdict(
            session,
            det.id,
            verdict="confirm",
            analyst="provider:unep-mars" if d else "eman",
            rechain=False,
        )
    ls = repo.freeze_label_set(session, "mars-v1", analyst_prefix="provider:")
    assert ls.n_labels == 2
    later = plume(session, src.id, day(5))
    repo.record_verdict(
        session, later.id, verdict="confirm", analyst="provider:unep-mars", rechain=False
    )
    n = session.scalar(
        select(func.count()).select_from(LabelSetMember).where(LabelSetMember.label_set_id == ls.id)
    )
    assert n == 2  # labels made after freezing never join it


def test_verdict_rechains_source_events(session):
    src = repo.add_source(session, "S-1", -103.48, 31.87)
    det = plume(session, src.id, day(0))
    assert session.scalar(select(func.count(Event.id))) == 0
    repo.record_verdict(session, det.id, verdict="confirm", analyst="eman")
    session.refresh(det)
    assert det.event_id is not None


def test_a2_no_overlapping_operators(session):
    """Gate A2: 10,000 random operator links leave 0 overlaps for one (asset, role)."""
    import numpy as np
    from sqlalchemy import text
    from sqlalchemy.dialects.postgresql import Range

    from geoapps_db.models import OrgAsset

    rng = np.random.default_rng(0)
    orgs = [repo.add_org(session, name=f"O{i}", org_type="company").id for i in range(5)]
    assets = [repo.add_asset(session, name=f"A{i}", asset_type="lease").id for i in range(20)]
    refused = 0
    for _ in range(10_000):
        a, b = sorted(rng.integers(0, 3650, size=2))
        if a == b:
            continue
        try:
            with session.begin_nested():
                session.add(
                    OrgAsset(
                        org_id=int(rng.choice(orgs)),
                        asset_id=int(rng.choice(assets)),
                        role="operator",
                        valid=Range(day(int(a)), day(int(b)), bounds="[)"),
                    )
                )
                session.flush()
        except IntegrityError:
            refused += 1
    overlaps = session.scalar(
        text(
            "SELECT count(*) FROM attribution.org_asset x JOIN attribution.org_asset y "
            "ON x.asset_id = y.asset_id AND x.role = y.role AND x.id < y.id AND x.valid && y.valid "
            "WHERE x.role = 'operator'"
        )
    )
    assert overlaps == 0 and refused > 0


def test_a3_as_of_oracle(session):
    """Gate A3: with 3 operator changes, the operator is right on 1,000 of 1,000 random dates."""
    import numpy as np

    rng = np.random.default_rng(1)
    src = repo.add_source(session, "S", -103.48, 31.87)
    fac = repo.add_facility(session, name="F", lon=-103.48, lat=31.87)
    lease = repo.add_asset(session, name="L", asset_type="lease")
    repo.link_facility_asset(session, facility_id=fac.id, asset_id=lease.id, valid_from=day(0))
    repo.link_source_facility(
        session, source_id=src.id, facility_id=fac.id, decided_by="t", valid_from=day(0)
    )
    changes = [0, 400, 950, 1700]  # the first operator, then 3 changes
    names = ["first", "second", "third", "fourth"]
    for d, name in zip(changes, names, strict=True):
        org = repo.add_org(session, name=name, org_type="company")
        repo.set_asset_role(
            session, asset_id=lease.id, org_id=org.id, role="operator", valid_from=day(d)
        )
    wrong = 0
    for d in rng.uniform(0, 2500, size=1000):
        expect = names[int(np.searchsorted(changes, d, side="right")) - 1]
        got = repo.who_for_source(session, src.id, at=day(float(d)))["operator"]["org"]
        wrong += got != expect
    assert wrong == 0


def test_persistence_threshold_with_mixed_sensors(session):
    """A coarse sensor's clear looks say nothing about plumes below its limit."""
    src = repo.add_source(session, "S-1", -103.48, 31.87)
    loc = repo.add_location(
        session,
        name="L",
        by="t",
        source_id=src.id,
        area={
            "type": "Polygon",
            "coordinates": [
                [[-103.49, 31.86], [-103.47, 31.86], [-103.47, 31.88], [-103.49, 31.86]]
            ],
        },
    )
    # fine sensor (limit 100 kg/h): 2 detections in 4 looks; coarse sensor (limit 5 t/h): 6 clear looks
    for d in range(4):
        det = plume(session, src.id, day(d), q=800) if d < 2 else None
        repo.add_observation(
            session,
            location_id=loc.id,
            observed_at=day(d),
            valid_fraction=1.0,
            detection_limit=100,
            pixel_size_m=30,
            detection_id=det.id if det else None,
        )
    for d in range(4, 10):
        repo.add_observation(
            session,
            location_id=loc.id,
            observed_at=day(d),
            valid_fraction=1.0,
            detection_limit=5000,
            pixel_size_m=5500,
        )
    mixed = repo.persistence(session, loc.id)
    at_800 = repo.persistence(session, loc.id, threshold=800)
    assert (mixed["n_valid"], mixed["n_det"]) == (
        10,
        2,
    )  # diluted by looks that could not see an 800 kg/h plume
    assert (at_800["n_valid"], at_800["n_det"]) == (4, 2) and at_800["mean"] == pytest.approx(0.5)


def test_coarse_detection_searches_wider(session):
    """A source seen only at km scale proposes facilities km away; a fine one does not."""
    fine = repo.add_source(session, "fine", -103.48, 31.87)
    coarse = repo.add_source(session, "coarse", -103.30, 31.87)
    near_fine = repo.add_facility(session, name="near fine", lon=-103.481, lat=31.871)
    repo.add_facility(session, name="5 km from fine", lon=-103.427, lat=31.87)
    near_coarse = repo.add_facility(session, name="8 km from coarse", lon=-103.215, lat=31.87)
    repo.add_detection(
        session,
        kind="ch4_plume",
        geometry=pt(-103.48, 31.87),
        marks={"p": 0.9},
        observed_at=day(0),
        source_id=fine.id,
        pixel_size_m=30,
    )
    repo.add_detection(
        session,
        kind="ch4_plume",
        geometry=pt(-103.30, 31.87),
        marks={"p": 0.9},
        observed_at=day(0),
        source_id=coarse.id,
        pixel_size_m=5500,
    )
    assert [p["facility_id"] for p in repo.propose_source_facilities(session, fine.id)] == [
        near_fine.id
    ]
    coarse_props = repo.propose_source_facilities(session, coarse.id)
    assert near_coarse.id in [p["facility_id"] for p in coarse_props]
    assert max(p["score"] for p in coarse_props) < 0.95  # spread, not certain


def test_detections_relate_across_scales_without_merging(session):
    src = repo.add_source(session, "S-1", -103.48, 31.87)
    blob = plume(session, src.id, day(0), q=9000)
    fine_a = plume(session, src.id, day(0), q=5000)
    fine_b = plume(session, src.id, day(0), q=3500)
    for f in (fine_a, fine_b):
        repo.relate_detections(
            session, blob.id, f.id, relation="contains", method="overlap", score=0.9
        )
    again = repo.relate_detections(
        session, blob.id, fine_a.id, relation="contains", method="overlap"
    )
    rels = repo.relations_for(session, blob.id)
    assert sorted(r["other_id"] for r in rels) == sorted([fine_a.id, fine_b.id])
    assert {r["role"] for r in rels} == {"a"} and again.score == 0.9  # idempotent
    assert repo.relations_for(session, fine_a.id)[0]["role"] == "b"
    with pytest.raises(ValueError):
        repo.relate_detections(session, blob.id, fine_a.id, relation="merged", method="x")
    with pytest.raises(IntegrityError):
        repo.relate_detections(session, blob.id, blob.id, relation="duplicate", method="x")
