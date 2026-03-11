from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import CargaOrgLotViewSet

app_name = "carga_org_lot"

router = DefaultRouter()
router.register(r"cargas", CargaOrgLotViewSet, basename="carga")

urlpatterns = [
    path("", include(router.urls)),
]
