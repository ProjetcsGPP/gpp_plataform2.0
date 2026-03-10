from django.urls import path, include
from rest_framework.routers import DefaultRouter

app_name = "carga_org_lot"

router = DefaultRouter()
# router.register(r"lotes", LoteViewSet, basename="lote")  # implementar na fase de domínio

urlpatterns = [
    path("", include(router.urls)),
]
