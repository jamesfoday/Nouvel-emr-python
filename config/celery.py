import os
from celery import Celery

# Point Celery at Django settings
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("nouvel")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

# Celery Beat schedule — send 24h/2h reminders every 5 minutes
app.conf.beat_schedule = {
    "send-due-reminders-every-5m": {
        "task": "apps.appointments.tasks.send_due_reminders",
        "schedule": 300.0,  # seconds
    },
}
