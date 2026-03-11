from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import AcaoPNGIViewSet

app_name = "acoes_pngi"

router = DefaultRouter()
router.register(r"acoes", AcaoPNGIViewSet, basename="acao")

urlpatterns = [
    path("", include(router.urls)),
]
