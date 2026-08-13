from celery import Celery
from kombu import Exchange, Queue

from app.core.config import get_settings
from app.observability import configure_celery_observability

settings = get_settings()

notification_exchange = Exchange("notifications", type="direct", durable=True)
file_exchange = Exchange("files", type="direct", durable=True)
export_exchange = Exchange("exports", type="direct", durable=True)
search_exchange = Exchange("search", type="direct", durable=True)
integration_exchange = Exchange("integrations", type="direct", durable=True)
dead_letter_exchange = Exchange("dead-letter", type="direct", durable=True)

celery_app = Celery(
    "forkroom",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.workers.tasks"],
)
configure_celery_observability(settings)
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
        Queue(
            "files.process",
            exchange=file_exchange,
            routing_key="files.process",
            durable=True,
            queue_arguments={
                "x-dead-letter-exchange": "dead-letter",
                "x-dead-letter-routing-key": "files.failed",
            },
        ),
        Queue(
            "files.failed",
            exchange=dead_letter_exchange,
            routing_key="files.failed",
            durable=True,
        ),
        Queue(
            "exports.generate",
            exchange=export_exchange,
            routing_key="exports.generate",
            durable=True,
            queue_arguments={
                "x-dead-letter-exchange": "dead-letter",
                "x-dead-letter-routing-key": "exports.failed",
            },
        ),
        Queue(
            "exports.failed",
            exchange=dead_letter_exchange,
            routing_key="exports.failed",
            durable=True,
        ),
        Queue(
            "search.index",
            exchange=search_exchange,
            routing_key="search.index",
            durable=True,
            queue_arguments={
                "x-dead-letter-exchange": "dead-letter",
                "x-dead-letter-routing-key": "search.failed",
            },
        ),
        Queue(
            "search.failed",
            exchange=dead_letter_exchange,
            routing_key="search.failed",
            durable=True,
        ),
        Queue(
            "integrations.events",
            exchange=integration_exchange,
            routing_key="integrations.events",
            durable=True,
            queue_arguments={
                "x-dead-letter-exchange": "dead-letter",
                "x-dead-letter-routing-key": "integrations.failed",
            },
        ),
        Queue(
            "integrations.failed",
            exchange=dead_letter_exchange,
            routing_key="integrations.failed",
            durable=True,
        ),
    ),
    task_routes={
        "forkroom.notifications.deliver": {
            "queue": "notifications.email",
            "routing_key": "notifications.email",
        },
        "forkroom.reminders.discover": {"queue": "scheduler"},
        "forkroom.notifications.recover": {"queue": "scheduler"},
        "forkroom.attachments.process": {
            "queue": "files.process",
            "routing_key": "files.process",
        },
        "forkroom.attachments.recover": {"queue": "scheduler"},
        "forkroom.exports.generate": {
            "queue": "exports.generate",
            "routing_key": "exports.generate",
        },
        "forkroom.exports.recover": {"queue": "scheduler"},
        "forkroom.search.index": {
            "queue": "search.index",
            "routing_key": "search.index",
        },
        "forkroom.search.refresh": {"queue": "scheduler"},
        "forkroom.integrations.dispatch": {
            "queue": "integrations.events",
            "routing_key": "integrations.events",
        },
        "forkroom.integrations.deliver": {
            "queue": "integrations.events",
            "routing_key": "integrations.events",
        },
        "forkroom.integrations.recover": {"queue": "scheduler"},
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
        "recover-pending-attachment-processing": {
            "task": "forkroom.attachments.recover",
            "schedule": 300.0,
        },
        "recover-incomplete-decision-exports": {
            "task": "forkroom.exports.recover",
            "schedule": 300.0,
        },
        "refresh-decision-search-index": {
            "task": "forkroom.search.refresh",
            "schedule": 60.0,
        },
        "recover-integration-events": {
            "task": "forkroom.integrations.recover",
            "schedule": 60.0,
        },
    },
)
