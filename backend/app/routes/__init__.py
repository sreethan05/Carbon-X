"""Router modules for CarbonX API."""
from app.routes.auth_router import router as auth_router
from app.routes.farms_router import router as farms_router
from app.routes.marketplace_router import router as marketplace_router
from app.routes.trust_router import router as trust_router
from app.routes.ops_router import router as ops_router
from app.routes.fpo_router import router as fpo_router
from app.routes.corporate_router import router as corporate_router

__all__ = [
    "auth_router",
    "farms_router",
    "marketplace_router",
    "trust_router",
    "ops_router",
    "fpo_router",
    "corporate_router",
]