"""App v1 router."""
from fastapi import APIRouter

from app.api.v1 import chat_routes, agents, auth_routes, health, knowledge, profile_routes

router = APIRouter(prefix="/v1")

# Include routers
router.include_router(chat_routes.router, prefix="/chat", tags=["chat"])
router.include_router(agents.router, tags=["agents"])
router.include_router(auth_routes.router)
router.include_router(health.router)
router.include_router(knowledge.router)
router.include_router(profile_routes.router)

@router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "version": "1.0.0"}
