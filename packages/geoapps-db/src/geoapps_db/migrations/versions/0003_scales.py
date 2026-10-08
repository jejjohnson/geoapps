"""Scales: what each sensor and each look can resolve (docs/design/03-data-model.md §12).

Sensors gain revisit, overpass time, band count and nominal detection limits per kind;
observations and detections gain the pixel size they were seen at; the observation's
detection limit is renamed from detection_limit_kg_h to detection_limit, in the kind's
limit mark; detection_relation links detections of one thing across scales or sensors.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-08 10:12:08.471422
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "detection_relation",
        sa.Column("a_id", sa.BigInteger(), nullable=False),
        sa.Column("b_id", sa.BigInteger(), nullable=False),
        sa.Column("relation", sa.String(length=16), nullable=False),
        sa.Column("method", sa.String(length=64), nullable=False),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("decided_by", sa.String(length=128), nullable=True),
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "relation IN ('same_moment', 'contains', 'duplicate')",
            name=op.f("ck_detection_relation_relation"),
        ),
        sa.CheckConstraint("a_id <> b_id", name=op.f("ck_detection_relation_distinct")),
        sa.ForeignKeyConstraint(
            ["a_id"],
            ["review.detection.id"],
            name=op.f("fk_detection_relation_a_id_detection"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["b_id"],
            ["review.detection.id"],
            name=op.f("fk_detection_relation_b_id_detection"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_detection_relation")),
        sa.UniqueConstraint(
            "a_id", "b_id", "relation", name=op.f("uq_detection_relation_a_id_b_id_relation")
        ),
        schema="review",
    )
    op.create_index(
        op.f("ix_detection_relation_a_id"),
        "detection_relation",
        ["a_id"],
        unique=False,
        schema="review",
    )
    op.create_index(
        op.f("ix_detection_relation_b_id"),
        "detection_relation",
        ["b_id"],
        unique=False,
        schema="review",
    )
    op.alter_column(
        "observation", "detection_limit_kg_h", new_column_name="detection_limit", schema="monitor"
    )
    op.add_column(
        "observation", sa.Column("pixel_size_m", sa.Float(), nullable=True), schema="monitor"
    )
    op.add_column("sensor", sa.Column("revisit_days", sa.Float(), nullable=True), schema="ref")
    op.add_column(
        "sensor", sa.Column("overpass_local_time", sa.String(length=5), nullable=True), schema="ref"
    )
    op.add_column("sensor", sa.Column("n_bands", sa.Integer(), nullable=True), schema="ref")
    op.add_column(
        "sensor",
        sa.Column(
            "detection_limits",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        schema="ref",
    )
    op.add_column(
        "detection", sa.Column("pixel_size_m", sa.Float(), nullable=True), schema="review"
    )


def downgrade() -> None:
    op.drop_column("detection", "pixel_size_m", schema="review")
    op.drop_column("sensor", "detection_limits", schema="ref")
    op.drop_column("sensor", "n_bands", schema="ref")
    op.drop_column("sensor", "overpass_local_time", schema="ref")
    op.drop_column("sensor", "revisit_days", schema="ref")
    op.drop_column("observation", "pixel_size_m", schema="monitor")
    op.alter_column(
        "observation", "detection_limit", new_column_name="detection_limit_kg_h", schema="monitor"
    )
    op.drop_index(
        op.f("ix_detection_relation_b_id"), table_name="detection_relation", schema="review"
    )
    op.drop_index(
        op.f("ix_detection_relation_a_id"), table_name="detection_relation", schema="review"
    )
    op.drop_table("detection_relation", schema="review")
