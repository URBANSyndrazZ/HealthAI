from pydantic import BaseModel, Field


class BasicInfo(BaseModel):
    name: str | None = None
    gender: str | None = None
    age: int | None = Field(None, ge=1, le=120)
    height_cm: float | None = Field(None, gt=0, le=250)
    weight_kg: float | None = Field(None, gt=0, le=400)


class HealthStatus(BaseModel):
    chronic_conditions: list[str] = Field(default_factory=list)
    risk_notes: str | None = None


class ProfileUpdateRequest(BaseModel):
    basic_info: BasicInfo = Field(default_factory=BasicInfo)
    health_status: HealthStatus = Field(default_factory=HealthStatus)
    health_goals: list[str] = Field(default_factory=list)


class ProfileResponse(BaseModel):
    user_id: str
    basic_info: dict
    health_status: dict
    health_goals: list
    version: int
