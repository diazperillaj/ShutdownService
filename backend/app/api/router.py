from fastapi import APIRouter

from .routes import auth, control, health, history
from .websockets import agent, panel

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(control.router)
api_router.include_router(history.router)
api_router.include_router(agent.router)
api_router.include_router(panel.router)
