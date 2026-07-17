"""API v1 Router - aggregates all module routes."""

from fastapi import APIRouter

from app.api.v1.endpoints.companies import router as companies_router
from app.api.v1.endpoints.knowledge_base import router as knowledge_base_router
from app.api.v1.endpoints.trends import router as trends_router

api_router = APIRouter()

api_router.include_router(companies_router, prefix="/companies", tags=["Company Analyzer"])
api_router.include_router(
    knowledge_base_router, prefix="/knowledge-base", tags=["Knowledge Base"]
)
api_router.include_router(trends_router, prefix="/trend-analyzer", tags=["Trend Analyzer"])


@api_router.get("/content-management", tags=["Content Management"])
async def content_management_status():
    """Content Management module status."""
    return {"module": "Content Management", "status": "active", "agents": ["StrategyConsultant", "ContentPlanner", "CampaignManager", "BrandCollaboration", "Analytics"]}


@api_router.get("/social-media-analyzer", tags=["Social Media Analyzer"])
async def social_media_analyzer_status():
    """Social Media Analyzer module status."""
    return {"module": "Social Media Analyzer", "status": "active", "agents": ["PlatformIntegration", "PerformanceTracking", "SocialAnalytics", "ChannelIntelligence"]}
