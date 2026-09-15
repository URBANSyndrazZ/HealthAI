import uuid
from datetime import datetime

from sqlalchemy import String, ForeignKey, JSON, INTEGER, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utc_now_naive
from app.models.database import Base


class UserProfile(Base):
    __tablename__ = "user_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), unique=True, nullable=False)
    basic_info: Mapped[dict] = mapped_column(JSON, default=dict)
    health_status: Mapped[dict] = mapped_column(JSON, default=dict)
    lifestyle: Mapped[dict] = mapped_column(JSON, default=dict)
    health_goals: Mapped[list] = mapped_column(JSON, default=list)
    diet_preferences: Mapped[dict] = mapped_column(JSON, default=dict)
    version: Mapped[int] = mapped_column(INTEGER, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), default=utc_now_naive)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), default=utc_now_naive, onupdate=utc_now_naive)