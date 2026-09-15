import copy
import logging
from concurrent.futures.thread import ThreadPoolExecutor

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import UserProfile

logger = logging.getLogger(__name__)
_executor = ThreadPoolExecutor(max_workers=2)

def merge_profile(current: dict, extracted: dict) -> dict:
    for field, value in extracted.items():
        if field not in current:
            current[field] = value
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, str) and item.startswith("-"):
                    current[field] = [x for x in current[field] if x != item[1:]]
                elif isinstance(item, str) and item.startswith("+"):
                    if item[1:] not in current[field]:
                        current[field].append(item[1:])
                else:
                    if item not in current[field]:
                        current[field].append(item)
        elif isinstance(value, dict):
            if not isinstance(current[field], dict):
                current[field] = value
            else:
                """
                current = {
                    "blood_pressure": {"systolic": 130, "diastolic": 85, "unit": "mmHg"},
                    "name": "张三"
                }
                extracted = {
                    "blood_pressure": {"systolic": 125}
                }
                """
                current[field] = merge_profile(current[field], value)
        else:
            current[field] = value
    return current

class ProfileManager:
    async def load_profile(self, db: AsyncSession, user_id: str) -> dict:
        result = await db.execute(select(UserProfile).where(UserProfile.user_id==user_id))
        profile = result.scalar_one_or_none()
        if not profile:
            return {}
        return {
            "basic_info": profile.basic_info or {},
            "health_status": profile.health_status or {},
            "lifestyle": profile.lifestyle or {},
            "health_goals": profile.health_goals or {},
            "diet_preferences": profile.diet_preferences or {}
        }

    async def update_profile(self, db: AsyncSession, user_id: str, extracted: dict) -> bool:
        result = await db.execute(select(UserProfile).where(UserProfile.user_id==user_id))
        profile = result.scalar_one_or_none()
        if not profile:
            profile = UserProfile(user_id=user_id)
            db.add(profile)
            await db.flush()

        updated = False
        for section, fields in extracted.items():
            if section == "basic_info":
                profile.basic_info = merge_profile(copy.deepcopy(profile.basic_info or {}), fields)
                updated = True
            elif section == "health_status":
                profile.health_status = merge_profile(copy.deepcopy(profile.health_status or {}), fields)
                updated = True
            elif section == "lifestyle":
                profile.lifestyle = merge_profile(copy.deepcopy(profile.lifestyle or {}), fields)
                updated = True
            elif section == "health_goals":
                profile.health_goals = merge_profile({"items": list(profile.health_goals or [])}, {"items": fields})["items"]
                updated = True
            elif section == "diet_preferences":
                profile.diet_preferences = merge_profile(copy.deepcopy(profile.diet_preferences or {}), fields)
                updated = True
        if not updated:
            return False
        profile.version = (profile.version or 0) + 1
        await db.commit()
        return True

profile_manager = ProfileManager()