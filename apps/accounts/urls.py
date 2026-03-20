from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    AplicacaoViewSet,
    LoginView,
    LogoutView,
    MeView,
    RoleViewSet,
    SwitchAppView,
    UserCreateView,
    UserCreateWithRoleView,
    UserProfileViewSet,
    UserRoleViewSet,
)

app_name = "accounts"

router = DefaultRouter()
router.register(r"aplicacoes", AplicacaoViewSet, basename="aplicacao")
router.register(r"profiles",   UserProfileViewSet, basename="userprofile")
router.register(r"roles",      RoleViewSet, basename="role")
router.register(r"user-roles", UserRoleViewSet, basename="userrole")

urlpatterns = [
    path("", include(router.urls)),
    path("login/",              LoginView.as_view(),              name="login"),
    path("logout/",             LogoutView.as_view(),             name="logout"),
    path("switch-app/",         SwitchAppView.as_view(),          name="switch-app"),
    path("me/",                 MeView.as_view(),                 name="me"),
    path("users/",              UserCreateView.as_view(),         name="user-create"),
    path("users/create-with-role/", UserCreateWithRoleView.as_view(),
         name="user-create-with-role"),
]
