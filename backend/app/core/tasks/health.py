"""Health data processing tasks.

This module provides background tasks for:
- Importing health data from files
- Processing and validating health records
- Generating health reports
- Data aggregation and statistics
"""

import logging
import asyncio
from typing import Dict, Optional

from app.core.celery import celery_app
from app.core.cache import cache_manager
from app.core.time import utc_isoformat

logger = logging.getLogger(__name__)


def _run_async(coro):
    """Run an async cache/database helper from a sync Celery task."""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        return asyncio.run(coro)
    if loop.is_running():
        # Celery tasks are sync in this module; this branch is defensive.
        return loop.create_task(coro)
    return loop.run_until_complete(coro)


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def import_health_data(
    self,
    user_id: str,
    file_path: str,
    file_type: str,
    data_type: Optional[str] = None
) -> Dict:
    """Import health data from file in background.

    Args:
        user_id: User ID
        file_path: Path to the file
        file_type: File type (csv, json)
        data_type: Type of health data (steps, sleep, heart_rate, weight)

    Returns:
        Import result dict
    """
    try:
        logger.info(f"[import_health_data] Processing {file_path} for user {user_id}")

        # TODO: Implement actual import logic with HealthService
        # For now, return mock result
        result = {
            'success': True,
            'user_id': user_id,
            'file_path': file_path,
            'records_imported': 0,
            'records_failed': 0,
            'processing_time': 0.0,
            'completed_at': utc_isoformat(),
        }

        # Invalidate user cache
        try:
            cache_key = f"health:profile:{user_id}"
            _run_async(cache_manager.delete(cache_key))
        except Exception as e:
            logger.warning(f"Failed to invalidate cache: {e}")

        logger.info(f"[import_health_data] Completed for user {user_id}")
        return result

    except Exception as exc:
        logger.error(f"[import_health_data] Failed: {exc}")
        # Retry the task
        raise self.retry(exc=exc)


@celery_app.task(bind=True, max_retries=3, default_retry_delay=30)
def generate_health_report(
    self,
    user_id: str,
    start_date: str,
    end_date: str,
    report_type: str = "summary"
) -> Dict:
    """Generate health report in background.

    Args:
        user_id: User ID
        start_date: Start date (ISO format)
        end_date: End date (ISO format)
        report_type: Type of report (summary, detailed, trends)

    Returns:
        Report result dict
    """
    try:
        logger.info(f"[generate_health_report] Generating {report_type} report for user {user_id}")

        # TODO: Implement actual report generation
        # For now, return mock result
        result = {
            'success': True,
            'user_id': user_id,
            'report_type': report_type,
            'start_date': start_date,
            'end_date': end_date,
            'generated_at': utc_isoformat(),
            'download_url': None,  # Would be set if report is exported
            'summary': {
                'total_steps': 0,
                'avg_sleep_hours': 0.0,
                'avg_heart_rate': 0,
            }
        }

        logger.info(f"[generate_health_report] Completed for user {user_id}")
        return result

    except Exception as exc:
        logger.error(f"[generate_health_report] Failed: {exc}")
        raise self.retry(exc=exc)


@celery_app.task(bind=True, max_retries=2, default_retry_delay=30)
def aggregate_health_data(
    self,
    user_id: str,
    aggregation_type: str = "daily",
    date_range: Optional[int] = 30
) -> Dict:
    """Aggregate health data in background.

    Args:
        user_id: User ID
        aggregation_type: Type of aggregation (daily, weekly, monthly)
        date_range: Number of days to aggregate

    Returns:
        Aggregation result dict
    """
    try:
        logger.info(f"[aggregate_health_data] Aggregating {aggregation_type} data for user {user_id}")

        # TODO: Implement actual aggregation logic
        result = {
            'success': True,
            'user_id': user_id,
            'aggregation_type': aggregation_type,
            'date_range_days': date_range,
            'aggregated_at': utc_isoformat(),
            'data_points': 0,
        }

        logger.info(f"[aggregate_health_data] Completed for user {user_id}")
        return result

    except Exception as exc:
        logger.error(f"[aggregate_health_data] Failed: {exc}")
        raise self.retry(exc=exc)
