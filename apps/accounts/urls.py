from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    AplicacaoPublicaViewSet,
    AplicacaoViewSet,
    LoginView,
    LogoutView,
    MeView,
    RoleViewSet,
    UserCreateView,
    UserCreateWithRoleView,
    UserProfileViewSet,
    UserRoleViewSet,
    ResolveUserView,
    LogoutAppView,
)

app_name = "accounts"

# Routers existentes (OK)
router = DefaultRouter()
router.register(r"aplicacoes", AplicacaoViewSet)
router.register(r"profiles", UserProfileViewSet)
router.register(r"roles", RoleViewSet)
router.register(r"user-roles", UserRoleViewSet)

auth_router = DefaultRouter()
auth_router.register(r"aplicacoes", AplicacaoPublicaViewSet)

urlpatterns = [
    path("auth/", include(auth_router.urls)),
    path("auth/resolve-user/", ResolveUserView.as_view(), name="resolve-user"),

    path("", include(router.urls)),
    path("login/", LoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),  # Global
    
    # 🔥 LOGOUT POR APP SIMPLES (sem conflito DRF)
    path("logout/<str:app_slug>/", LogoutAppView.as_view(), name="logout_app"),
    
    path("me/", MeView.as_view(), name="me"),
    path("users/", UserCreateView.as_view(), name="user-create"),
    path("users/create-with-role/", UserCreateWithRoleView.as_view(), name="user-create-with-role"),
]
