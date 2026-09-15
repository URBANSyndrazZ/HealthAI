import uuid
from datetime import date, datetime

from sqlalchemy import String, ForeignKey, Date, JSON, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utc_now_naive
from app.models.database import Base


class HealthRecord(Base):
    __tablename__ = "health_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    date_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    record_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    source: Mapped[str] = mapped_column(String(64), default="import")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), default=utc_now_naive)