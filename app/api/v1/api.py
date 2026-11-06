from fastapi import APIRouter
from app.api.v1.endpoints import workflows , leads , exports  , auth , ingestion

api_router = APIRouter()

api_router.include_router(workflows.router , tags = ["Workflows"])
api_router.include_router(leads.router , tags = ["Leads"])
api_router.include_router(exports.router , tags = ["Exports"])
api_router.include_router(auth.router , tags = ["Authentication"])
api_router.include_router(ingestion.router , tags = ["Ingestion"])




