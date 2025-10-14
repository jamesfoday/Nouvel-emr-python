# config/celery.py
import os
from celery import Celery

# Use your real settings module by default
os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    os.getenv("DJANGO_SETTINGS_MODULE", "config.settings"),
)

app = Celery("nouvel")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

# Upstash TLS relax (dev-only) if needed
if str(app.conf.broker_url or "").startswith("rediss://"):
    app.conf.broker_transport_options = {"ssl": {"cert_reqs": "CERT_NONE"}}
if str(app.conf.result_backend or "").startswith("rediss://"):
    app.conf.redis_backend_use_ssl = {"cert_reqs": "CERT_NONE"}

app.conf.beat_schedule = {
    "send-due-reminders-every-5m": {
        "task": "apps.appointments.tasks.send_due_reminders",
        "schedule": 300.0,
    },
}

@app.task(bind=True)
def debug_task(self):
    print(f"Request: {self.request!r}")
