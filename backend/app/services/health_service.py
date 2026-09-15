import csv
import io
import json
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

from fastapi import UploadFile
from sqlalchemy import select, delete, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import utc_now_naive
from app.models.health import HealthRecord

VALID_DATA_TYPES = {"steps", "sleep", "heart_rate", "weight"}

@dataclass
class ImportResult:
    imported: int = 0
    failed: int = 0
    errors: list[str] = field(default_factory=list)

class HealthService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_health_data(
        self,
        user_id: str,
        data_type: str|None = None,
        start_date: str|None = None,
        end_date: str|None = None
    ) -> dict[str, Any]:
        """Get health records grouped by data type"""
        types = self._resolve_type(data_type)
        records: dict[str, list[dict[str, Any]]] = {kind: [] for kind in VALID_DATA_TYPES}

        stmt = (
            select(HealthRecord)
            .where(HealthRecord.user_id == user_id)
            .where(HealthRecord.date_type.in_(types))
            .order_by(HealthRecord.record_date.asc(), HealthRecord.created_at.asc())
        )
        if start_date:
            stmt = stmt.where(HealthRecord.record_date >= self._parse_date(start_date))
        if end_date:
            stmt = stmt.where(HealthRecord.record_date <= self._parse_date(end_date))

        result = await self.db.execute(stmt)
        for record in result.scalars().all():
            payload = dict(record.data or {})
            payload["id"] = record.id
            payload["date"] = record.record_date.isoformat()
            records.setdefault(record.date_type, []).append(payload)

        return records

    async def import_data(
        self,
        user_id: str,
        file: UploadFile,
        file_format: str,
        data_type: str
    ) -> ImportResult:
        """Import health records from a CSV or JSON upload"""
        content = await file.read()
        if file_format == "csv":
            rows = self._read_csv(content)
        elif file_format == "json":
            rows = self._read_json(content)
        else:
            return ImportResult(failed=1, errors=[f"Unsupported file format: {file_format}"])

        result = ImportResult()
        fallback_type = None if data_type == "all" else data_type

        for index, row in enumerate(rows, start=1):
            try:
                kind = self._normalize_data_type(str(row.get("data_type") or row.get("type") or fallback_type or ""))
                if kind not in VALID_DATA_TYPES:
                    raise ValueError(f"Unsupported data type: {kind or 'empty'}")

                record_date = self._parse_date(str(row.get("date") or row.get("record_date") or ""))
                payload = self._normalize_payload(kind, row)
                self.db.add(HealthRecord(
                    user_id=user_id,
                    date_type=kind,
                    record_date=record_date,
                    data=payload
                ))
                result.imported += 1
            except Exception as exc:
                result.failed += 1
                result.errors.append(f"Row {index}: {str(exc)}")

        if result.imported:
            await self.db.commit()
        return result

    async def delete_records(
        self,
        user_id: str,
        record_ids: list[str] | None = None,
        start_date: str | None = None,
        end_date: str | None = None
    ):
        """Delete records that belong to the current user"""
        stmt = delete(HealthRecord).where(HealthRecord.user_id == user_id)

        if record_ids:
            stmt = stmt.where(HealthRecord.id.in_(record_ids))
        if start_date:
            stmt = stmt.where(HealthRecord.record_date >= self._parse_date(start_date))
        if end_date:
            stmt = stmt.where(HealthRecord.record_date <= self._parse_date(end_date))

        result = await self.db.execute(stmt)
        await self.db.commit()
        return int(result.rowcount or 0)

    async def get_stats(
        self,
        user_id: str,
        date_type: str,
        period: str = "30d"
    ) -> dict[str, Any]:
        """Get simple statistics for one health data type"""
        if date_type not in VALID_DATA_TYPES:
            raise ValueError(f"Unsupported data type: {date_type}")

        days = self.period_to_days(period)
        start_data = (utc_now_naive() - timedelta(days=days)).date()
        stmt = (
            select(HealthRecord)
            .where(HealthRecord.user_id == user_id)
            .where(HealthRecord.date_type == date_type)
            .where(HealthRecord.record_date >= start_data)
        )
        result = await self.db.execute(stmt)
        values = [
            self._stat_value(date_type, record.data or {})
            for record in result.scalars().all()
        ]
        values = [value for value in values if value is not None]

        return {
            "data_type": date_type,
            "period": period,
            "count": len(values),
            "total": round(sum(values), 2) if values else None,
            "average": round(sum(values) / len(values), 2) if values else None,
            "max": max(values) if values else None,
            "trend": "stable"
        }

    async def get_summary_stats(self, user_id: str,) -> dict[str, Any]:
        """Get summary statistics across all health record types"""
        count_stmt = select(func.count()).select_from(HealthRecord).where(HealthRecord.user_id == user_id)
        count = (await self.db.execute(count_stmt)).scalar_one()

        range_stmt = select(func.min(HealthRecord.record_date), func.max(HealthRecord.record_date)).where(
            HealthRecord.user_id == user_id
        )
        date_start, date_end = (await self.db.execute(range_stmt)).one()

        type_stmt = select(HealthRecord.date_type).where(HealthRecord.user_id == user_id).distinct()
        data_types = [row[0] for row in (await self.db.execute(type_stmt)).all()]

        return {
            "total_records": count,
            "date_range": {
                "start": date_start.isoformat() if date_start else None,
                "end": date_end.isoformat() if date_end else None
            },
            "data_type": data_types
        }

    async def get_agent_context(self, user_id: str, days: int = 30) -> dict[str, Any]:
        """Buidl a compact health-data context for Agent personalization"""
        period = f"{days}d"
        end = utc_now_naive().date()
        start = end - timedelta(days=days)
        records = await self.get_health_data(
            user_id=user_id,
            start_date=start.isoformat(),
            end_date=end.isoformat()
        )

        stats: dict[str, Any] = {}
        for data_type in sorted(VALID_DATA_TYPES):
            stats[data_type] = await self.get_stats(user_id, data_type, period=period)

        latest_records = {
            data_type: values[-5:]
            for data_type, values in records.items()
            if values
        }

        return {
            "period_days": days,
            "stats": stats,
            "latest_records": latest_records,
            "insights": self._build_agent_insights(stats)
        }

    def _read_csv(self, content: bytes) -> list[dict[str, Any]]:
        text = content.decode("utf-8-sig")
        return [dict(row) for row in csv.DictReader(io.StringIO(text))]

    def _read_json(self, content: bytes) -> list[dict[str, Any]]:
        data = json.loads(content.decode("utf-8"))
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and isinstance(data.get("records"), list):
            return data["records"]
        if isinstance(data, dict):
            return [data]
        raise ValueError("JSON must be an object, a list, or {'records': [...]}")

    def _resolve_type(self, data_type: str | None) -> list[str]:
        if not data_type or data_type == "all":
            return sorted(VALID_DATA_TYPES)
        kind = self._normalize_data_type(data_type)
        if kind not in VALID_DATA_TYPES:
            raise ValueError(f"Unsupported data type: {data_type}")
        return [kind]

    def _normalize_data_type(self, data_type: str) -> str:
        return data_type.strip().replace("-", "_")

    def _parse_date(self, value: str) -> date:
        if not value:
            raise ValueError("date is required")
        return datetime.strptime(value[:10], "%Y-%m-%d").date()

    def _normalize_payload(self, data_type: str, row: dict[str, Any]) -> dict[str, Any]:
        payload: dict[str, Any] = {"date": self._parse_date(str(row.get("date") or row.get("record_date"))).isoformat()}
        if data_type == "steps":
            payload["steps"] = self._to_int(row.get("steps"))
            payload["distance"] = self._to_float(row.get("distance"), required=False)
            payload["calories"] = self._to_int(row.get("calories"), required=False)
        elif data_type == "sleep":
            payload["duration"] = self._to_int(row.get("duration"))
            payload["deep_sleep"] = self._to_float(row.get("deep_sleep") or row.get("deepSleep"), required=False)
            payload["light_sleep"] = self._to_float(row.get("light_sleep") or row.get("lightSleep"), required=False)
            payload["quality"] = row.get("quality") or None
        elif data_type == "heart_rate":
            payload["resting"] = self._to_int(row.get("resting"))
            payload["max"] = self._to_int(row.get("max"), required=False)
            payload["avg"] = self._to_int(row.get("avg"), required=False)
        elif data_type == "weight":
            payload["weight"] = self._to_float(row.get("weight"))
        return {key: value for key, value in payload.items() if value is not None}

    def _to_int(self, value: Any, *, required: bool = True) -> int | None:
        if value in (None, ""):
            if required:
                raise ValueError("required integer field is empty")
            return None
        return int(float(value))

    def _to_float(self, value: Any, *, required: bool = True) -> float | None:
        if value in (None, ""):
            if required:
                raise ValueError("required numeric field is empty")
            return None
        return float(value)

    def period_to_days(self, period: str) -> int:
        if period.endswith("d"):
            return int(period[:-1])
        if period.endswith("y"):
            return int(period[:-1]) * 365
        return 30

    def _stat_value(self, data_type: str, payload: dict[str, Any]) -> float | None:
        key = {
            "steps": "steps",
            "sleep": "duration",
            "heart_rate": "resting",
            "weight": "weight",
        }[data_type]
        value = payload.get(key)
        return float(value) if value is not None else None

    def _build_agent_insights(self, stats: dict[str, Any]) -> list[str]:
        insights: list[str] = []

        steps_avg = stats.get("steps", {}).get("average")
        if steps_avg is not None:
            if steps_avg < 5000:
                insights.append("最近步数均值偏低，运动建议应从低强度、可坚持的日常活动开始。")
            elif steps_avg >= 8000:
                insights.append("最近步数均值较好，可在恢复充分的前提下逐步提升训练质量。")

        sleep_avg = stats.get("sleep", {}).get("average")
        if sleep_avg is not None:
            if sleep_avg < 6:
                insights.append("最近睡眠时长偏短，建议优先关注作息稳定和睡眠恢复。")
            elif sleep_avg >= 7:
                insights.append("最近睡眠时长处于较理想区间，可结合精神状态继续观察。")

        resting_hr_avg = stats.get("heart_rate", {}).get("average")
        if resting_hr_avg is not None:
            if resting_hr_avg >= 90:
                insights.append("最近静息心率均值偏高，运动建议需要更保守，并提醒必要时咨询医生。")
            elif resting_hr_avg < 60:
                insights.append("最近静息心率均值较低，如伴随不适应建议就医评估。")

        return insights
