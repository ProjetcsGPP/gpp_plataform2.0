import os

from celery import Celery
from django.conf import settings

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")

app = Celery("gpp_plataform")
app.config_from_object("django.conf:settings", namespace="CELERY")
pacotes = getattr(settings, "GPP_CELERY_TASK_PACKAGES", None)
if pacotes is None:
    app.autodiscover_tasks()
elif pacotes:
    app.autodiscover_tasks(packages=pacotes)
# Tupla vazia é intencional no perfil de IAM/Portal/Ações: não importar as
# tarefas de todos os INSTALLED_APPS por fallback implícito do Celery.
