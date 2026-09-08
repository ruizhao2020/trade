import logging
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from app.db import get_session
from app.models.template import Template
from app.schemas.template import TemplateCreate, TemplateUpdate, TemplateResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/templates", tags=["templates"])


def _to_response(t: Template) -> TemplateResponse:
    return TemplateResponse(
        id=t.id,
        name=t.name,
        logic=t.logic,
        condition_groups=t.condition_groups or [],
        primary_tf=t.primary_tf,
        secondary_tfs=t.secondary_tfs or [],
        created_at=t.created_at.isoformat() if t.created_at else None,
        updated_at=t.updated_at.isoformat() if t.updated_at else None,
        enabled=t.enabled,
        trade_params=t.trade_params,
    )


@router.get("", response_model=list[TemplateResponse])
async def list_templates(session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(Template).order_by(Template.updated_at.desc()))
    templates = result.scalars().all()
    logger.info(f"GET /templates -> {len(templates)} templates")
    return [_to_response(t) for t in templates]


@router.post("", response_model=TemplateResponse, status_code=201)
async def create_template(body: TemplateCreate, session: AsyncSession = Depends(get_session)):
    logger.info(f"POST /templates id={body.id}")
    existing = await session.get(Template, body.id)
    if existing:
        raise HTTPException(status_code=409, detail="Template already exists")
    t = Template(
        id=body.id,
        name=body.name,
        logic=body.logic,
        condition_groups=body.condition_groups,
        primary_tf=body.primary_tf,
        secondary_tfs=body.secondary_tfs,
        enabled=body.enabled,
        trade_params=body.trade_params.model_dump() if body.trade_params else None,
    )
    session.add(t)
    await session.commit()
    await session.refresh(t)
    logger.info(f"POST /templates id={body.id} created")
    return _to_response(t)


@router.get("/{template_id}", response_model=TemplateResponse)
async def get_template(template_id: str, session: AsyncSession = Depends(get_session)):
    logger.info(f"GET /templates/{template_id}")
    t = await session.get(Template, template_id)
    if not t:
        raise HTTPException(status_code=404, detail="Template not found")
    return _to_response(t)


@router.put("/{template_id}", response_model=TemplateResponse)
async def update_template(template_id: str, body: TemplateUpdate, session: AsyncSession = Depends(get_session)):
    logger.info(f"PUT /templates/{template_id}")
    t = await session.get(Template, template_id)
    if not t:
        raise HTTPException(status_code=404, detail="Template not found")
    update_data = body.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(t, key, value)
    await session.commit()
    await session.refresh(t)
    logger.info(f"PUT /templates/{template_id} updated")
    return _to_response(t)


@router.delete("/{template_id}", status_code=204)
async def delete_template(template_id: str, session: AsyncSession = Depends(get_session)):
    logger.info(f"DELETE /templates/{template_id}")
    t = await session.get(Template, template_id)
    if not t:
        raise HTTPException(status_code=404, detail="Template not found")
    await session.delete(t)
    await session.commit()
    logger.info(f"DELETE /templates/{template_id} deleted")
