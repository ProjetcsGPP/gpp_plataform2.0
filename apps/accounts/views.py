"""
GPP Plataform 2.0 — Accounts Views
"""
import logging
from datetime import datetime, timezone

from django.utils import timezone as dj_timezone
from rest_framework import status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from common.mixins import AuditableMixin
from common.permissions import HasRolePermission, IsPortalAdmin

from .models import AccountsSession, Role, UserProfile, UserRole
from .serializers import (
    GPPTokenObtainPairSerializer,
    RoleSerializer,
    UserProfileSerializer,
    UserRoleSerializer,
)

security_logger = logging.getLogger("gpp.security")


# ─── Auth Views ───────────────────────────────────────────────────────────────────

class GPPTokenObtainPairView(TokenObtainPairView):
    """
    Login endpoint.
    Além de retornar o token, registra a sessão em AccountsSession
    para permitir revogação explícita (anti-replay).
    """
    serializer_class = GPPTokenObtainPairSerializer
    throttle_scope = "login"

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)

        if response.status_code == 200:
            # Registra sessão no banco para controle de revogação
            from rest_framework_simplejwt.tokens import AccessToken
            access_token = AccessToken(response.data["access"])
            jti = access_token.get("jti")
            user_id = access_token.get("user_id")
            exp = access_token.get("exp")

            if jti and user_id:
                AccountsSession.objects.create(
                    user_id=user_id,
                    jti=jti,
                    expires_at=datetime.fromtimestamp(exp, tz=timezone.utc),
                    ip_address=self._get_client_ip(request),
                    user_agent=request.META.get("HTTP_USER_AGENT", "")[:500],
                )

        return response

    @staticmethod
    def _get_client_ip(request):
        x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forwarded_for:
            return x_forwarded_for.split(",")[0].strip()
        return request.META.get("REMOTE_ADDR")


class TokenRevokeView(APIView):
    """
    Revoga o access token atual marcando a sessão como revogada.
    Também invalida o refresh token via blacklist.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        refresh_token = request.data.get("refresh")
        jti = getattr(request, "token_jti", None)  # injetado pelo JWTAuthenticationMiddleware

        # Revoga sessão no banco
        if jti:
            AccountsSession.objects.filter(jti=jti).update(
                revoked=True,
                revoked_at=dj_timezone.now(),
            )
            security_logger.warning(
                "TOKEN_REVOKED user_id=%s jti=%s",
                request.user.id, jti,
            )

        # Invalida refresh token via blacklist do simplejwt
        if refresh_token:
            try:
                token = RefreshToken(refresh_token)
                token.blacklist()
            except TokenError:
                pass  # já está na blacklist ou inválido

        return Response({"detail": "Sessão encerrada com sucesso."}, status=status.HTTP_200_OK)


# ─── CRUD ViewSets ──────────────────────────────────────────────────────────────────

class UserProfileViewSet(AuditableMixin, viewsets.ModelViewSet):
    """
    CRUD de UserProfile.
    Usuários comuns só vêem e editam o próprio perfil.
    PORTAL_ADMIN vê todos.
    """
    serializer_class = UserProfileSerializer
    permission_classes = [IsAuthenticated, HasRolePermission]

    def get_queryset(self):
        user = self.request.user
        if getattr(self.request, "is_portal_admin", False):
            return UserProfile.objects.all().select_related(
                "user", "status_usuario", "tipo_usuario"
            )
        return UserProfile.objects.filter(user=user).select_related(
            "user", "status_usuario", "tipo_usuario"
        )


class RoleViewSet(viewsets.ReadOnlyModelViewSet):
    """Lista roles. Escrita apenas via Admin."""
    queryset = Role.objects.all().select_related("aplicacao", "group")
    serializer_class = RoleSerializer
    permission_classes = [IsAuthenticated, IsPortalAdmin]


class UserRoleViewSet(viewsets.ModelViewSet):
    """Gerencia UserRoles. Apenas PORTAL_ADMIN."""
    serializer_class = UserRoleSerializer
    permission_classes = [IsAuthenticated, IsPortalAdmin]

    def get_queryset(self):
        return UserRole.objects.all().select_related(
            "user", "aplicacao", "role"
        )
