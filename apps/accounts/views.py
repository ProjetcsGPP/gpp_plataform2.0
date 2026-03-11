"""
GPP Plataform 2.0 — Accounts Views
FASE 6: APIs iniciais — profiles, roles, user-roles, me
"""
import logging
from datetime import datetime, timezone

from django.utils import timezone as dj_timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from common.mixins import AuditableMixin, SecureQuerysetMixin
from common.permissions import HasRolePermission, IsPortalAdmin

from .models import AccountsSession, Role, UserProfile, UserRole
from .serializers import (
    GPPTokenObtainPairSerializer,
    RoleSerializer,
    UserProfileSerializer,
    UserRoleSerializer,
    MeSerializer,
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
        jti = getattr(request, "token_jti", None)

        if jti:
            AccountsSession.objects.filter(jti=jti).update(
                revoked=True,
                revoked_at=dj_timezone.now(),
            )
            security_logger.warning(
                "TOKEN_REVOKED user_id=%s jti=%s",
                request.user.id, jti,
            )

        if refresh_token:
            try:
                token = RefreshToken(refresh_token)
                token.blacklist()
            except TokenError:
                pass

        return Response({"detail": "Sessão encerrada com sucesso."}, status=status.HTTP_200_OK)


# ─── Me View ─────────────────────────────────────────────────────────────────────

class MeView(APIView):
    """
    GET /api/accounts/me/
    Retorna dados do usuário autenticado: profile + roles + apps com acesso.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        try:
            profile = user.profile
        except UserProfile.DoesNotExist:
            profile = None

        user_roles = (
            UserRole.objects
            .filter(user=user)
            .select_related("role", "aplicacao")
        )

        data = MeSerializer({
            "user": user,
            "profile": profile,
            "user_roles": user_roles,
        }).data

        return Response(data)


# ─── CRUD ViewSets ──────────────────────────────────────────────────────────────────

class UserProfileViewSet(SecureQuerysetMixin, AuditableMixin, viewsets.ModelViewSet):
    """
    APIs de UserProfile.
    - PORTAL_ADMIN: vê e edita todos os profiles.
    - Usuário comum: vê e edita apenas o próprio profile (PATCH only).

    SecureQuerysetMixin garante proteção IDOR via campo 'orgao'.
    Para PORTAL_ADMIN o escopo é bypassado manualmente em get_queryset.
    """
    serializer_class = UserProfileSerializer
    permission_classes = [IsAuthenticated, HasRolePermission]
    http_method_names = ["get", "patch", "head", "options"]

    # SecureQuerysetMixin: campos de escopo
    scope_field = "orgao"
    scope_source = "orgao"

    def get_queryset(self):
        user = self.request.user
        # PORTAL_ADMIN vê todos sem restrição de escopo
        if getattr(self.request, "is_portal_admin", False):
            return UserProfile.objects.all().select_related(
                "user", "status_usuario", "tipo_usuario"
            )
        # Usuário comum: apenas o próprio profile
        return UserProfile.objects.filter(user=user).select_related(
            "user", "status_usuario", "tipo_usuario"
        )

    def partial_update(self, request, *args, **kwargs):
        """
        PATCH /api/accounts/profiles/{id}/
        Usuário comum só pode editar o próprio profile.
        PORTAL_ADMIN pode editar qualquer profile.
        """
        instance = self.get_object()
        if not getattr(request, "is_portal_admin", False):
            if instance.user != request.user:
                security_logger.warning(
                    "PROFILE_PATCH_DENIED user_id=%s target_user_id=%s",
                    request.user.id, instance.user_id,
                )
                raise PermissionDenied("Você só pode editar o próprio perfil.")
        return super().partial_update(request, *args, **kwargs)


class RoleViewSet(viewsets.ReadOnlyModelViewSet):
    """Lista roles. Apenas PORTAL_ADMIN."""
    queryset = Role.objects.all().select_related("aplicacao", "group")
    serializer_class = RoleSerializer
    permission_classes = [IsAuthenticated, IsPortalAdmin]


class UserRoleViewSet(AuditableMixin, viewsets.ModelViewSet):
    """
    Gerencia UserRoles. Apenas PORTAL_ADMIN.
    - POST: atribui role a usuário.
    - DELETE: remove role de usuário.
    """
    serializer_class = UserRoleSerializer
    permission_classes = [IsAuthenticated, IsPortalAdmin]
    http_method_names = ["get", "post", "delete", "head", "options"]

    def get_queryset(self):
        return UserRole.objects.all().select_related(
            "user", "aplicacao", "role"
        )

    def create(self, request, *args, **kwargs):
        security_logger.info(
            "USERROLE_ASSIGN admin_id=%s payload=%s",
            request.user.id, request.data,
        )
        return super().create(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        security_logger.info(
            "USERROLE_REMOVE admin_id=%s userrole_id=%s user_id=%s",
            request.user.id, instance.id, instance.user_id,
        )
        return super().destroy(request, *args, **kwargs)
