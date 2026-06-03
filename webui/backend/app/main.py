"""MATB Research Console backend (Phase 1A)."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="MATB Research Console", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3100"],
    allow_methods=["*"],
    allow_headers=["*"],
)

from app.routers import fits, ingest, metrics, participants, tracker  # noqa: E402

app.include_router(participants.router)
app.include_router(ingest.router)
app.include_router(tracker.router)
app.include_router(metrics.router)
app.include_router(fits.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
