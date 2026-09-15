"""Celery tasks package for HealthAI.

This package contains all background task modules:
- health: Health data processing tasks
- agent: Agent processing tasks
- notification: Notification and reminder tasks
"""

from app.core.celery import celery_app

__all__ = ['celery_app']
