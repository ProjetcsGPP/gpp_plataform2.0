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
    #SwitchAppView,
)

app_name = "accounts"

# Router principal — endpoints autenticados
router = DefaultRouter()
router.register(r"aplicacoes", AplicacaoViewSet,      basename="aplicacao")
router.register(r"profiles",   UserProfileViewSet,    basename="userprofile")
router.register(r"roles",      RoleViewSet,           basename="role")
router.register(r"user-roles", UserRoleViewSet,       basename="userrole")

# Router de autenticação — endpoints públicos (AllowAny)
auth_router = DefaultRouter()
auth_router.register(r"aplicacoes", AplicacaoPublicaViewSet, basename="auth-aplicacao")

urlpatterns = [
    # Endpoints públicos de suporte ao fluxo de login
    path("auth/",  include(auth_router.urls)),
    path("auth/resolve-user/", ResolveUserView.as_view(), name="resolve-user"),

    # Endpoints autenticados
    path("", include(router.urls)),
    path("login/",                      LoginView.as_view(),             name="login"),
    path("logout/",                     LogoutView.as_view(),            name="logout"),
    #path("switch-app/",                SwitchAppView.as_view(),         name="switch-app"),
    
    path("logout/<str:app_slug>/", LogoutAppView.as_view(), name="logout_app"),
    
    path("me/",                         MeView.as_view(),                name="me"),
    path("users/",                      UserCreateView.as_view(),        name="user-create"),
    path("users/create-with-role/",     UserCreateWithRoleView.as_view(),name="user-create-with-role"),
]
