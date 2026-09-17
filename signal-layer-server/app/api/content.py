from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_chan_service, get_data_service, get_indicator_service
from app.api.security import require_permission
from app.db import get_session
from app.models.auth import User
from app.models.content import ArticleDraft, ContentTemplate
from app.schemas.content import ArticleContentUpdate, ArticleDraftResponse, ArticleGenerateRequest, ArticleStatusUpdate, ContentTemplateCreate, ContentTemplateResponse, ContentTemplateUpdate
from app.services.content_service import ContentService

router = APIRouter(prefix="/api/v1/content", tags=["content"])


def _template_response(item: ContentTemplate, user_id: Optional[int] = None) -> ContentTemplateResponse:
    return ContentTemplateResponse(
        id=item.id, name=item.name, description=item.description,
        sections=item.sections or [], enabled=item.enabled, built_in=item.built_in,
        editable=bool(not item.built_in and item.user_id == user_id),
    )


def _draft_response(item: ArticleDraft) -> ArticleDraftResponse:
    return ArticleDraftResponse(
        id=item.id, template_id=item.template_id, title=item.title,
        symbol=item.symbol, symbol_name=item.symbol_name, market=item.market,
        as_of=item.as_of, timeframes=item.timeframes or [],
        structured_data=item.structured_data or {}, chart_specs=item.chart_specs or [],
        standard_markdown=item.standard_markdown,
        platform_variants=item.platform_variants or {}, status=item.status,
        created_at=item.created_at,
    )


@router.get("/templates", response_model=list[ContentTemplateResponse], dependencies=[Depends(require_permission("content.view"))])
async def list_content_templates(user: User = Depends(require_permission("content.view")), session: AsyncSession = Depends(get_session)):
    items = (await session.execute(select(ContentTemplate).where(
        ContentTemplate.enabled.is_(True),
        or_(ContentTemplate.built_in.is_(True), ContentTemplate.user_id == user.id),
    ).order_by(ContentTemplate.id))).scalars().all()
    return [_template_response(item, user.id) for item in items]


@router.post("/templates", response_model=ContentTemplateResponse, status_code=201, dependencies=[Depends(require_permission("content.manage"))])
async def create_content_template(
    body: ContentTemplateCreate,
    user: User = Depends(require_permission("content.manage")),
    session: AsyncSession = Depends(get_session),
):
    item = ContentTemplate(
        id=f"content_{user.id}_{int(datetime.now().timestamp() * 1000)}",
        user_id=user.id, name=body.name, description=body.description,
        sections=list(dict.fromkeys(body.sections)), enabled=True, built_in=False,
    )
    session.add(item)
    await session.commit()
    await session.refresh(item)
    return _template_response(item, user.id)


@router.put("/templates/{template_id}", response_model=ContentTemplateResponse, dependencies=[Depends(require_permission("content.manage"))])
async def update_content_template(
    template_id: str,
    body: ContentTemplateUpdate,
    user: User = Depends(require_permission("content.manage")),
    session: AsyncSession = Depends(get_session),
):
    item = await session.get(ContentTemplate, template_id)
    if not item or item.built_in or item.user_id != user.id:
        raise HTTPException(status_code=404, detail="可编辑模板不存在")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(item, field, list(dict.fromkeys(value)) if field == "sections" else value)
    await session.commit()
    await session.refresh(item)
    return _template_response(item, user.id)


@router.delete("/templates/{template_id}", status_code=204, dependencies=[Depends(require_permission("content.manage"))])
async def delete_content_template(
    template_id: str,
    user: User = Depends(require_permission("content.manage")),
    session: AsyncSession = Depends(get_session),
):
    item = await session.get(ContentTemplate, template_id)
    if not item or item.built_in or item.user_id != user.id:
        raise HTTPException(status_code=404, detail="可删除模板不存在")
    await session.delete(item)
    await session.commit()


@router.post("/generate", response_model=ArticleDraftResponse, status_code=201, dependencies=[Depends(require_permission("content.generate"))])
async def generate_article(
    body: ArticleGenerateRequest,
    user: User = Depends(require_permission("content.generate")),
    session: AsyncSession = Depends(get_session),
):
    template = await session.get(ContentTemplate, body.template_id)
    if not template or not template.enabled or (not template.built_in and template.user_id != user.id):
        raise HTTPException(status_code=404, detail="内容模板不存在或已停用")
    service = ContentService(get_data_service(), get_chan_service(), get_indicator_service())
    try:
        draft = await service.generate(
            session, user_id=user.id, template=template,
            symbol=body.symbol, symbol_name=body.symbol_name, market=body.market,
            timeframes=list(dict.fromkeys(body.timeframes)), kline_limit=body.kline_limit,
        )
    except Exception as error:
        await session.rollback()
        raise HTTPException(status_code=500, detail=f"文章生成失败：{error}") from error
    return _draft_response(draft)


@router.get("/drafts", response_model=list[ArticleDraftResponse], dependencies=[Depends(require_permission("content.view"))])
async def list_drafts(
    limit: int = Query(default=30, ge=1, le=100),
    user: User = Depends(require_permission("content.view")),
    session: AsyncSession = Depends(get_session),
):
    items = (await session.execute(select(ArticleDraft).where(
        ArticleDraft.user_id == user.id
    ).order_by(ArticleDraft.created_at.desc()).limit(limit))).scalars().all()
    return [_draft_response(item) for item in items]


@router.get("/drafts/{draft_id}", response_model=ArticleDraftResponse, dependencies=[Depends(require_permission("content.view"))])
async def get_draft(
    draft_id: int,
    user: User = Depends(require_permission("content.view")),
    session: AsyncSession = Depends(get_session),
):
    item = await session.get(ArticleDraft, draft_id)
    if not item or item.user_id != user.id:
        raise HTTPException(status_code=404, detail="文章草稿不存在")
    return _draft_response(item)


@router.put("/drafts/{draft_id}/status", response_model=ArticleDraftResponse, dependencies=[Depends(require_permission("content.manage"))])
async def update_draft_status(
    draft_id: int,
    body: ArticleStatusUpdate,
    user: User = Depends(require_permission("content.manage")),
    session: AsyncSession = Depends(get_session),
):
    item = await session.get(ArticleDraft, draft_id)
    if not item or item.user_id != user.id:
        raise HTTPException(status_code=404, detail="文章草稿不存在")
    item.status = body.status
    item.reviewed_at = datetime.now() if body.status == "reviewed" else None
    await session.commit()
    await session.refresh(item)
    return _draft_response(item)


@router.put("/drafts/{draft_id}", response_model=ArticleDraftResponse, dependencies=[Depends(require_permission("content.manage"))])
async def update_draft_content(
    draft_id: int,
    body: ArticleContentUpdate,
    user: User = Depends(require_permission("content.manage")),
    session: AsyncSession = Depends(get_session),
):
    item = await session.get(ArticleDraft, draft_id)
    if not item or item.user_id != user.id:
        raise HTTPException(status_code=404, detail="文章草稿不存在")
    if body.standard_markdown is not None:
        item.standard_markdown = body.standard_markdown
    if body.platform_variants is not None:
        item.platform_variants = body.platform_variants
    await session.commit()
    await session.refresh(item)
    return _draft_response(item)
