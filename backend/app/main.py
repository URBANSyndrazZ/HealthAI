"""HealthAI Application"""
import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import router as v1_router
from app.config import settings
from app.core.http_guard import RequestSizeLimitMiddleware, InMemoryRateLimitMiddleware
from app.core.observability import configure_loggin, RequestTraceMiddleware
from app.memory.long_term import long_term_memory
from app.models.database import init_db
from app.rag.retriever import rag_retriever

configure_loggin()
logger = logging.getLogger(__name__)

async def _warmup_rag() -> None:
    """Warm up RAG dependencies in the background so first chat is faster."""
    try:
        logger.info("[startup] RAG warmup started")
        await rag_retriever.initialize()
        logger.info("[startup] RAG warmup finished")
    except Exception:
        logger.exception("[startup] RAG warmup failed")

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # StartUp
    print("🚀 Starting HealthAI API...")
    print("📚 API Documentation: http://localhost:8000/docs")
    await init_db()
    try:
        await long_term_memory.initialize()
    except Exception:
        logger.exception("[startup] long-term memory initialization failed")
    warmup_task = None
    if settings.rag_warmup_on_startup:
        warmup_task = asyncio.create_task(_warmup_rag())
        app.state.rag_warmup_task = warmup_task
    print("🗄️ Database initialized")
    print("")
    yield
    # Shutdown
    if warmup_task is not None and not warmup_task.done():
        warmup_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await warmup_task
    await rag_retriever.close()
    await long_term_memory.close()
    print("👋 Shutting down...")

app = FastAPI(
    title="HealthAI API",
    description="Multi-agent intelligent health management system",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(RequestTraceMiddleware)
app.add_middleware(RequestSizeLimitMiddleware)
app.add_middleware(InMemoryRateLimitMiddleware)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # In production, replace with specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(v1_router, prefix="/api")

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "messages": "Welcome to HealthAI API",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/api/v1/health",
    }
