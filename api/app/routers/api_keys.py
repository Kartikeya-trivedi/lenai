"""
API key management endpoints — create, list, rotate, revoke.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_api_key
from app.models.api_key import ApiKey
from app.schemas.api_keys import (
    ApiKeyCreatedResponse,
    ApiKeyResponse,
    CreateApiKeyRequest,
    RotateKeyResponse,
    UpdateApiKeyRequest,
)
from app.services.api_key_service import ApiKeyService

router = APIRouter(prefix="/v1/api-keys", tags=["API Keys"])


@router.post(
    "",
    response_model=ApiKeyCreatedResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new API key",
)
async def create_api_key(
    request: CreateApiKeyRequest,
    db: AsyncSession = Depends(get_db),
    api_key: ApiKey = Depends(get_current_api_key),
):
    """Create a new API key. The raw key is returned ONLY in this response."""
    service = ApiKeyService(db)
    new_key, raw_key = await service.create_key(
        tenant_id=api_key.tenant_id,
        name=request.name,
        scopes=request.scopes,
        rate_limit_rpm=request.rate_limit_rpm,
        monthly_request_cap=request.monthly_request_cap,
    )

    response = ApiKeyCreatedResponse.model_validate(new_key)
    response.raw_key = raw_key
    return response


@router.get(
    "",
    response_model=list[ApiKeyResponse],
    summary="List API keys",
)
async def list_api_keys(
    db: AsyncSession = Depends(get_db),
    api_key: ApiKey = Depends(get_current_api_key),
):
    """List all API keys for the current tenant (keys are masked)."""
    service = ApiKeyService(db)
    keys = await service.list_keys(api_key.tenant_id)
    return [ApiKeyResponse.model_validate(k) for k in keys]


@router.patch(
    "/{key_id}",
    response_model=ApiKeyResponse,
    summary="Update an API key",
)
async def update_api_key(
    key_id: uuid.UUID,
    request: UpdateApiKeyRequest,
    db: AsyncSession = Depends(get_db),
    api_key: ApiKey = Depends(get_current_api_key),
):
    """Update an API key's name, scopes, or rate limits."""
    service = ApiKeyService(db)
    updated = await service.update_key(
        key_id=key_id,
        tenant_id=api_key.tenant_id,
        **request.model_dump(exclude_none=True),
    )

    if updated is None:
        raise HTTPException(status_code=404, detail="API key not found")

    return ApiKeyResponse.model_validate(updated)


@router.delete(
    "/{key_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke an API key",
)
async def revoke_api_key(
    key_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    api_key: ApiKey = Depends(get_current_api_key),
):
    """Revoke an API key (soft delete)."""
    service = ApiKeyService(db)
    revoked = await service.revoke_key(key_id, api_key.tenant_id)

    if revoked is None:
        raise HTTPException(status_code=404, detail="API key not found")


@router.post(
    "/{key_id}/rotate",
    response_model=RotateKeyResponse,
    summary="Rotate an API key",
)
async def rotate_api_key(
    key_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    api_key: ApiKey = Depends(get_current_api_key),
):
    """Revoke the old key and issue a new one with the same config."""
    service = ApiKeyService(db)
    new_key, raw_key = await service.rotate_key(key_id, api_key.tenant_id)

    if new_key is None:
        raise HTTPException(status_code=404, detail="API key not found")

    return RotateKeyResponse(
        new_key=raw_key,
        old_key_revoked_at=datetime.now(timezone.utc),
    )
