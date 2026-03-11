from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import AplicacaoViewSet, DashboardView

app_name = "portal"

router = DefaultRouter()
router.register(r"aplicacoes", AplicacaoViewSet, basename="aplicacao")

urlpatterns = [
    path("", include(router.urls)),
    path("dashboard/", DashboardView.as_view(), name="dashboard"),
]
