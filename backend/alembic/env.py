from alembic import context
from app.database.session import Base, get_engine
from app.models import Dam, Scenario, SimulationRun, ImpactSummary

target_metadata = Base.metadata

if context.is_offline_mode():
    context.configure(dialect_name="postgresql", target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    with get_engine().connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
