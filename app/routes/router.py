from fastapi import APIRouter

from app.routes.v1.action_reviews import router as action_reviews_router
from app.routes.v1.auth import router as auth_router
from app.routes.v1.collaboration import router as collaboration_router
from app.routes.v1.decision_locks import router as decision_locks_router
from app.routes.v1.decisions import router as decisions_router
from app.routes.v1.health import router as health_router
from app.routes.v1.objections import router as objections_router
from app.routes.v1.proposals import router as proposals_router
from app.routes.v1.voting import router as voting_router
from app.routes.v1.workspaces import router as workspaces_router

api_router = APIRouter()
api_router.include_router(auth_router)
api_router.include_router(health_router)
api_router.include_router(workspaces_router)
api_router.include_router(decisions_router)
api_router.include_router(decision_locks_router)
api_router.include_router(proposals_router)
api_router.include_router(objections_router)
api_router.include_router(voting_router)
api_router.include_router(action_reviews_router)
api_router.include_router(collaboration_router)
