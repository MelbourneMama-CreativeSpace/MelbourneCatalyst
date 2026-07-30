"""Media & Asset Library routes — upload/list/delete files in Supabase
Storage. Same multipart/size-cap pattern as the Knowledge Base's document
uploader (`knowledge_base.py`); storage IO lives in
`app/agents/media_library/storage.py`, this file only handles the
request/response + persistence around it.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.media_library.storage import (
    MediaLibraryNotConfiguredError,
    delete_asset,
    upload_asset,
)
from app.config import settings
from app.db.models import Company, MediaAsset
from app.db.session import get_session
from app.models.media_library import MediaAssetListResponse, MediaAssetOut
from app.security.auth import get_current_user

router = APIRouter(dependencies=[Depends(get_current_user)])


async def _get_company_or_404(session: AsyncSession, company_id: uuid.UUID) -> Company:
    company = await session.get(Company, company_id)
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found")
    return company


@router.post("/{company_id}/assets", response_model=MediaAssetOut)
async def upload_media_asset(
    company_id: uuid.UUID,
    file: UploadFile = File(...),
    tags: str | None = Form(None),
    uploaded_by: str | None = Form(None),
    session: AsyncSession = Depends(get_session),
) -> MediaAssetOut:
    await _get_company_or_404(session, company_id)

    content_bytes = await file.read()
    if len(content_bytes) > settings.MEDIA_UPLOAD_MAX_BYTES:
        raise HTTPException(status_code=413, detail="File exceeds maximum upload size")

    parsed_tags = (
        [t.strip() for t in tags.split(",") if t.strip()] if tags else None
    )

    try:
        asset = await upload_asset(
            company_id,
            file.filename or f"upload-{uuid.uuid4()}",
            file.content_type or "application/octet-stream",
            content_bytes,
            tags=parsed_tags,
            uploaded_by=uploaded_by,
        )
    except MediaLibraryNotConfiguredError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    session.add(asset)
    await session.commit()
    await session.refresh(asset)
    return MediaAssetOut.model_validate(asset)


@router.get("/{company_id}/assets", response_model=MediaAssetListResponse)
async def list_media_assets(
    company_id: uuid.UUID,
    tag: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> MediaAssetListResponse:
    await _get_company_or_404(session, company_id)

    stmt = (
        select(MediaAsset)
        .where(MediaAsset.company_id == company_id)
        .order_by(MediaAsset.created_at.desc())
    )
    rows = (await session.execute(stmt)).scalars().all()
    if tag is not None:
        # Filtered in Python, not the DB — `tags` is a JSON list on SQLite
        # and a Postgres ARRAY depending on dialect (_StringArrayType,
        # same as elsewhere in this app); this keeps the filter identical
        # on both without dialect-specific query branching for a list
        # that's realistically small per company.
        rows = [r for r in rows if r.tags and tag in r.tags]
    return MediaAssetListResponse(items=[MediaAssetOut.model_validate(r) for r in rows])


@router.delete("/assets/{asset_id}", response_model=MediaAssetOut)
async def delete_media_asset(
    asset_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> MediaAssetOut:
    asset = await session.get(MediaAsset, asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="Asset not found")

    try:
        await delete_asset(asset)
    except MediaLibraryNotConfiguredError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    result = MediaAssetOut.model_validate(asset)
    await session.delete(asset)
    await session.commit()
    return result
