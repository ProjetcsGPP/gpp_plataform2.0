from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import FrontEndLogging

app_name = "core"

# Router principal — endpoints autenticados
core_router = DefaultRouter()

urlpatterns = [
    # Endpoints públicos de suporte ao fluxo de login
    path("core/", include(core_router.urls)),
    path("core/frontendlog/", FrontEndLogging.as_view(), name="frontend"),
]
