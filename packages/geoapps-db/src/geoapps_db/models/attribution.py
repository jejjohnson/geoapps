"""attribution (app 2): who is behind a source, valid over time.

source ─(source_facility)→ facility ─(facility_asset)→ asset ─(org_asset)→ org
                           facility ─(facility_government)→ org (government, regulator)
                                                            org ─(org_relation)→ org

Exclusion constraints, not app code, refuse contradictions (data model §3).
"""

from datetime import datetime

from sqlalchemy import CheckConstraint, Float, ForeignKey, String, Text, text
from sqlalchemy.dialects.postgresql import ExcludeConstraint
from sqlalchemy.orm import Mapped, mapped_column

from geoapps_db.models.base import Base, CreatedMixin, IdMixin, Timestamp, ValidMixin, _in

LINK_STATUSES = ("proposed", "confirmed", "rejected", "superseded")
LINK_METHODS = ("automatic", "analyst", "imported")
ORG_TYPES = ("company", "government", "regulator", "other")
ROLES = ("operator", "owner")


class SourceFacility(IdMixin, CreatedMixin, ValidMixin, Base):
    """A scored candidate link; once confirmed, the source sits on that facility for `valid`."""

    __tablename__ = "source_facility"
    __table_args__ = (
        CheckConstraint(_in("status", LINK_STATUSES), name="status"),
        CheckConstraint(_in("method", LINK_METHODS), name="method"),
        ExcludeConstraint(
            ("source_id", "="),
            ("valid", "&&"),
            where=text("status = 'confirmed'"),
            using="gist",
            name="ex_source_facility_one_confirmed",
        ),
        {"schema": "attribution"},
    )

    source_id: Mapped[int] = mapped_column(ForeignKey("ref.source.id"), index=True)
    facility_id: Mapped[int] = mapped_column(ForeignKey("ref.facility.id"), index=True)
    score: Mapped[float | None] = mapped_column(Float)  # p(j | plume), calibrated later
    method: Mapped[str] = mapped_column(String(16), default="automatic", server_default="automatic")
    status: Mapped[str] = mapped_column(
        String(16), default="proposed", server_default="proposed", index=True
    )
    decided_by: Mapped[str | None] = mapped_column(String(128))
    decided_at: Mapped[datetime | None] = mapped_column(Timestamp)
    supersedes_id: Mapped[int | None] = mapped_column(ForeignKey("attribution.source_facility.id"))
    assertion_id: Mapped[int | None] = mapped_column(ForeignKey("core.assertion.id"))
    run_id: Mapped[int | None] = mapped_column(ForeignKey("core.run.id"))


class Org(IdMixin, CreatedMixin, Base):
    """A company, a government or a regulator."""

    __tablename__ = "org"
    __table_args__ = (
        CheckConstraint(_in("org_type", ORG_TYPES), name="org_type"),
        {"schema": "attribution"},
    )

    name: Mapped[str] = mapped_column(String(256))
    org_type: Mapped[str] = mapped_column(String(16))
    country: Mapped[str | None] = mapped_column(String(128))


class OrgRelation(IdMixin, CreatedMixin, ValidMixin, Base):
    """Parent → child: subsidiary, joint venture."""

    __tablename__ = "org_relation"
    __table_args__ = {"schema": "attribution"}

    parent_id: Mapped[int] = mapped_column(ForeignKey("attribution.org.id"), index=True)
    child_id: Mapped[int] = mapped_column(ForeignKey("attribution.org.id"), index=True)
    relation: Mapped[str] = mapped_column(String(32))


class Asset(IdMixin, CreatedMixin, ValidMixin, Base):
    """A government reporting unit: a lease, licence, concession or permit."""

    __tablename__ = "asset"
    __table_args__ = {"schema": "attribution"}

    name: Mapped[str] = mapped_column(String(256))
    asset_type: Mapped[str] = mapped_column(String(32))
    jurisdiction: Mapped[str | None] = mapped_column(String(128))
    reporting_id: Mapped[str | None] = mapped_column(String(128))  # the regulator's own id
    government_id: Mapped[int | None] = mapped_column(ForeignKey("attribution.org.id"))
    note: Mapped[str | None] = mapped_column(Text)


class FacilityAsset(IdMixin, CreatedMixin, ValidMixin, Base):
    __tablename__ = "facility_asset"
    __table_args__ = (
        ExcludeConstraint(
            ("facility_id", "="), ("valid", "&&"), using="gist", name="ex_facility_asset_one"
        ),
        {"schema": "attribution"},
    )

    facility_id: Mapped[int] = mapped_column(ForeignKey("ref.facility.id"), index=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("attribution.asset.id"), index=True)
    assertion_id: Mapped[int | None] = mapped_column(ForeignKey("core.assertion.id"))


class OrgAsset(IdMixin, CreatedMixin, ValidMixin, Base):
    """An operator or owner of an asset; one operator at a time, owners may share."""

    __tablename__ = "org_asset"
    __table_args__ = (
        CheckConstraint(_in("role", ROLES), name="role"),
        CheckConstraint("share IS NULL OR (share > 0 AND share <= 1)", name="share"),
        ExcludeConstraint(
            ("asset_id", "="),
            ("valid", "&&"),
            where=text("role = 'operator'"),
            using="gist",
            name="ex_org_asset_one_operator",
        ),
        {"schema": "attribution"},
    )

    org_id: Mapped[int] = mapped_column(ForeignKey("attribution.org.id"), index=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("attribution.asset.id"), index=True)
    role: Mapped[str] = mapped_column(String(16))
    share: Mapped[float | None] = mapped_column(Float)
    assertion_id: Mapped[int | None] = mapped_column(ForeignKey("core.assertion.id"))


class FacilityGovernment(IdMixin, CreatedMixin, ValidMixin, Base):
    """A government or regulator linked straight to a facility, with or without an asset."""

    __tablename__ = "facility_government"
    __table_args__ = {"schema": "attribution"}

    facility_id: Mapped[int] = mapped_column(ForeignKey("ref.facility.id"), index=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("attribution.org.id"), index=True)
    role: Mapped[str] = mapped_column(String(32), default="regulator", server_default="regulator")
    assertion_id: Mapped[int | None] = mapped_column(ForeignKey("core.assertion.id"))
