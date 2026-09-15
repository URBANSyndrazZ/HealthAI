"""
Health data schema
"""
from pydantic import BaseModel, ConfigDict

# Base schemas
class StepsData(BaseModel):
    date: str
    steps: int
    distance: float|None = None
    calories: int|None = None

class SleepData(BaseModel):
    date: str
    duration: float
    deep_sleep: float|None = None
    light_sleep: float|None = None
    quality: str|None = None

class HeartRateData(BaseModel):
    date: str
    resting: int
    max: int|None=None
    avg: int|None=None

# Response schemas
class HealthProfileReponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: str
    records: dict # Contains steps, sleep, heart_rate data
    summary: dict|None = None

class HealthDataImportReponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    status: str  # completed, partial, failed
    imported_count: int
    failed_count: int
    errors: list[str]

class HealthStats(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    data_type: str
    period: str
    total: float|None=None
    average: float|None=None
    max: float|None=None
    min: float|None=None
    count: int
    trend: str|None = None  # up, down, stable

# Request schemas
class HealthDataImportRequest(BaseModel):
    format: str # csv, json
    data_type: str # steps, sleep, heart_rate, all

class HealthDataDeleteRequest(BaseModel):
    record_ids: list[str]|None = None
    start_date: str|None = None
    end_date: str|None = None

class HealthStateRequest(BaseModel):
    data_type: str
    period: str = "30d" # 7d, 30d, 90d, 1y