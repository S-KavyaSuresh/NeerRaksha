from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def record_columns():
    return [sa.Column("id", sa.Uuid(), nullable=False, primary_key=True), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)]


def upgrade():
    op.create_table("dams", *record_columns(), sa.Column("name", sa.String(160), nullable=False), sa.Column("river", sa.String(120), nullable=False), sa.Column("state", sa.String(120), nullable=False), sa.Column("latitude", sa.Float(), nullable=False), sa.Column("longitude", sa.Float(), nullable=False))
    op.create_table("scenarios", *record_columns(), sa.Column("dam_id", sa.Uuid(), sa.ForeignKey("dams.id"), nullable=False), sa.Column("name", sa.String(160), nullable=False), sa.Column("breach_type", sa.String(60), nullable=False), sa.Column("breach_width_m", sa.Float(), nullable=False), sa.Column("breach_time_minutes", sa.Float(), nullable=False), sa.Column("initial_water_level_m", sa.Float(), nullable=False), sa.Column("status", sa.String(40), nullable=False))
    op.create_index("ix_scenarios_dam_id", "scenarios", ["dam_id"])
    op.create_table("simulation_runs", *record_columns(), sa.Column("scenario_id", sa.Uuid(), sa.ForeignKey("scenarios.id"), nullable=False), sa.Column("engine", sa.String(100), nullable=False), sa.Column("status", sa.String(40), nullable=False), sa.Column("progress", sa.Integer(), nullable=False), sa.Column("started_at", sa.DateTime(timezone=True), nullable=True), sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True), sa.Column("output_path", sa.String(512), nullable=True), sa.CheckConstraint("progress >= 0 AND progress <= 100", name="valid_progress"))
    op.create_index("ix_simulation_runs_scenario_id", "simulation_runs", ["scenario_id"])
    op.create_table("impact_summaries", *record_columns(), sa.Column("simulation_run_id", sa.Uuid(), sa.ForeignKey("simulation_runs.id"), nullable=False), sa.Column("flooded_area_km2", sa.Float(), nullable=False), sa.Column("maximum_depth_m", sa.Float(), nullable=False), sa.Column("population_exposed", sa.Integer(), nullable=False), sa.Column("buildings_affected", sa.Integer(), nullable=False), sa.Column("critical_assets", sa.Integer(), nullable=False))
    op.create_index("ix_impact_summaries_simulation_run_id", "impact_summaries", ["simulation_run_id"], unique=True)


def downgrade():
    op.drop_table("impact_summaries")
    op.drop_table("simulation_runs")
    op.drop_table("scenarios")
    op.drop_table("dams")
