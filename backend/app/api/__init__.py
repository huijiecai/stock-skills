from fastapi import APIRouter
from .stock import router as stock_router
from .index import router as index_router
from .concept import router as concept_router
from .market import router as market_router
from .collector import router as collector_router
from .simulation import router as simulation_router
from .account import router as account_router

__all__ = [
    "stock_router",
    "index_router",
    "concept_router",
    "market_router",
    "collector_router",
    "simulation_router",
    "account_router",
]