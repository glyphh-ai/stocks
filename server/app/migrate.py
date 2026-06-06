"""Apply Alembic migrations programmatically.

Used both by `python -m app.migrate` and by the FastAPI startup hook, so the
running schema is always at head after a restart.
"""

from pathlib import Path

from alembic import command
from alembic.config import Config

_SERVER_ROOT = Path(__file__).resolve().parent.parent


def _alembic_config() -> Config:
    cfg = Config(str(_SERVER_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(_SERVER_ROOT / "migrations"))
    return cfg


def run_migrations() -> None:
    command.upgrade(_alembic_config(), "head")


if __name__ == "__main__":
    run_migrations()
    print("migrations applied: schema at head")
