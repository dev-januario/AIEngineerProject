"""Initial schema — cria tabela leads com todos os campos.

Revision ID: 001_initial_schema
Revises: 
Create Date: 2026-06-19
"""
from alembic import op
import sqlalchemy as sa

revision = "001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "leads",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("phone", sa.String(50), nullable=True),
        sa.Column("company", sa.String(255), nullable=True),
        sa.Column("role", sa.String(255), nullable=True),
        sa.Column("company_size", sa.String(50), nullable=True),
        sa.Column("sector", sa.String(100), nullable=True),
        sa.Column("linkedin_url", sa.String(500), nullable=True),
        sa.Column("enrichment_data", sa.JSON(), nullable=True),
        sa.Column("qualification_score", sa.Float(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "new", "enriched", "contacted", "confirmed", "declined",
                "no_response", "attended", "no_show", "followed_up",
                "meeting_booked", "out_of_icp",
                name="leadstatus",
            ),
            nullable=False,
        ),
        sa.Column(
            "funnel_phase",
            sa.Enum(
                "capture", "enrichment", "pre_event", "post_event", "closed",
                name="funnelphase",
            ),
            nullable=False,
        ),
        sa.Column("communication_log", sa.JSON(), nullable=True),
        sa.Column("last_contacted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("contact_attempts", sa.Integer(), nullable=False),
        sa.Column("event_notes", sa.Text(), nullable=True),
        sa.Column("attended", sa.Boolean(), nullable=True),
        # Acompanhante
        sa.Column("with_companion", sa.Boolean(), nullable=False),
        sa.Column("companion_email", sa.String(255), nullable=True),
        sa.Column("companion_relationship", sa.String(50), nullable=True),
        # LGPD
        sa.Column("lgpd_consent", sa.Boolean(), nullable=False),
        sa.Column("consent_at", sa.DateTime(timezone=True), nullable=True),
        # Timestamps
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_leads_email"), "leads", ["email"], unique=True)
    op.create_index(op.f("ix_leads_status"), "leads", ["status"], unique=False)
    op.create_index(op.f("ix_leads_funnel_phase"), "leads", ["funnel_phase"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_leads_funnel_phase"), table_name="leads")
    op.drop_index(op.f("ix_leads_status"), table_name="leads")
    op.drop_index(op.f("ix_leads_email"), table_name="leads")
    op.drop_table("leads")
    op.execute("DROP TYPE IF EXISTS leadstatus")
    op.execute("DROP TYPE IF EXISTS funnelphase")
