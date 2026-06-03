from fastapi import APIRouter

from app.core.config import get_settings


router = APIRouter()


@router.get("/health")
async def health_check() -> dict[str, str]:
    settings = get_settings()
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "status": "ok",
    }
