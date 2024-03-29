import logging
import os
import time

from celery import Celery

# Set the default Django settings module for the 'celery' program.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings.base")

app = Celery("reports")

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
# - namespace='CELERY' means all celery-related configuration keys
#   should have a `CELERY_` prefix.
app.config_from_object("django.conf:settings", namespace="CELERY")

# Load task modules from all registered Django apps.
app.autodiscover_tasks()

logger = logging.getLogger(__name__)


@app.task(bind=True)
def generate_zip_task(self, exam_id, user_id):
    from jsplatform.models import ExamReport

    report = ExamReport.objects.get(exam_id=exam_id)
    report.generate_zip_archive()
