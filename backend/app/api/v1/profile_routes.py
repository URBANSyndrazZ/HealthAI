from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models.profile import UserProfile
from app.models.user import User
from app.schemas.profile import ProfileResponse, ProfileUpdateRequest

router = APIRouter(prefix="/profile", tags=["profile"])


async def _get_profile(db: AsyncSession, current_user: User) -> UserProfile:
    result = await db.execute(
        select(UserProfile).where(UserProfile.user_id == current_user.id)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        profile = UserProfile(user_id=current_user.id)
        db.add(profile)
        await db.flush()
    return profile


@router.get("", response_model=ProfileResponse)
async def get_profile(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ProfileResponse:
    profile = await _get_profile(db, current_user)
    return ProfileResponse(
        user_id=current_user.id,
        basic_info=profile.basic_info or {},
        health_status=profile.health_status or {},
        health_goals=profile.health_goals or [],
        version=profile.version,
    )


@router.put("", response_model=ProfileResponse)
async def update_profile(
    payload: ProfileUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ProfileResponse:
    profile = await _get_profile(db, current_user)
    profile.basic_info = payload.basic_info.model_dump(exclude_none=True)
    profile.health_status = payload.health_status.model_dump()
    profile.health_goals = payload.health_goals
    profile.version += 1
    await db.commit()
    await db.refresh(profile)
    return ProfileResponse(
        user_id=current_user.id,
        basic_info=profile.basic_info or {},
        health_status=profile.health_status or {},
        health_goals=profile.health_goals or [],
        version=profile.version,
    )
