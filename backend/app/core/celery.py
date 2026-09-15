"""Celery configuration for HealthAI.

This module provides:
- Asynchronous task processing
- Background job scheduling
- Task result caching
- Distributed task queue
"""

import logging
import os
from typing import Any, Optional

from celery import Celery
from celery.signals import task_failure, task_success, task_retry

from app.config import settings

logger = logging.getLogger(__name__)

# Celery configuration
CELERY_BROKER_URL = getattr(settings, 'CELERY_BROKER_URL', 'redis://localhost:6379/1')
CELERY_RESULT_BACKEND = getattr(settings, 'CELERY_RESULT_BACKEND', 'redis://localhost:6379/2')

# Initialize Celery app
celery_app = Celery(
    'ai_health_manager',
    broker=CELERY_BROKER_URL,
    backend=CELERY_RESULT_BACKEND,
    include=[
        'app.core.tasks.health',
        'app.core.tasks.agent',
        'app.core.tasks.notification',
    ]
)

# Celery configuration
celery_app.conf.update(
    # Task execution
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='Asia/Shanghai',
    enable_utc=True,

    # Task execution settings
    task_track_started=True,
    task_time_limit=3600,  # 1 hour
    task_soft_time_limit=3000,  # 50 minutes

    # Worker settings
    worker_prefetch_multiplier=4,
    worker_max_tasks_per_child=1000,

    # Result settings
    result_expires=3600 * 24,  # 24 hours
    result_extended=True,

    # Retry settings
    task_default_retry_delay=60,  # 1 minute
    task_max_retries=3,

    # Queue settings
    task_default_queue='default',
    task_routes={
        'app.core.tasks.health.*': {'queue': 'health'},
        'app.core.tasks.agent.*': {'queue': 'agent'},
        'app.core.tasks.notification.*': {'queue': 'notification'},
    },
)


# ==================== Signal Handlers ====================

@task_success.connect
def task_success_handler(sender=None, result=None, **kwargs):
    """Handle task success."""
    logger.info(f"Task {sender.name} completed successfully")


@task_failure.connect
def task_failure_handler(sender=None, task_id=None, exception=None, **kwargs):
    """Handle task failure."""
    logger.error(f"Task {sender.name} failed: {exception}")


@task_retry.connect
def task_retry_handler(sender=None, request=None, **kwargs):
    """Handle task retry."""
    logger.warning(f"Task {sender.name} is being retried")


# ==================== Task Utilities ====================

def get_task_info(task_id: str) -> Optional[dict]:
    """Get task status and result.

    Args:
        task_id: Celery task ID

    Returns:
        Task information dict or None
    """
    from celery.result import AsyncResult

    result = AsyncResult(task_id, app=celery_app)

    return {
        'task_id': task_id,
        'status': result.status,
        'result': result.result if result.ready() else None,
        'date_done': result.date_done,
    }


def revoke_task(task_id: str, terminate: bool = False) -> bool:
    """Revoke a running task.

    Args:
        task_id: Celery task ID
        terminate: Whether to terminate the task forcefully

    Returns:
        True if task was revoked
    """
    try:
        celery_app.control.revoke(task_id, terminate=terminate)
        return True
    except Exception as e:
        logger.error(f"Failed to revoke task {task_id}: {e}")
        return False
