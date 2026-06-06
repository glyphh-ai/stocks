from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from .config import settings

# SQLite: relational application data.
sqlite_engine = create_engine(settings.sqlite_url, connect_args={"check_same_thread": False})
SqliteSession = sessionmaker(bind=sqlite_engine, autoflush=False, autocommit=False)

# Postgres + pgvector: hyperdimensional (HDC) vector storage.
pg_engine = create_engine(settings.pg_url, pool_pre_ping=True)
PgSession = sessionmaker(bind=pg_engine, autoflush=False, autocommit=False)


def init_pgvector() -> None:
    """Ensure the pgvector extension is available."""
    with pg_engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
