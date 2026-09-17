from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.schemas.site import PublicSiteConfigResponse
from app.services.public_site_service import public_indicator_feature_policies, public_indicator_policies

router = APIRouter(prefix="/api/v1/site", tags=["site"])


@router.get("/config", response_model=PublicSiteConfigResponse)
async def public_site_config(session: AsyncSession = Depends(get_session)):
    return PublicSiteConfigResponse(
        indicators=await public_indicator_policies(session),
        indicator_features=await public_indicator_feature_policies(session),
    )
