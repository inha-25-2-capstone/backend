"""
Celery application configuration
"""
import os
from celery import Celery
from src.utils.logger import setup_logger

logger = setup_logger()

# Redis configuration from environment
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Create Celery app
celery_app = Celery(
    "politics_news_worker",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["src.workers.tasks"]  # Auto-discover tasks
)

# Celery configuration
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Seoul",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=None,  # No time limit (disabled for dev)
    task_soft_time_limit=None,  # No soft time limit (disabled for dev)
    task_acks_late=True,  # Acknowledge task after completion
    worker_prefetch_multiplier=1,  # Process one task at a time
    worker_max_tasks_per_child=50,  # Restart worker after 50 tasks
)

logger.info(f"Celery app initialized with broker: {REDIS_URL}")
