"""
GPP Plataform 2.0 — Accounts Views
FASE 6: APIs iniciais — profiles, roles, user-roles, me
GAP-01: adicionado UserCreateView
GAP-02: adicionado AplicacaoViewSet
GAP-03: RoleViewSet com filtro por aplicacao_id via query param
GAP-04: UserRoleSerializer.validate() garante unicidade e role correta
GAP-05: UserRoleViewSet.create() sincroniza permissões atomicamente
"""
import logging
from datetime import datetime, timezone

from django.db import transaction
from django.utils import timezone as dj_timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import APIException, PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from common.mixins import AuditableMixin, SecureQuerysetMixin
from common.permissions import HasRolePermission, IsPortalAdmin

from .models import AccountsSession, Aplicacao, Role, UserProfile, UserRole
from .serializers import (
    AplicacaoSerializer,
    GPPTokenObtainPairSerializer,
    RoleSerializer,
    UserCreateSerializer,
    UserProfileSerializer,
    UserRoleSerializer,
    MeSerializer,
)
from .services.permission_sync import sync_user_permissions_from_group

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


# ─── User Create View (GAP-01) ───────────────────────────────────────────────────

class UserCreateView(APIView):
    """
    POST /api/accounts/users/
    Cria atomicamente um auth.User e seu UserProfile.
    Acesso exclusivo: PORTAL_ADMIN.

    R-01: transaction.atomic() no serializer — rollback total em falha.
          Exceções genéricas (ex: DB error) são capturadas aqui e
          convertidas para APIException(500) para que o gpp_exception_handler
          as processe corretamente sem re-levantar no TestClient.
    R-02: idusuariocriacao preenchido com o admin autenticado.
    R-03: apenas PORTAL_ADMIN.
    R-07: não cria UserRole — responsabilidade da Fase 4/6.
    """
    permission_classes = [IsAuthenticated, IsPortalAdmin]

    def post(self, request):
        serializer = UserCreateSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        try:
            profile = serializer.save()
        except Exception as exc:
            security_logger.error(
                "USER_CREATE_ERROR admin_id=%s error=%s",
                request.user.id, str(exc),
            )
            raise APIException(
                detail="Erro interno ao criar usuário. Tente novamente."
            ) from exc

        security_logger.info(
            "USER_CREATED admin_id=%s new_user_id=%s username=%s",
            request.user.id, profile.user_id, profile.user.username,
        )
        return Response(
            UserCreateSerializer(profile, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


# ─── Aplicacao ViewSet (GAP-02) ───────────────────────────────────────────────────

class AplicacaoViewSet(viewsets.ReadOnlyModelViewSet):
    """
    GET /api/accounts/aplicacoes/
    GET /api/accounts/aplicacoes/{idaplicacao}/

    Lista e detalha aplicações elegíveis para associação de usuário.
    R-01: filtra isshowinportal=False — aplicações de portal nunca são retornadas.
    R-02: acesso exclusivo a PORTAL_ADMIN.
    R-03: ReadOnlyModelViewSet — POST/PUT/PATCH/DELETE retornam 405 automaticamente.
    R-04: get_queryset filtrado garante 404 para apps com isshowinportal=True.
    R-05: ordenação por nomeaplicacao alfabético.
    """
    serializer_class = AplicacaoSerializer
    permission_classes = [IsAuthenticated, IsPortalAdmin]

    def get_queryset(self):
        return Aplicacao.objects.filter(isshowinportal=False).order_by("nomeaplicacao")


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
    """
    GET /api/accounts/roles/
    GET /api/accounts/roles/{id}/

    Lista e detalha roles disponíveis. Acesso exclusivo a PORTAL_ADMIN.

    GAP-03 — Filtragem por aplicacao_id:
    R-01: sem query param retorna todas as roles (compatibilidade preservada).
    R-02: aplicacao_id inválido (não inteiro) retorna [] — nunca 500.
    R-03: aplicacao_id de app inexistente retorna [] — nunca 404.
    R-04: aplicacao_id de app sem roles retorna [].
    R-05: apenas PORTAL_ADMIN.
    R-06: group_id/group_name são allow_null no serializer — roles sem group não quebram.
    R-07: ordenação por nomeperfil.
    """
    serializer_class = RoleSerializer
    permission_classes = [IsAuthenticated, IsPortalAdmin]

    def get_queryset(self):
        qs = Role.objects.all().select_related("aplicacao", "group")
        aplicacao_id = self.request.query_params.get("aplicacao_id")
        if aplicacao_id is not None:
            try:
                aplicacao_id = int(aplicacao_id)
            except (ValueError, TypeError):
                # R-02: valor não inteiro → lista vazia, sem 500
                return Role.objects.none()
            qs = qs.filter(aplicacao_id=aplicacao_id)
        return qs.order_by("nomeperfil")


class UserRoleViewSet(AuditableMixin, viewsets.ModelViewSet):
    """
    Gerencia UserRoles. Apenas PORTAL_ADMIN.
    - POST: atribui role a usuário + sincroniza permissões atomicamente (GAP-05).
    - DELETE: remove role de usuário (revogação de permissões é Fase 5).

    R-03: a criação do UserRole e o sync de permissões são atômicos —
          se o sync falhar, o UserRole é revertido (rollback).
    R-06: DELETE não revoga permissões nesta fase — log WARNING registrado.
    R-07: apenas PORTAL_ADMIN.
    """
    serializer_class = UserRoleSerializer
    permission_classes = [IsAuthenticated, IsPortalAdmin]
    http_method_names = ["get", "post", "delete", "head", "options"]

    def get_queryset(self):
        return UserRole.objects.all().select_related(
            "user", "aplicacao", "role"
        )

    def perform_create(self, serializer):
        # UserRole não possui campos created_by/updated_by — sobrescreve
        # AuditableMixin para não repassar esses kwargs ao model.
        serializer.save()
        
    def create(self, request, *args, **kwargs):
        """
        POST /api/accounts/user-roles/

        GAP-04: validação de unicidade e role correta delegada ao serializer.
        GAP-05: sincronização de permissões dentro de transaction.atomic().
        R-03: se sync_user_permissions_from_group lançar exceção,
              o UserRole NÃO é persistido — rollback total.
        """
        security_logger.info(
            "USERROLE_ASSIGN admin_id=%s payload=%s",
            request.user.id, request.data,
        )
        with transaction.atomic():
            response = super().create(request, *args, **kwargs)

            # Recupera a instância recém-criada para executar o sync
            userrole_id = response.data.get("id")
            userrole = UserRole.objects.select_related(
                "user", "role__group"
            ).get(pk=userrole_id)

            added = sync_user_permissions_from_group(
                user=userrole.user,
                group=userrole.role.group,
            )
            security_logger.info(
                "USERROLE_PERM_SYNC user_id=%s role=%s permissions_added=%s",
                userrole.user_id,
                userrole.role.codigoperfil,
                added,
            )

        return response

    def destroy(self, request, *args, **kwargs):
        """
        DELETE /api/accounts/user-roles/{id}/

        R-06: permissões NÃO são revogadas nesta fase.
        Log WARNING registrado para rastreabilidade.
        """
        instance = self.get_object()
        security_logger.info(
            "USERROLE_REMOVE admin_id=%s userrole_id=%s user_id=%s",
            request.user.id, instance.id, instance.user_id,
        )
        security_logger.warning(
            "USERROLE_PERM_REVOKE_PENDING userrole_id=%s user_id=%s role=%s "
            "reason=fase5_not_implemented",
            instance.id, instance.user_id, instance.role.codigoperfil,
        )
        return super().destroy(request, *args, **kwargs)
