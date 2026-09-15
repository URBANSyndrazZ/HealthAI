from typing import Any

from fastapi import APIRouter, Query, Depends, HTTPException, status, File, Form, UploadFile
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_user
from app.models import User
from app.schemas.health import HealthProfileReponse, HealthDataImportReponse, HealthStats
from app.services.health_service import HealthService

router = APIRouter(prefix="/health", tags=["health"])

class DeleteRecordsRequest(BaseModel):
    record_ids: list[str] | None = None
    start_date: str | None = None
    end_date: str | None = None

@router.get("/profile", response_model=HealthProfileReponse)
async def get_health_profile(
    data_type: str | None = Query(None, description="Data type: steps, sleep, heart_rate or all"),
    start_date: str|None = Query(None, alias="startDate"),
    end_date: str|None = Query(None, alias="endDate"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> HealthProfileReponse:
    service = HealthService(db)
    try:
        data = await service.get_health_data(
            user_id=current_user.id,
            data_type=data_type,
            start_date=start_date,
            end_date=end_date
        )
        return HealthProfileReponse(
            user_id=current_user.id,
            records=data,
            summary=await service.get_summary_stats(user_id=current_user.id)
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

@router.post("/import", response_model=HealthDataImportReponse)
async def import_health_data(
    format: str = Form(..., description="File format: csv or json"),
    data_type: str | None = Form(None),
    data_type_alias: str | None = Form(None, alias="dataType"),
    file: UploadFile = File(..., description="Data file to import"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> HealthDataImportReponse:
    service = HealthService(db)
    data_kind = data_type or data_type_alias
    if not data_kind:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="data_type is required")

    result = await service.import_data(
        user_id=current_user.id,
        file=file,
        file_format=format,
        data_type=data_kind
    )
    import_status = "failed" if result.imported == 0 and result.failed else "completed"
    if result.imported and result.failed:
        import_status = "partial"
    return HealthDataImportReponse(
        status=import_status,
        imported_count=result.imported,
        failed_count=result.failed,
        errors=result.errors
    )

@router.delete("/records")
async def delete_health_records(
    payload: DeleteRecordsRequest | None = None,
    record_ids: list[str] | None = Query(None),
    start_date: str | None = Query(None, alias="startDate"),
    end_date: str | None = Query(None, alias="endDate"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> dict[str, Any]:
    service = HealthService(db)
    payload = payload or DeleteRecordsRequest()
    delete_count = await service.delete_records(
        user_id=current_user.id,
        record_ids=payload.record_ids or record_ids,
        start_date=payload.start_date or start_date,
        end_date=payload.end_date or end_date
    )
    return {
        "delete_count": delete_count,
        "messages": f"Successfully deleted {delete_count} records."
    }

@router.get("/stats", response_model=HealthStats)
async def get_health_stats(
    data_type: str = Query(..., description="Data type: steps, sleep, heart_rate or all"),
    period: str = Query("30d", description="Time period: 7d, 30d, 90d, 1y"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> HealthStats:
    service = HealthService(db)
    try:
        return HealthStats(**await service.get_stats(user_id=current_user.id, date_type=data_type, period=period))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
