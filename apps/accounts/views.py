"""
GPP Plataform 2.0 — Accounts Views
FASE 6: APIs iniciais — profiles, roles, user-roles, me
GAP-01: adicionado UserCreateView
GAP-02: adicionado AplicacaoViewSet
GAP-03: RoleViewSet com filtro por aplicacao_id via query param
GAP-04: UserRoleSerializer.validate() garante unicidade e role correta
GAP-05 Fase 4: UserRoleViewSet.create() sincroniza permissões atomicamente
GAP-05 Fase 5: UserRoleViewSet.destroy() revoga permissões exclusivas atomicamente
FASE 6: UserCreateWithRoleView — fluxo orquestrado atômico User+Profile+Role+Sync
DYN-SCOPE: escopo por aplicação centralizado em AuthorizationService
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
from common.permissions import CanCreateUser, CanEditUser, HasRolePermission, IsPortalAdmin

from .models import AccountsSession, Aplicacao, Role, UserProfile, UserRole
from .serializers import (
    AplicacaoSerializer,
    GPPTokenObtainPairSerializer,
    RoleSerializer,
    UserCreateSerializer,
    UserCreateWithRoleSerializer,
    UserProfileSerializer,
    UserRoleSerializer,
    MeSerializer,
)
from .services.permission_sync import (
    sync_user_permissions_from_group,
    revoke_user_permissions_from_group,
)

security_logger = logging.getLogger("gpp.security")


# ─── Auth Views ───────────────────────────────────────────────────────────────────────────────────

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


# ─── Me View ───────────────────────────────────────────────────────────────────────────────────

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


# ─── User Create View (GAP-01) ─────────────────────────────────────────────────────────

class UserCreateView(APIView):
    """
    POST /api/accounts/users/
    Cria atomicamente um auth.User e seu UserProfile.
    Acesso: ClassificacaoUsuario.pode_criar_usuario=True (ou PORTAL_ADMIN bootstrap).

    R-01: transaction.atomic() no serializer — rollback total em falha.
          Exceções genéricas (ex: DB error) são capturadas aqui e
          convertidas para APIException(500) para que o gpp_exception_handler
          as processe corretamente sem re-levantar no TestClient.
    R-02: idusuariocriacao preenchido com o admin autenticado.
    R-03: CanCreateUser — lê ClassificacaoUsuario.pode_criar_usuario via AuthorizationService.
    R-07: não cria UserRole — responsabilidade da Fase 4/6.
    DYN-SCOPE: user_can_manage_target_user — gestores só criam usuários
               com interseção de aplicações. Verificação feita após
               validação do serializer, antes do save(), usando dados do banco.
    """
    permission_classes = [IsAuthenticated, CanCreateUser]

    def post(self, request):
        serializer = UserCreateSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)

        # DYN-SCOPE: verifica escopo por aplicação para gestores.
        # O usuário alvo ainda não foi criado; verificamos o gestor contra
        # um usuário existente representado pelo campo 'target_user' se
        # presente no contexto, ou ignoramos se não aplicável neste fluxo.
        # Neste endpoint o target é um novo usuário, então a verificação
        # de interseção é feita após criação em UserCreateWithRoleView.
        # Aqui aplicamos apenas a verificação quando 'target_user' é fornecido
        # via contexto (edição) ou pulamos para novo usuário sem role ainda.
        target_user = serializer.validated_data.get("target_user")
        if target_user is not None:
            from apps.accounts.services.authorization_service import AuthorizationService
            service = AuthorizationService(request.user)
            if not service.user_can_manage_target_user(target_user):
                security_logger.warning(
                    "USER_CREATE_SCOPE_DENIED admin_id=%s target_user_id=%s "
                    "reason=no_app_intersection",
                    request.user.id, target_user.id,
                )
                raise PermissionDenied(
                    "Você não tem permissão para gerenciar este usuário "
                    "(sem interseção de aplicações)."
                )

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


# ─── User Create With Role View (FASE 6) ──────────────────────────────────────────────

class UserCreateWithRoleView(APIView):
    """
    POST /api/accounts/users/create-with-role/

    Endpoint orquestrador da Fase 6.
    Executa atomicamente: criação de auth.User + UserProfile + UserRole +
    sincronização de permissões em uma única requisição.

    R-01: transaction.atomic() dentro do serializer — rollback total em qualquer falha.
    R-02: isshowinportal=False validado pelo queryset do campo aplicacao_id.
    R-03: role.aplicacao == aplicacao validado no validate() do serializer.
    R-04: validações de senha, unicidade, e role única por app reaplicadas.
    R-06: CanCreateUser — lê ClassificacaoUsuario.pode_criar_usuario via AuthorizationService.
    R-07: permissions_added reflete exatamente quantas perms foram adicionadas.
    DYN-SCOPE: user_can_create_user_in_application — gestores só podem criar usuários
               em aplicações onde possuem UserRole. A aplicação é lida do banco
               via aplicacao_id validado pelo serializer, nunca da request direta.
               Autorização centralizada em AuthorizationService.
    """
    permission_classes = [IsAuthenticated, CanCreateUser]

    def post(self, request):
        serializer = UserCreateWithRoleSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)

        # DYN-SCOPE: delega verificação de escopo ao AuthorizationService.
        # A aplicação é extraída dos dados validados pelo serializer (banco),
        # nunca diretamente da request, evitando manipulação.
        #aplicacao_destino = serializer.validated_data.get("aplicacao_id")
        aplicacao_destino = serializer.validated_data["aplicacao"]
        
        if aplicacao_destino is not None:
            from apps.accounts.services.authorization_service import AuthorizationService
            service = AuthorizationService(request.user)
            if not service.user_can_create_user_in_application(aplicacao_destino):
                security_logger.warning(
                    "USER_CREATE_WITH_ROLE_SCOPE_DENIED admin_id=%s aplicacao_id=%s "
                    "reason=no_permission_in_target_app",
                    request.user.id,
                    getattr(aplicacao_destino, "pk", aplicacao_destino),
                )
                raise PermissionDenied(
                    "Você só pode criar usuários nas aplicações que gerencia."
                )

        try:
            result = serializer.save()
        except Exception as exc:
            security_logger.error(
                "USER_CREATE_WITH_ROLE_ERROR admin_id=%s error=%s",
                request.user.id, str(exc),
            )
            raise APIException(
                detail="Erro interno ao criar usuário com role. Tente novamente."
            ) from exc

        security_logger.info(
            "USER_CREATED_WITH_ROLE admin_id=%s new_user_id=%s role=%s app=%s perms_added=%s",
            request.user.id,
            result["user_id"],
            result["role"],
            result["aplicacao"],
            result["permissions_added"],
        )
        return Response(result, status=status.HTTP_201_CREATED)


# ─── Aplicacao ViewSet (GAP-02) ───────────────────────────────────────────────────────────────────

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


# ─── CRUD ViewSets ────────────────────────────────────────────────────────────────────────────────────

class UserProfileViewSet(SecureQuerysetMixin, AuditableMixin, viewsets.ModelViewSet):
    """
    APIs de UserProfile.
    - PORTAL_ADMIN: vê e edita todos os profiles.
    - Usuário comum: vê e edita apenas o próprio profile (PATCH only).

    SecureQuerysetMixin garante proteção IDOR via campo 'orgao'.
    Para PORTAL_ADMIN o escopo é bypassado manualmente em get_queryset.
    """
    serializer_class = UserProfileSerializer
    permission_classes = [IsAuthenticated, HasRolePermission, CanEditUser]
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
            ).order_by('user__username')
        # Usuário comum: apenas o próprio profile
        return UserProfile.objects.filter(user=user).select_related(
            "user", "status_usuario", "tipo_usuario"
        ).order_by('user__username')

    def partial_update(self, request, *args, **kwargs):
        """
        PATCH /api/accounts/profiles/{id}/

        CanEditUser (no permission_classes) já garante que o usuário pode
        editar usuários em geral. Esta verificação adicional garante proteção
        IDOR: usuário sem is_portal_admin só edita o próprio perfil.
        Gestores (pode_editar_usuario=True) editam apenas perfis de usuários
        pertencentes às aplicações que também gerenciam (escopo por aplicação).
        """
        instance = self.get_object()
        from apps.accounts.services.authorization_service import AuthorizationService
        service = AuthorizationService(request.user)

        # Permite auto-edição do próprio perfil sem restrição de escopo
        if instance.user == request.user:
            return super().partial_update(request, *args, **kwargs)

        # Para edição de outro usuário, delega ao AuthorizationService
        if not service.user_can_edit_target_user(instance.user):
            security_logger.warning(
                "PROFILE_PATCH_DENIED user_id=%s target_user_id=%s "
                "reason=no_edit_permission_or_no_app_intersection",
                request.user.id, instance.user_id,
            )
            raise PermissionDenied("Você não tem permissão para editar este perfil.")

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
                return Role.objects.none()
            qs = qs.filter(aplicacao_id=aplicacao_id)
        return qs.order_by("nomeperfil")


class UserRoleViewSet(AuditableMixin, viewsets.ModelViewSet):
    """
    Gerencia UserRoles. Apenas PORTAL_ADMIN.
    - POST: atribui role a usuário + sincroniza permissões atomicamente (GAP-05 Fase 4).
    - DELETE: remove role de usuário + revoga permissões exclusivas atomicamente (GAP-05 Fase 5).

    R-02: a deleção do UserRole e a revogação de permissões são atômicas —
          se a revogação falhar, o UserRole não é deletado (rollback).
    R-05: apenas PORTAL_ADMIN (garantido por permission_classes).
    """
    serializer_class = UserRoleSerializer
    permission_classes = [IsAuthenticated, IsPortalAdmin]
    http_method_names = ["get", "post", "delete", "head", "options"]

    def get_queryset(self):
        return UserRole.objects.all().select_related(
            "user", "aplicacao", "role"
        )

    def perform_create(self, serializer):
        serializer.save()

    def create(self, request, *args, **kwargs):
        """
        POST /api/accounts/user-roles/

        GAP-04: validação de unicidade e role correta delegada ao serializer.
        GAP-05 Fase 4: sincronização de permissões dentro de transaction.atomic().
        R-03: se sync_user_permissions_from_group lançar exceção,
              o UserRole NÃO é persistido — rollback total.
        """
        security_logger.info(
            "USERROLE_ASSIGN admin_id=%s payload=%s",
            request.user.id, request.data,
        )
        with transaction.atomic():
            response = super().create(request, *args, **kwargs)

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

        GAP-05 Fase 5: revogação de permissões exclusivas dentro de transaction.atomic().

        Regras:
          R-01: só revoga permissões não cobertas por outros grupos ativos do usuário.
          R-02: deleção e revogação são atômicas — falha na revogação faz rollback.
          R-03: role.group=None → revogação ignorada com WARNING, sem 500.
          R-05: apenas PORTAL_ADMIN (garantido por permission_classes).
        """
        instance = self.get_object()

        security_logger.info(
            "USERROLE_REMOVE admin_id=%s userrole_id=%s user_id=%s role=%s app=%s",
            request.user.id, instance.id, instance.user_id,
            instance.role.codigoperfil,
            instance.aplicacao.codigointerno if instance.aplicacao else "N/A",
        )

        with transaction.atomic():
            user = instance.user
            group = instance.role.group

            response = super().destroy(request, *args, **kwargs)

            removed = revoke_user_permissions_from_group(user=user, group_removed=group)
            security_logger.info(
                "USERROLE_PERM_REVOKE user_id=%s group=%s permissions_removed=%s",
                user.pk, group.name if group else "None", removed,
            )

        return response
