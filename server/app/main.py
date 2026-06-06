from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from .config import settings
from .db import pg_engine, sqlite_engine
from .migrate import run_migrations
from .routers import credentials, dashboard, jobs, templates, tools, trades


@asynccontextmanager
async def lifespan(app: FastAPI):
    run_migrations()  # bring the schema to head on every startup
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(jobs.router)
app.include_router(dashboard.router)
app.include_router(templates.router)
app.include_router(tools.router)
app.include_router(credentials.router)
app.include_router(trades.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "app": settings.app_name}


@app.get("/health/db")
def health_db() -> dict[str, str]:
    result: dict[str, str] = {}
    try:
        with sqlite_engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        result["sqlite"] = "ok"
    except Exception as exc:  # noqa: BLE001
        result["sqlite"] = f"error: {exc}"
    try:
        with pg_engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        result["postgres"] = "ok"
    except Exception as exc:  # noqa: BLE001
        result["postgres"] = f"error: {exc}"
    return result
