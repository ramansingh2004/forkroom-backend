from fastapi import APIRouter

from app.routes.v1.auth import router as auth_router
from app.routes.v1.health import router as health_router
from app.routes.v1.workspaces import router as workspaces_router

api_router = APIRouter()
api_router.include_router(auth_router)
api_router.include_router(health_router)
api_router.include_router(workspaces_router)
