from celery import Celery
from kombu import Exchange, Queue

from app.core.config import get_settings

settings = get_settings()

notification_exchange = Exchange("notifications", type="direct", durable=True)
dead_letter_exchange = Exchange("dead-letter", type="direct", durable=True)

celery_app = Celery(
    "forkroom",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.workers.tasks"],
)
celery_app.conf.update(
    broker_connection_retry_on_startup=True,
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_default_queue="notifications.email",
    task_default_exchange="notifications",
    task_default_exchange_type="direct",
    task_default_routing_key="notifications.email",
    task_queues=(
        Queue(
            "notifications.email",
            exchange=notification_exchange,
            routing_key="notifications.email",
            durable=True,
            queue_arguments={
                "x-dead-letter-exchange": "dead-letter",
                "x-dead-letter-routing-key": "notifications.failed",
            },
        ),
        Queue(
            "notifications.failed",
            exchange=dead_letter_exchange,
            routing_key="notifications.failed",
            durable=True,
        ),
        Queue("scheduler", durable=True),
    ),
    task_routes={
        "forkroom.notifications.deliver": {
            "queue": "notifications.email",
            "routing_key": "notifications.email",
        },
        "forkroom.reminders.discover": {"queue": "scheduler"},
        "forkroom.notifications.recover": {"queue": "scheduler"},
    },
    beat_schedule={
        "discover-due-reminders": {
            "task": "forkroom.reminders.discover",
            "schedule": 60.0,
        },
        "recover-stale-notification-deliveries": {
            "task": "forkroom.notifications.recover",
            "schedule": 300.0,
        },
    },
)
