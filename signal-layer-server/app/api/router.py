from fastapi import APIRouter
from app.api.kline import router as kline_router
from app.api.chan import router as chan_router
from app.api.indicator import router as indicator_router
from app.api.signal import router as signal_router
from app.api.template import router as template_router
from app.api.symbol import router as symbol_router
from app.api.ws import router as ws_router
from app.api.screener import router as screener_router
from app.api.notifications import router as notifications_router
from app.api.auth import router as auth_router
from app.api.admin import router as admin_router

api_router = APIRouter()

api_router.include_router(auth_router)
api_router.include_router(admin_router)
api_router.include_router(kline_router)
api_router.include_router(chan_router)
api_router.include_router(indicator_router)
api_router.include_router(signal_router)
api_router.include_router(template_router)
api_router.include_router(symbol_router)
api_router.include_router(ws_router)
api_router.include_router(screener_router)
api_router.include_router(notifications_router)
