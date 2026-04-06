from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    AplicacaoPublicaViewSet,
    AplicacaoViewSet,
    LoginView,
    LogoutView,
    LogoutAppView,
    MeView,
    MePermissionView,
    RoleViewSet,
    UserCreateView,
    UserCreateWithRoleView,
    UserProfileViewSet,
    UserRoleViewSet,
    ResolveUserView,
)

app_name = "accounts"

# basename explícito obrigatório: nenhum desses ViewSets define
# `queryset` como atributo de classe (usam get_queryset() dinâmico),
# portanto o DRF não consegue inferir o basename automaticamente.
router = DefaultRouter()
router.register(r"aplicacoes", AplicacaoViewSet, basename="aplicacao")
router.register(r"profiles", UserProfileViewSet, basename="userprofile")
router.register(r"roles", RoleViewSet, basename="role")
router.register(r"user-roles", UserRoleViewSet, basename="userrole")

auth_router = DefaultRouter()
auth_router.register(r"aplicacoes", AplicacaoPublicaViewSet, basename="aplicacao-publica")

urlpatterns = [
    path("auth/", include(auth_router.urls)),
    path("auth/resolve-user/", ResolveUserView.as_view(), name="resolve-user"),

    path("", include(router.urls)),
    path("login/", LoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("logout/<str:app_slug>/", LogoutAppView.as_view(), name="logout_app"),

    path("me/", MeView.as_view(), name="me"),
    path("me/permissions/", MePermissionView.as_view(), name="me-permissions"),
    path("users/", UserCreateView.as_view(), name="user-create"),
    path("users/create-with-role/", UserCreateWithRoleView.as_view(), name="user-create-with-role"),
]
