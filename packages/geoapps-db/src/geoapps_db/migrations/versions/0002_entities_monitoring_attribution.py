"""Entities, monitoring, attribution and provenance (docs/design/03-data-model.md).

Adds the attribution and monitor schemas, datasets and assertions in core,
sensors, facilities and external ids in ref, label sets in review and feedback
in notify. Detections gain sensor, source, event and dataset links, and their
geometry widens from POLYGON to any geometry so a point-only plume can be stored.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-08 02:49:04.326476
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from geoalchemy2 import Geometry
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS attribution")
    op.execute("CREATE SCHEMA IF NOT EXISTS monitor")
    op.create_table(
        "org",
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("org_type", sa.String(length=16), nullable=False),
        sa.Column("country", sa.String(length=128), nullable=True),
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "org_type IN ('company', 'government', 'regulator', 'other')",
            name=op.f("ck_org_org_type"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_org")),
        schema="attribution",
    )
    op.create_table(
        "feedback",
        sa.Column("author", sa.String(length=128), nullable=False),
        sa.Column("about", sa.String(length=16), nullable=False),
        sa.Column("about_id", sa.BigInteger(), nullable=False),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("action", sa.String(length=64), nullable=True),
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "about IN ('alert', 'detection', 'attribution', 'facility', 'source')",
            name=op.f("ck_feedback_about"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_feedback")),
        schema="notify",
    )
    op.create_index(
        op.f("ix_feedback_author"), "feedback", ["author"], unique=False, schema="notify"
    )
    op.create_geospatial_table(
        "facility",
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("facility_type", sa.String(length=64), nullable=True),
        sa.Column("sector", sa.String(length=128), nullable=True),
        sa.Column("country", sa.String(length=128), nullable=True),
        sa.Column(
            "geom",
            Geometry(
                srid=4326,
                dimension=2,
                spatial_index=False,
                from_text="ST_GeomFromEWKT",
                name="geometry",
                nullable=False,
            ),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=16), server_default="active", nullable=False),
        sa.Column(
            "attrs", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False
        ),
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("valid", postgresql.TSTZRANGE(), server_default="(,)", nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_facility")),
        schema="ref",
    )
    op.create_geospatial_index(
        "idx_facility_geom",
        "facility",
        ["geom"],
        unique=False,
        schema="ref",
        postgresql_using="gist",
        postgresql_ops={},
    )
    op.create_table(
        "sensor",
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("platform", sa.String(length=128), nullable=True),
        sa.Column("agency", sa.String(length=128), nullable=True),
        sa.Column("sensor_type", sa.String(length=64), nullable=True),
        sa.Column("gsd_m", sa.Float(), nullable=True),
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sensor")),
        sa.UniqueConstraint("name", name=op.f("uq_sensor_name")),
        schema="ref",
    )
    op.create_table(
        "xref",
        sa.Column("entity", sa.String(length=16), nullable=False),
        sa.Column("entity_id", sa.BigInteger(), nullable=False),
        sa.Column("provider", sa.String(length=128), nullable=False),
        sa.Column("record_id", sa.String(length=256), nullable=False),
        sa.Column("match_score", sa.Float(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "entity IN ('source', 'facility', 'asset', 'org', 'detection', 'sensor', 'location')",
            name=op.f("ck_xref_entity"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_xref")),
        sa.UniqueConstraint(
            "provider", "entity", "record_id", name=op.f("uq_xref_provider_entity_record_id")
        ),
        schema="ref",
    )
    op.create_index(
        op.f("ix_xref_entity_entity_id"),
        "xref",
        ["entity", "entity_id"],
        unique=False,
        schema="ref",
    )
    op.create_table(
        "label_set",
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("frozen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "filter", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False
        ),
        sa.Column("n_labels", sa.Integer(), server_default="0", nullable=False),
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_label_set")),
        sa.UniqueConstraint("name", name=op.f("uq_label_set_name")),
        schema="review",
    )
    op.create_table(
        "asset",
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("asset_type", sa.String(length=32), nullable=False),
        sa.Column("jurisdiction", sa.String(length=128), nullable=True),
        sa.Column("reporting_id", sa.String(length=128), nullable=True),
        sa.Column("government_id", sa.BigInteger(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("valid", postgresql.TSTZRANGE(), server_default="(,)", nullable=False),
        sa.ForeignKeyConstraint(
            ["government_id"], ["attribution.org.id"], name=op.f("fk_asset_government_id_org")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_asset")),
        schema="attribution",
    )
    op.create_table(
        "org_relation",
        sa.Column("parent_id", sa.BigInteger(), nullable=False),
        sa.Column("child_id", sa.BigInteger(), nullable=False),
        sa.Column("relation", sa.String(length=32), nullable=False),
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("valid", postgresql.TSTZRANGE(), server_default="(,)", nullable=False),
        sa.ForeignKeyConstraint(
            ["child_id"], ["attribution.org.id"], name=op.f("fk_org_relation_child_id_org")
        ),
        sa.ForeignKeyConstraint(
            ["parent_id"], ["attribution.org.id"], name=op.f("fk_org_relation_parent_id_org")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_org_relation")),
        schema="attribution",
    )
    op.create_index(
        op.f("ix_org_relation_child_id"),
        "org_relation",
        ["child_id"],
        unique=False,
        schema="attribution",
    )
    op.create_index(
        op.f("ix_org_relation_parent_id"),
        "org_relation",
        ["parent_id"],
        unique=False,
        schema="attribution",
    )
    op.create_table(
        "dataset",
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("licence", sa.String(length=128), server_default="unspecified", nullable=False),
        sa.Column("attribution", sa.Text(), nullable=True),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("n_records", sa.Integer(), nullable=True),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("run_id", sa.BigInteger(), nullable=True),
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["run_id"], ["core.run.id"], name=op.f("fk_dataset_run_id_run")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_dataset")),
        sa.UniqueConstraint("name", "sha256", name=op.f("uq_dataset_name_sha256")),
        schema="core",
    )
    op.create_index(op.f("ix_dataset_name"), "dataset", ["name"], unique=False, schema="core")
    op.create_geospatial_table(
        "location",
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column(
            "area",
            Geometry(
                geometry_type="POLYGON",
                srid=4326,
                dimension=2,
                spatial_index=False,
                from_text="ST_GeomFromEWKT",
                name="geometry",
                nullable=False,
            ),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=16), server_default="candidate", nullable=False),
        sa.Column("source_id", sa.BigInteger(), nullable=True),
        sa.Column("facility_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "sensors", postgresql.ARRAY(sa.String(length=128)), server_default="{}", nullable=False
        ),
        sa.Column("revisit_days", sa.Float(), nullable=True),
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('candidate', 'monitored', 'paused', 'retired')",
            name=op.f("ck_location_status"),
        ),
        sa.ForeignKeyConstraint(
            ["facility_id"], ["ref.facility.id"], name=op.f("fk_location_facility_id_facility")
        ),
        sa.ForeignKeyConstraint(
            ["source_id"], ["ref.source.id"], name=op.f("fk_location_source_id_source")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_location")),
        schema="monitor",
    )
    op.create_geospatial_index(
        "idx_location_area",
        "location",
        ["area"],
        unique=False,
        schema="monitor",
        postgresql_using="gist",
        postgresql_ops={},
    )
    op.create_index(
        op.f("ix_location_facility_id"), "location", ["facility_id"], unique=False, schema="monitor"
    )
    op.create_index(
        op.f("ix_location_source_id"), "location", ["source_id"], unique=False, schema="monitor"
    )
    op.create_table(
        "assertion",
        sa.Column("provider", sa.String(length=128), nullable=False),
        sa.Column("dataset_id", sa.BigInteger(), nullable=True),
        sa.Column("record_id", sa.String(length=256), nullable=True),
        sa.Column("claim", sa.String(length=64), nullable=False),
        sa.Column("accepted", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("asserted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "payload", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False
        ),
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["dataset_id"], ["core.dataset.id"], name=op.f("fk_assertion_dataset_id_dataset")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_assertion")),
        schema="core",
    )
    op.create_index(
        op.f("ix_assertion_dataset_id"), "assertion", ["dataset_id"], unique=False, schema="core"
    )
    op.create_index(
        op.f("ix_assertion_provider"), "assertion", ["provider"], unique=False, schema="core"
    )
    op.create_table(
        "event",
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("source_id", sa.BigInteger(), nullable=True),
        sa.Column("location_id", sa.BigInteger(), nullable=True),
        sa.Column("t_a", sa.DateTime(timezone=True), nullable=True),
        sa.Column("t_b", sa.DateTime(timezone=True), nullable=False),
        sa.Column("t_c", sa.DateTime(timezone=True), nullable=False),
        sa.Column("t_d", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=8), server_default="open", nullable=False),
        sa.Column("n_detections", sa.Integer(), server_default="0", nullable=False),
        sa.Column("q_mean_kg_h", sa.Float(), nullable=True),
        sa.Column("q_sigma_kg_h", sa.Float(), nullable=True),
        sa.Column("run_id", sa.BigInteger(), nullable=True),
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("status IN ('open', 'closed')", name=op.f("ck_event_status")),
        sa.CheckConstraint("t_b <= t_c", name=op.f("ck_event_order")),
        sa.ForeignKeyConstraint(
            ["location_id"], ["monitor.location.id"], name=op.f("fk_event_location_id_location")
        ),
        sa.ForeignKeyConstraint(["run_id"], ["core.run.id"], name=op.f("fk_event_run_id_run")),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["ref.source.id"],
            name=op.f("fk_event_source_id_source"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_event")),
        schema="monitor",
    )
    op.create_index(op.f("ix_event_kind"), "event", ["kind"], unique=False, schema="monitor")
    op.create_index(
        op.f("ix_event_source_id"), "event", ["source_id"], unique=False, schema="monitor"
    )
    op.create_table(
        "location_status",
        sa.Column("location_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("by", sa.String(length=128), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('candidate', 'monitored', 'paused', 'retired')",
            name=op.f("ck_location_status_status"),
        ),
        sa.ForeignKeyConstraint(
            ["location_id"],
            ["monitor.location.id"],
            name=op.f("fk_location_status_location_id_location"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_location_status")),
        schema="monitor",
    )
    op.create_index(
        op.f("ix_location_status_location_id"),
        "location_status",
        ["location_id"],
        unique=False,
        schema="monitor",
    )
    op.create_table(
        "facility_asset",
        sa.Column("facility_id", sa.BigInteger(), nullable=False),
        sa.Column("asset_id", sa.BigInteger(), nullable=False),
        sa.Column("assertion_id", sa.BigInteger(), nullable=True),
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("valid", postgresql.TSTZRANGE(), server_default="(,)", nullable=False),
        postgresql.ExcludeConstraint(
            (sa.column("facility_id"), "="),
            (sa.column("valid"), "&&"),
            using="gist",
            name="ex_facility_asset_one",
        ),
        sa.ForeignKeyConstraint(
            ["assertion_id"],
            ["core.assertion.id"],
            name=op.f("fk_facility_asset_assertion_id_assertion"),
        ),
        sa.ForeignKeyConstraint(
            ["asset_id"], ["attribution.asset.id"], name=op.f("fk_facility_asset_asset_id_asset")
        ),
        sa.ForeignKeyConstraint(
            ["facility_id"],
            ["ref.facility.id"],
            name=op.f("fk_facility_asset_facility_id_facility"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_facility_asset")),
        schema="attribution",
    )
    op.create_index(
        op.f("ix_facility_asset_asset_id"),
        "facility_asset",
        ["asset_id"],
        unique=False,
        schema="attribution",
    )
    op.create_index(
        op.f("ix_facility_asset_facility_id"),
        "facility_asset",
        ["facility_id"],
        unique=False,
        schema="attribution",
    )
    op.create_table(
        "facility_government",
        sa.Column("facility_id", sa.BigInteger(), nullable=False),
        sa.Column("org_id", sa.BigInteger(), nullable=False),
        sa.Column("role", sa.String(length=32), server_default="regulator", nullable=False),
        sa.Column("assertion_id", sa.BigInteger(), nullable=True),
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("valid", postgresql.TSTZRANGE(), server_default="(,)", nullable=False),
        sa.ForeignKeyConstraint(
            ["assertion_id"],
            ["core.assertion.id"],
            name=op.f("fk_facility_government_assertion_id_assertion"),
        ),
        sa.ForeignKeyConstraint(
            ["facility_id"],
            ["ref.facility.id"],
            name=op.f("fk_facility_government_facility_id_facility"),
        ),
        sa.ForeignKeyConstraint(
            ["org_id"], ["attribution.org.id"], name=op.f("fk_facility_government_org_id_org")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_facility_government")),
        schema="attribution",
    )
    op.create_index(
        op.f("ix_facility_government_facility_id"),
        "facility_government",
        ["facility_id"],
        unique=False,
        schema="attribution",
    )
    op.create_index(
        op.f("ix_facility_government_org_id"),
        "facility_government",
        ["org_id"],
        unique=False,
        schema="attribution",
    )
    op.create_table(
        "org_asset",
        sa.Column("org_id", sa.BigInteger(), nullable=False),
        sa.Column("asset_id", sa.BigInteger(), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("share", sa.Float(), nullable=True),
        sa.Column("assertion_id", sa.BigInteger(), nullable=True),
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("valid", postgresql.TSTZRANGE(), server_default="(,)", nullable=False),
        postgresql.ExcludeConstraint(
            (sa.column("asset_id"), "="),
            (sa.column("valid"), "&&"),
            where=sa.text("role = 'operator'"),
            using="gist",
            name="ex_org_asset_one_operator",
        ),
        sa.CheckConstraint("role IN ('operator', 'owner')", name=op.f("ck_org_asset_role")),
        sa.CheckConstraint(
            "share IS NULL OR (share > 0 AND share <= 1)", name=op.f("ck_org_asset_share")
        ),
        sa.ForeignKeyConstraint(
            ["assertion_id"],
            ["core.assertion.id"],
            name=op.f("fk_org_asset_assertion_id_assertion"),
        ),
        sa.ForeignKeyConstraint(
            ["asset_id"], ["attribution.asset.id"], name=op.f("fk_org_asset_asset_id_asset")
        ),
        sa.ForeignKeyConstraint(
            ["org_id"], ["attribution.org.id"], name=op.f("fk_org_asset_org_id_org")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_org_asset")),
        schema="attribution",
    )
    op.create_index(
        op.f("ix_org_asset_asset_id"), "org_asset", ["asset_id"], unique=False, schema="attribution"
    )
    op.create_index(
        op.f("ix_org_asset_org_id"), "org_asset", ["org_id"], unique=False, schema="attribution"
    )
    op.create_table(
        "source_facility",
        sa.Column("source_id", sa.BigInteger(), nullable=False),
        sa.Column("facility_id", sa.BigInteger(), nullable=False),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("method", sa.String(length=16), server_default="automatic", nullable=False),
        sa.Column("status", sa.String(length=16), server_default="proposed", nullable=False),
        sa.Column("decided_by", sa.String(length=128), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("supersedes_id", sa.BigInteger(), nullable=True),
        sa.Column("assertion_id", sa.BigInteger(), nullable=True),
        sa.Column("run_id", sa.BigInteger(), nullable=True),
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("valid", postgresql.TSTZRANGE(), server_default="(,)", nullable=False),
        postgresql.ExcludeConstraint(
            (sa.column("source_id"), "="),
            (sa.column("valid"), "&&"),
            where=sa.text("status = 'confirmed'"),
            using="gist",
            name="ex_source_facility_one_confirmed",
        ),
        sa.CheckConstraint(
            "method IN ('automatic', 'analyst', 'imported')", name=op.f("ck_source_facility_method")
        ),
        sa.CheckConstraint(
            "status IN ('proposed', 'confirmed', 'rejected', 'superseded')",
            name=op.f("ck_source_facility_status"),
        ),
        sa.ForeignKeyConstraint(
            ["assertion_id"],
            ["core.assertion.id"],
            name=op.f("fk_source_facility_assertion_id_assertion"),
        ),
        sa.ForeignKeyConstraint(
            ["facility_id"],
            ["ref.facility.id"],
            name=op.f("fk_source_facility_facility_id_facility"),
        ),
        sa.ForeignKeyConstraint(
            ["run_id"], ["core.run.id"], name=op.f("fk_source_facility_run_id_run")
        ),
        sa.ForeignKeyConstraint(
            ["source_id"], ["ref.source.id"], name=op.f("fk_source_facility_source_id_source")
        ),
        sa.ForeignKeyConstraint(
            ["supersedes_id"],
            ["attribution.source_facility.id"],
            name=op.f("fk_source_facility_supersedes_id_source_facility"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_source_facility")),
        schema="attribution",
    )
    op.create_index(
        op.f("ix_source_facility_facility_id"),
        "source_facility",
        ["facility_id"],
        unique=False,
        schema="attribution",
    )
    op.create_index(
        op.f("ix_source_facility_source_id"),
        "source_facility",
        ["source_id"],
        unique=False,
        schema="attribution",
    )
    op.create_index(
        op.f("ix_source_facility_status"),
        "source_facility",
        ["status"],
        unique=False,
        schema="attribution",
    )
    op.create_table(
        "observation",
        sa.Column("location_id", sa.BigInteger(), nullable=False),
        sa.Column("sensor_id", sa.BigInteger(), nullable=True),
        sa.Column("scene_id", sa.String(length=256), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_fraction", sa.Float(), nullable=False),
        sa.Column("detection_limit_kg_h", sa.Float(), nullable=True),
        sa.Column("detection_id", sa.BigInteger(), nullable=True),
        sa.Column("run_id", sa.BigInteger(), nullable=True),
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "valid_fraction >= 0 AND valid_fraction <= 1",
            name=op.f("ck_observation_valid_fraction"),
        ),
        sa.ForeignKeyConstraint(
            ["detection_id"],
            ["review.detection.id"],
            name=op.f("fk_observation_detection_id_detection"),
        ),
        sa.ForeignKeyConstraint(
            ["location_id"],
            ["monitor.location.id"],
            name=op.f("fk_observation_location_id_location"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"], ["core.run.id"], name=op.f("fk_observation_run_id_run")
        ),
        sa.ForeignKeyConstraint(
            ["sensor_id"], ["ref.sensor.id"], name=op.f("fk_observation_sensor_id_sensor")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_observation")),
        schema="monitor",
    )
    op.create_index(
        op.f("ix_observation_location_id"),
        "observation",
        ["location_id"],
        unique=False,
        schema="monitor",
    )
    op.create_index(
        op.f("ix_observation_observed_at"),
        "observation",
        ["observed_at"],
        unique=False,
        schema="monitor",
    )
    op.create_table(
        "label_set_member",
        sa.Column("label_set_id", sa.BigInteger(), nullable=False),
        sa.Column("label_id", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(
            ["label_id"], ["review.label.id"], name=op.f("fk_label_set_member_label_id_label")
        ),
        sa.ForeignKeyConstraint(
            ["label_set_id"],
            ["review.label_set.id"],
            name=op.f("fk_label_set_member_label_set_id_label_set"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("label_set_id", "label_id", name=op.f("pk_label_set_member")),
        schema="review",
    )
    op.add_column(
        "source",
        sa.Column("event_kind", sa.String(length=64), server_default="ch4_plume", nullable=False),
        schema="ref",
    )
    op.alter_column("source", "kind", new_column_name="source_type", schema="ref")
    op.add_column("source", sa.Column("sector", sa.String(length=128), nullable=True), schema="ref")
    op.add_column(
        "source", sa.Column("country", sa.String(length=128), nullable=True), schema="ref"
    )
    op.add_column(
        "source",
        sa.Column("status", sa.String(length=16), server_default="active", nullable=False),
        schema="ref",
    )
    op.add_column(
        "source", sa.Column("first_seen", sa.DateTime(timezone=True), nullable=True), schema="ref"
    )
    op.add_column(
        "source", sa.Column("last_seen", sa.DateTime(timezone=True), nullable=True), schema="ref"
    )
    op.create_index(op.f("ix_source_country"), "source", ["country"], unique=False, schema="ref")
    op.create_index(
        op.f("ix_source_event_kind"), "source", ["event_kind"], unique=False, schema="ref"
    )
    op.create_index(op.f("ix_source_sector"), "source", ["sector"], unique=False, schema="ref")
    op.add_column(
        "detection", sa.Column("sensor_id", sa.BigInteger(), nullable=True), schema="review"
    )
    op.add_column(
        "detection", sa.Column("source_id", sa.BigInteger(), nullable=True), schema="review"
    )
    op.add_column(
        "detection", sa.Column("event_id", sa.BigInteger(), nullable=True), schema="review"
    )
    op.add_column(
        "detection", sa.Column("dataset_id", sa.BigInteger(), nullable=True), schema="review"
    )
    op.add_column(
        "detection",
        sa.Column(
            "attrs", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False
        ),
        schema="review",
    )
    op.add_column(
        "detection", sa.Column("supersedes_id", sa.BigInteger(), nullable=True), schema="review"
    )
    op.alter_column(
        "detection",
        "geom",
        existing_type=Geometry(
            geometry_type="POLYGON",
            srid=4326,
            dimension=2,
            from_text="ST_GeomFromEWKT",
            name="geometry",
            nullable=False,
            _spatial_index_reflected=True,
        ),
        type_=Geometry(
            srid=4326, dimension=2, from_text="ST_GeomFromEWKT", name="geometry", nullable=False
        ),
        existing_nullable=False,
        schema="review",
    )
    op.create_index(
        op.f("ix_detection_dataset_id"), "detection", ["dataset_id"], unique=False, schema="review"
    )
    op.create_index(
        op.f("ix_detection_event_id"), "detection", ["event_id"], unique=False, schema="review"
    )
    op.create_index(
        op.f("ix_detection_observed_at"),
        "detection",
        ["observed_at"],
        unique=False,
        schema="review",
    )
    op.create_index(
        op.f("ix_detection_sensor_id"), "detection", ["sensor_id"], unique=False, schema="review"
    )
    op.create_index(
        op.f("ix_detection_source_id"), "detection", ["source_id"], unique=False, schema="review"
    )
    op.create_foreign_key(
        op.f("fk_detection_sensor_id_sensor"),
        "detection",
        "sensor",
        ["sensor_id"],
        ["id"],
        source_schema="review",
        referent_schema="ref",
    )
    op.create_foreign_key(
        op.f("fk_detection_dataset_id_dataset"),
        "detection",
        "dataset",
        ["dataset_id"],
        ["id"],
        source_schema="review",
        referent_schema="core",
    )
    op.create_foreign_key(
        op.f("fk_detection_supersedes_id_detection"),
        "detection",
        "detection",
        ["supersedes_id"],
        ["id"],
        source_schema="review",
        referent_schema="review",
    )
    op.create_foreign_key(
        op.f("fk_detection_source_id_source"),
        "detection",
        "source",
        ["source_id"],
        ["id"],
        source_schema="review",
        referent_schema="ref",
    )
    op.create_foreign_key(
        op.f("fk_detection_event_id_event"),
        "detection",
        "event",
        ["event_id"],
        ["id"],
        source_schema="review",
        referent_schema="monitor",
        ondelete="SET NULL",
    )
    op.alter_column(
        "label",
        "geom",
        existing_type=Geometry(
            geometry_type="POLYGON",
            srid=4326,
            dimension=2,
            spatial_index=False,
            from_text="ST_GeomFromEWKT",
            name="geometry",
            _spatial_index_reflected=True,
        ),
        type_=Geometry(
            srid=4326,
            dimension=2,
            spatial_index=False,
            from_text="ST_GeomFromEWKT",
            name="geometry",
        ),
        existing_nullable=True,
        schema="review",
    )
    op.create_index(op.f("ix_label_analyst"), "label", ["analyst"], unique=False, schema="review")


def downgrade() -> None:
    op.drop_index(op.f("ix_label_analyst"), table_name="label", schema="review")
    op.alter_column(
        "label",
        "geom",
        existing_type=Geometry(
            srid=4326,
            dimension=2,
            spatial_index=False,
            from_text="ST_GeomFromEWKT",
            name="geometry",
        ),
        type_=Geometry(
            geometry_type="POLYGON",
            srid=4326,
            dimension=2,
            spatial_index=False,
            from_text="ST_GeomFromEWKT",
            name="geometry",
            _spatial_index_reflected=True,
        ),
        existing_nullable=True,
        schema="review",
    )
    op.drop_constraint(
        op.f("fk_detection_event_id_event"), "detection", schema="review", type_="foreignkey"
    )
    op.drop_constraint(
        op.f("fk_detection_source_id_source"), "detection", schema="review", type_="foreignkey"
    )
    op.drop_constraint(
        op.f("fk_detection_supersedes_id_detection"),
        "detection",
        schema="review",
        type_="foreignkey",
    )
    op.drop_constraint(
        op.f("fk_detection_dataset_id_dataset"), "detection", schema="review", type_="foreignkey"
    )
    op.drop_constraint(
        op.f("fk_detection_sensor_id_sensor"), "detection", schema="review", type_="foreignkey"
    )
    op.drop_index(op.f("ix_detection_source_id"), table_name="detection", schema="review")
    op.drop_index(op.f("ix_detection_sensor_id"), table_name="detection", schema="review")
    op.drop_index(op.f("ix_detection_observed_at"), table_name="detection", schema="review")
    op.drop_index(op.f("ix_detection_event_id"), table_name="detection", schema="review")
    op.drop_index(op.f("ix_detection_dataset_id"), table_name="detection", schema="review")
    op.alter_column(
        "detection",
        "geom",
        existing_type=Geometry(
            srid=4326, dimension=2, from_text="ST_GeomFromEWKT", name="geometry", nullable=False
        ),
        type_=Geometry(
            geometry_type="POLYGON",
            srid=4326,
            dimension=2,
            from_text="ST_GeomFromEWKT",
            name="geometry",
            nullable=False,
            _spatial_index_reflected=True,
        ),
        existing_nullable=False,
        schema="review",
    )
    op.drop_column("detection", "supersedes_id", schema="review")
    op.drop_column("detection", "attrs", schema="review")
    op.drop_column("detection", "dataset_id", schema="review")
    op.drop_column("detection", "event_id", schema="review")
    op.drop_column("detection", "source_id", schema="review")
    op.drop_column("detection", "sensor_id", schema="review")
    op.drop_index(op.f("ix_source_sector"), table_name="source", schema="ref")
    op.drop_index(op.f("ix_source_event_kind"), table_name="source", schema="ref")
    op.drop_index(op.f("ix_source_country"), table_name="source", schema="ref")
    op.drop_column("source", "last_seen", schema="ref")
    op.drop_column("source", "first_seen", schema="ref")
    op.drop_column("source", "status", schema="ref")
    op.drop_column("source", "country", schema="ref")
    op.drop_column("source", "sector", schema="ref")
    op.alter_column("source", "source_type", new_column_name="kind", schema="ref")
    op.drop_column("source", "event_kind", schema="ref")
    op.drop_table("label_set_member", schema="review")
    op.drop_index(op.f("ix_observation_observed_at"), table_name="observation", schema="monitor")
    op.drop_index(op.f("ix_observation_location_id"), table_name="observation", schema="monitor")
    op.drop_table("observation", schema="monitor")
    op.drop_index(
        op.f("ix_source_facility_status"), table_name="source_facility", schema="attribution"
    )
    op.drop_index(
        op.f("ix_source_facility_source_id"), table_name="source_facility", schema="attribution"
    )
    op.drop_index(
        op.f("ix_source_facility_facility_id"), table_name="source_facility", schema="attribution"
    )
    op.drop_table("source_facility", schema="attribution")
    op.drop_index(op.f("ix_org_asset_org_id"), table_name="org_asset", schema="attribution")
    op.drop_index(op.f("ix_org_asset_asset_id"), table_name="org_asset", schema="attribution")
    op.drop_table("org_asset", schema="attribution")
    op.drop_index(
        op.f("ix_facility_government_org_id"),
        table_name="facility_government",
        schema="attribution",
    )
    op.drop_index(
        op.f("ix_facility_government_facility_id"),
        table_name="facility_government",
        schema="attribution",
    )
    op.drop_table("facility_government", schema="attribution")
    op.drop_index(
        op.f("ix_facility_asset_facility_id"), table_name="facility_asset", schema="attribution"
    )
    op.drop_index(
        op.f("ix_facility_asset_asset_id"), table_name="facility_asset", schema="attribution"
    )
    op.drop_table("facility_asset", schema="attribution")
    op.drop_index(
        op.f("ix_location_status_location_id"), table_name="location_status", schema="monitor"
    )
    op.drop_table("location_status", schema="monitor")
    op.drop_index(op.f("ix_event_source_id"), table_name="event", schema="monitor")
    op.drop_index(op.f("ix_event_kind"), table_name="event", schema="monitor")
    op.drop_table("event", schema="monitor")
    op.drop_index(op.f("ix_assertion_provider"), table_name="assertion", schema="core")
    op.drop_index(op.f("ix_assertion_dataset_id"), table_name="assertion", schema="core")
    op.drop_table("assertion", schema="core")
    op.drop_index(op.f("ix_location_source_id"), table_name="location", schema="monitor")
    op.drop_index(op.f("ix_location_facility_id"), table_name="location", schema="monitor")
    op.drop_geospatial_index(
        "idx_location_area",
        table_name="location",
        schema="monitor",
        postgresql_using="gist",
        column_name="area",
    )
    op.drop_geospatial_table("location", schema="monitor")
    op.drop_index(op.f("ix_dataset_name"), table_name="dataset", schema="core")
    op.drop_table("dataset", schema="core")
    op.drop_index(
        op.f("ix_org_relation_parent_id"), table_name="org_relation", schema="attribution"
    )
    op.drop_index(op.f("ix_org_relation_child_id"), table_name="org_relation", schema="attribution")
    op.drop_table("org_relation", schema="attribution")
    op.drop_table("asset", schema="attribution")
    op.drop_table("label_set", schema="review")
    op.drop_index(op.f("ix_xref_entity_entity_id"), table_name="xref", schema="ref")
    op.drop_table("xref", schema="ref")
    op.drop_table("sensor", schema="ref")
    op.drop_geospatial_index(
        "idx_facility_geom",
        table_name="facility",
        schema="ref",
        postgresql_using="gist",
        column_name="geom",
    )
    op.drop_geospatial_table("facility", schema="ref")
    op.drop_index(op.f("ix_feedback_author"), table_name="feedback", schema="notify")
    op.drop_table("feedback", schema="notify")
    op.drop_table("org", schema="attribution")
    op.execute("DROP SCHEMA IF EXISTS monitor CASCADE")
    op.execute("DROP SCHEMA IF EXISTS attribution CASCADE")
