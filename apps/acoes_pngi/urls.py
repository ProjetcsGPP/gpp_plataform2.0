from django.urls import path, include
from rest_framework.routers import DefaultRouter

app_name = "acoes_pngi"

router = DefaultRouter()
# router.register(r"acoes", AcaoViewSet, basename="acao")  # implementar na fase de domínio

urlpatterns = [
    path("", include(router.urls)),
]
