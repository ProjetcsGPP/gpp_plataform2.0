import os

from celery import Celery
from django.conf import settings

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")

app = Celery("gpp_plataform")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks(
    packages=getattr(settings, "GPP_CELERY_TASK_PACKAGES", None)
)
