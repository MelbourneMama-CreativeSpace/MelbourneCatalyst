"""API v1 Router - aggregates all module routes."""

from fastapi import APIRouter

from app.api.v1.endpoints.chat import router as chat_router
from app.api.v1.endpoints.companies import router as companies_router
from app.api.v1.endpoints.competitor_research import router as competitor_research_router
from app.api.v1.endpoints.content_management import router as content_management_router
from app.api.v1.endpoints.dashboard import router as dashboard_router
from app.api.v1.endpoints.knowledge_base import router as knowledge_base_router
from app.api.v1.endpoints.media_library import router as media_library_router
from app.api.v1.endpoints.social_media_analyzer import router as social_media_analyzer_router
from app.api.v1.endpoints.trends import router as trends_router

api_router = APIRouter()

api_router.include_router(dashboard_router, prefix="/dashboard", tags=["Dashboard"])
api_router.include_router(chat_router, prefix="/chat", tags=["Chat"])
api_router.include_router(companies_router, prefix="/companies", tags=["Company Analyzer"])
api_router.include_router(
    knowledge_base_router, prefix="/knowledge-base", tags=["Knowledge Base"]
)
api_router.include_router(trends_router, prefix="/trend-analyzer", tags=["Trend Analyzer"])
api_router.include_router(
    content_management_router, prefix="/content-management", tags=["Content Management"]
)
api_router.include_router(
    competitor_research_router, prefix="/competitor-research", tags=["Competitor Research"]
)
api_router.include_router(
    social_media_analyzer_router, prefix="/social-media-analyzer", tags=["Social Media Analyzer"]
)
api_router.include_router(media_library_router, prefix="/media-library", tags=["Media Library"])
