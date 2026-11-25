from celery import Celery

from vaalikone.core.config import get_settings

settings = get_settings()

app = Celery("vaalikone", broker=settings.REDIS_URL, backend=settings.REDIS_URL)
app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    worker_prefetch_multiplier=1,
)
