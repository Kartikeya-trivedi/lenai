"""
Initial database schema — creates all tables, indexes, and enum types.

Revision ID: 001
Create Date: 2025-05-23
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = "001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Create ENUM types ──────────────────────────────────────
    job_status_enum = postgresql.ENUM(
        "pending", "queued", "processing", "completed", "failed", "dead_letter",
        name="jobstatus",
        create_type=False,
    )
    modality_enum = postgresql.ENUM(
        "image", "video", "voice_stt", "voice_tts",
        name="modality",
        create_type=False,
    )

    # Create enums explicitly
    op.execute("CREATE TYPE IF NOT EXISTS jobstatus AS ENUM ('pending', 'queued', 'processing', 'completed', 'failed', 'dead_letter')")
    op.execute("CREATE TYPE IF NOT EXISTS modality AS ENUM ('image', 'video', 'voice_stt', 'voice_tts')")

    # ── api_keys table ─────────────────────────────────────────
    op.create_table(
        "api_keys",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("key_hash", sa.String(255), nullable=False, unique=True),
        sa.Column("key_prefix", sa.String(20), nullable=False, index=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("scopes", postgresql.ARRAY(sa.String), server_default="{}"),
        sa.Column("rate_limit_rpm", sa.Integer, server_default="60"),
        sa.Column("monthly_request_cap", sa.Integer, server_default="10000"),
        sa.Column("is_active", sa.Boolean, server_default="true"),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
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
    )

    # ── jobs table ─────────────────────────────────────────────
    op.create_table(
        "jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "api_key_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("api_keys.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("modality", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("input_params", postgresql.JSONB, server_default="{}"),
        sa.Column("input_file_key", sa.String(500), nullable=True),
        sa.Column("output_file_key", sa.String(500), nullable=True),
        sa.Column("output_url", sa.Text, nullable=True),
        sa.Column("output_url_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("error_trace", sa.Text, nullable=True),
        sa.Column("retry_count", sa.Integer, server_default="0"),
        sa.Column("max_retries", sa.Integer, server_default="3"),
        sa.Column("webhook_url", sa.String(2048), nullable=True),
        sa.Column("progress", sa.Integer, server_default="0"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
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
    )

    # Composite indexes for common queries
    op.create_index("ix_jobs_tenant_status", "jobs", ["tenant_id", "status"])
    op.create_index("ix_jobs_tenant_created", "jobs", ["tenant_id", "created_at"])
    op.create_index("ix_jobs_status_created", "jobs", ["status", "created_at"])

    # ── usage_records table ────────────────────────────────────
    op.create_table(
        "usage_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "api_key_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("api_keys.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "job_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("modality", sa.String(20), nullable=False),
        sa.Column("compute_time_ms", sa.Integer, nullable=True),
        sa.Column("input_size_bytes", sa.BigInteger, nullable=True),
        sa.Column("output_size_bytes", sa.BigInteger, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    op.create_index("ix_usage_tenant_created", "usage_records", ["tenant_id", "created_at"])

    # ── webhook_deliveries table ───────────────────────────────
    op.create_table(
        "webhook_deliveries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "job_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("url", sa.String(2048), nullable=False),
        sa.Column("payload", postgresql.JSONB, nullable=True),
        sa.Column("status_code", sa.Integer, nullable=True),
        sa.Column("response_body", sa.Text, nullable=True),
        sa.Column("attempt_number", sa.Integer, nullable=False, server_default="1"),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    op.create_index("ix_webhook_job_id", "webhook_deliveries", ["job_id"])

    # ── Updated-at trigger function ────────────────────────────
    op.execute("""
        CREATE OR REPLACE FUNCTION update_updated_at_column()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = now();
            RETURN NEW;
        END;
        $$ language 'plpgsql';
    """)

    # Apply trigger to tables with updated_at
    for table_name in ("api_keys", "jobs"):
        op.execute(f"""
            CREATE TRIGGER update_{table_name}_updated_at
                BEFORE UPDATE ON {table_name}
                FOR EACH ROW
                EXECUTE FUNCTION update_updated_at_column();
        """)


def downgrade() -> None:
    # Drop triggers
    for table_name in ("api_keys", "jobs"):
        op.execute(f"DROP TRIGGER IF EXISTS update_{table_name}_updated_at ON {table_name}")

    op.execute("DROP FUNCTION IF EXISTS update_updated_at_column()")

    # Drop tables in reverse dependency order
    op.drop_table("webhook_deliveries")
    op.drop_table("usage_records")
    op.drop_table("jobs")
    op.drop_table("api_keys")

    # Drop enum types
    op.execute("DROP TYPE IF EXISTS jobstatus")
    op.execute("DROP TYPE IF EXISTS modality")
