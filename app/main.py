"""
FastAPI application entry point.
    use:
    python -m uvicorn app.main:app --reload
"""

from dotenv import load_dotenv
load_dotenv()

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.catalog_mapper import load_categories
from app.routes import router
from config import APP_DEBUG



@asynccontextmanager
async def lifespan(app: FastAPI):
    """Runs once at startup before the server begins accepting requests."""
    print("[startup] Loading catalog categories for category mapper...")
    load_categories()
    print("[startup] Ready.")
    yield
    # Nothing to clean up on shutdown at this scale


app = FastAPI(
    title="Decor Chatbot API",
    description="Interior decor recommendation pipeline — extraction, retrieval, recommendation.",
    version="0.1.0",
    debug=APP_DEBUG,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # open for local dev — tighten for production
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api/v1")


@app.get("/health")
async def health() -> dict:
    """Simple liveness check — useful for deployment health probes and
    for the frontend to confirm the API is reachable on load."""
    return {"status": "ok"}