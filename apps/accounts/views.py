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
FIX: except Exception substituído por captura específica (DatabaseError/IntegrityError/OperationalError)
     ValidationError e PermissionDenied propagam normalmente para respostas 400/403 corretos
POLICY-EXPANSION: AplicacaoViewSet.get_queryset() diferencia usuário privilegiado de comum;
                  filtro hardcoded isshowinportal removido — lógica delegada aos flags + frontend.
POLICY-EXPANSION: UserProfileViewSet.partial_update() migrado para UserProfilePolicy.
FASE-0: JWT removido — LoginView, LogoutView e SwitchAppView baseadas em sessão Django.
ARCH-01: Endpoint de aplicacoes separado em dois:
         - AplicacaoPublicaViewSet → GET /api/accounts/auth/aplicacoes/ (AllowAny)
           Usado pelo seletor de login; expõe apenas apps ativas sem flags internos.
         - AplicacaoViewSet → GET /api/accounts/aplicacoes/ (IsAuthenticated)
           Pós-login; PORTAL_ADMIN vê todas, usuário comum vê só suas apps via UserRole.
FIX-TESTS: pagination_class = None nos dois AplicacaoViewSets para evitar
           resp.data paginado (dict) nos testes — retorna lista plana diretamente.
FIX-THROTTLE: throttle_classes = [] em AplicacaoPublicaViewSet — endpoint público
              não deve ser limitado por AnonRateThrottle; evita 429 nos testes.
"""
import logging
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.db import DatabaseError, IntegrityError, OperationalError, transaction
from django.middleware.csrf import rotate_token
from django.utils import timezone as dj_timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import APIException, PermissionDenied, ValidationError as DRFValidationError
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView

from common.mixins import AuditableMixin, SecureQuerysetMixin
from common.permissions import CanCreateUser, CanEditUser, HasRolePermission, IsPortalAdmin

from .models import AccountsSession, Aplicacao, Role, UserProfile, UserRole
from .serializers import (
    AplicacaoPublicaSerializer,
    AplicacaoSerializer,
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
from .utils import get_client_ip

security_logger = logging.getLogger("gpp.security")


# ─── Auth Views (Sessão) ──────────────────────────────────────────────────────

class LoginView(APIView):
    """
    POST /api/accounts/login/
    Realiza autenticação via sessão (cookie HttpOnly).

    Payload: { "username": "...", "password": "...", "app_context": "PORTAL" }
    """
    permission_classes = [AllowAny]
    throttle_scope = "login"

    def post(self, request):
        username    = request.data.get("username")
        password    = request.data.get("password")
        app_context = request.data.get("app_context")

        if not username or not password or not app_context:
            return Response(
                {"detail": "Credenciais ou app_context não informados.",
                 "code": "invalid_request"},
                status=status.HTTP_400_BAD_REQUEST
            )

        user = authenticate(request, username=username, password=password)

        if not user:
            return Response(
                {"detail": "Credenciais inválidas.", "code": "invalid_credentials"},
                status=status.HTTP_401_UNAUTHORIZED
            )

        app = Aplicacao.objects.filter(
            codigointerno=app_context,
            isappbloqueada=False
        ).first()

        if not app:
            return Response(
                {"detail": "Aplicação inválida ou bloqueada.",
                 "code": "invalid_app"},
                status=status.HTTP_403_FORBIDDEN
            )

        if app_context == "PORTAL":
            has_access = user.is_superuser or UserRole.objects.filter(
                user=user,
                role__codigoperfil="PORTAL_ADMIN"
            ).exists()
            deny_reason = "not_portal_admin"
            deny_detail = "Acesso ao Portal restrito a administradores."
        else:
            has_access = UserRole.objects.filter(
                user=user,
                aplicacao=app
            ).exists()
            deny_reason = "no_role"
            deny_detail = "Usuário sem acesso à aplicação informada."

        if not has_access:
            security_logger.warning(
                "LOGIN_DENIED user_id=%s app_context=%s reason=%s",
                user.id, app_context, deny_reason
            )
            return Response(
                {"detail": deny_detail, "code": "forbidden"},
                status=status.HTTP_403_FORBIDDEN
            )

        login(request, user)
        request.session.cycle_key()
        rotate_token(request)
        request.session["app_context"] = app_context

        session_obj = AccountsSession.objects.create(
            user=user,
            session_key=request.session.session_key,
            app_context=app_context,
            expires_at=dj_timezone.now() + timedelta(
                seconds=settings.SESSION_COOKIE_AGE
            ),
            ip_address=get_client_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT", ""),
            revoked=False
        )

        security_logger.info(
            "LOGIN_SUCCESS user_id=%s username=%s app_context=%s session_key=%s",
            user.id, user.username, app_context, session_obj.session_key
        )

        return Response({"detail": "Login realizado com sucesso"})


class LogoutView(APIView):
    """
    POST /api/accounts/logout/
    Encerra a sessão atual e revoga no banco.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        session_key = request.session.session_key

        AccountsSession.objects.filter(
            session_key=session_key,
            revoked=False
        ).update(
            revoked=True,
            revoked_at=dj_timezone.now()
        )

        security_logger.info(
            "LOGOUT user_id=%s session_key=%s",
            request.user.id, session_key
        )

        logout(request)
        return Response({"detail": "Logout realizado"})


class SwitchAppView(APIView):
    """
    POST /api/accounts/switch-app/
    Troca o contexto de aplicação mantendo a mesma sessão autenticada.
    """
    permission_classes = [IsAuthenticated]
    throttle_scope = "login"

    def post(self, request):
        new_app = request.data.get("app_context")

        if not new_app:
            return Response(
                {"detail": "app_context não informado.", "code": "invalid_request"},
                status=status.HTTP_400_BAD_REQUEST
            )

        user = request.user

        app = Aplicacao.objects.filter(
            codigointerno=new_app,
            isappbloqueada=False
        ).first()

        if not app:
            security_logger.warning(
                "SWITCH_APP_DENIED user_id=%s to_app=%s reason=invalid_app",
                user.id, new_app
            )
            return Response(
                {"detail": "Aplicação inválida ou bloqueada.", "code": "invalid_app"},
                status=status.HTTP_403_FORBIDDEN
            )

        if new_app == "PORTAL":
            has_access = user.is_superuser or UserRole.objects.filter(
                user=user,
                role__codigoperfil="PORTAL_ADMIN"
            ).exists()
        else:
            has_access = UserRole.objects.filter(
                user=user,
                aplicacao=app
            ).exists()

        if not has_access:
            security_logger.warning(
                "SWITCH_APP_DENIED user_id=%s to_app=%s reason=no_access",
                user.id, new_app
            )
            return Response(
                {"detail": "Usuário sem acesso à aplicação.", "code": "forbidden"},
                status=status.HTTP_403_FORBIDDEN
            )

        old_app = request.session.get("app_context")
        session_key = request.session.session_key

        AccountsSession.objects.filter(
            session_key=session_key,
            revoked=False
        ).update(
            revoked=True,
            revoked_at=dj_timezone.now()
        )

        request.session["app_context"] = new_app
        request.session.save()

        AccountsSession.objects.create(
            user=user,
            session_key=session_key,
            app_context=new_app,
            expires_at=dj_timezone.now() + timedelta(
                seconds=settings.SESSION_COOKIE_AGE
            ),
            ip_address=get_client_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT", ""),
            revoked=False
        )

        security_logger.info(
            "SWITCH_APP user_id=%s from_app=%s to_app=%s session_key=%s",
            user.id, old_app, new_app, session_key
        )

        return Response({"detail": "Contexto alterado com sucesso"})


# ─── Me View ──────────────────────────────────────────────────────────────────

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


# ─── User Create View (GAP-01) ─────────────────────────────────────────────────

class UserCreateView(APIView):
    """
    POST /api/accounts/users/
    Cria atomicamente um auth.User e seu UserProfile.
    """
    permission_classes = [IsAuthenticated, CanCreateUser]

    def post(self, request):
        serializer = UserCreateSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)

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
        except (DRFValidationError, PermissionDenied):
            raise
        except (DatabaseError, IntegrityError, OperationalError) as exc:
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


# ─── User Create With Role View (FASE 6) ──────────────────────────────────────

class UserCreateWithRoleView(APIView):
    """
    POST /api/accounts/users/create-with-role/
    Cria atomicamente auth.User + UserProfile + UserRole + sync de permissões.
    """
    permission_classes = [IsAuthenticated, CanCreateUser]

    def post(self, request):
        serializer = UserCreateWithRoleSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)

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
        except (DRFValidationError, PermissionDenied):
            raise
        except (DatabaseError, IntegrityError, OperationalError) as exc:
            security_logger.exception(
                "USER_CREATE_WITH_ROLE_ERROR admin_id=%s",
                request.user.id,
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


# ─── Aplicacao Publica ViewSet (ARCH-01) ───────────────────────────────────────

class AplicacaoPublicaViewSet(viewsets.ReadOnlyModelViewSet):
    """
    GET /api/accounts/auth/aplicacoes/
    GET /api/accounts/auth/aplicacoes/{codigointerno}/

    Endpoint PÚBLICO — sem autenticação necessária.
    Usado pelo frontend para popular o seletor de app_context na tela de login.

    Retorna apenas apps ativas (não bloqueadas e prontas para produção).
    Expõe somente codigointerno e nomeaplicacao — sem vazar flags internos.

    R-01: ReadOnly — POST/PUT/PATCH/DELETE retornam 405.
    R-02: Filtro fixo: isappbloqueada=False AND isappproductionready=True.
    R-03: pagination_class = None — retorna lista plana sem envelope de paginação.
    R-04: throttle_classes = [] — endpoint público de leitura; sem rate limit.
    """
    serializer_class = AplicacaoPublicaSerializer
    permission_classes = [AllowAny]
    throttle_classes = []  # sem rate limit — endpoint público de lookup
    pagination_class = None
    lookup_field = "codigointerno"

    def get_queryset(self):
        return Aplicacao.objects.filter(
            isappbloqueada=False,
            isappproductionready=True,
        ).order_by("nomeaplicacao")


# ─── Aplicacao ViewSet (GAP-02 / ARCH-01) ─────────────────────────────────────

class AplicacaoViewSet(viewsets.ReadOnlyModelViewSet):
    """
    GET /api/accounts/aplicacoes/
    GET /api/accounts/aplicacoes/{idaplicacao}/

    Endpoint AUTENTICADO — pós-login.
    Retorna as aplicações visíveis ao usuário conforme seu perfil:
      - PORTAL_ADMIN / SuperUser: todas as apps sem restrição.
      - Usuário comum: apenas apps onde possui UserRole,
        filtradas por isappbloqueada=False e isappproductionready=True.

    R-01: ReadOnly — POST/PUT/PATCH/DELETE retornam 405.
    R-02: Ordenação alfabética por nomeaplicacao.
    R-03: pagination_class = None — retorna lista plana sem envelope de paginação.
    """
    serializer_class = AplicacaoSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None

    def get_queryset(self):
        user = self.request.user
        is_privileged = (
            getattr(self.request, "is_portal_admin", False)
            or user.is_superuser
        )
        if is_privileged:
            return Aplicacao.objects.all().order_by("nomeaplicacao")
        user_app_ids = UserRole.objects.filter(user=user).values_list(
            "aplicacao_id", flat=True
        )
        return Aplicacao.objects.filter(
            isappbloqueada=False,
            isappproductionready=True,
            idaplicacao__in=user_app_ids,
        ).order_by("nomeaplicacao")


# ─── CRUD ViewSets ─────────────────────────────────────────────────────────────

class UserProfileViewSet(SecureQuerysetMixin, AuditableMixin, viewsets.ModelViewSet):
    """
    APIs de UserProfile.
    """
    serializer_class = UserProfileSerializer
    permission_classes = [IsAuthenticated, HasRolePermission, CanEditUser]
    http_method_names = ["get", "patch", "head", "options"]

    scope_field = "orgao"
    scope_source = "orgao"

    def get_queryset(self):
        user = self.request.user
        if getattr(self.request, "is_portal_admin", False):
            return UserProfile.objects.all().select_related(
                "user", "status_usuario", "tipo_usuario"
            ).order_by('user__username')
        return UserProfile.objects.filter(user=user).select_related(
            "user", "status_usuario", "tipo_usuario"
        ).order_by('user__username')

    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        from apps.accounts.policies import UserProfilePolicy

        policy = UserProfilePolicy(request.user, instance)

        if not policy.can_edit_profile():
            security_logger.warning(
                "PROFILE_PATCH_DENIED user_id=%s target_user_id=%s",
                request.user.id, instance.user_id,
            )
            raise PermissionDenied("Você não tem permissão para editar este perfil.")

        if "classificacao_usuario" in request.data and not policy.can_change_classificacao():
            security_logger.warning(
                "PROFILE_PATCH_CLASSIFICACAO_DENIED user_id=%s target_user_id=%s",
                request.user.id, instance.user_id,
            )
            raise PermissionDenied("Apenas administradores podem alterar a classificação.")

        if "status_usuario" in request.data and not policy.can_change_status():
            security_logger.warning(
                "PROFILE_PATCH_STATUS_DENIED user_id=%s target_user_id=%s",
                request.user.id, instance.user_id,
            )
            raise PermissionDenied("Apenas administradores podem alterar o status do usuário.")

        return super().partial_update(request, *args, **kwargs)


class RoleViewSet(viewsets.ReadOnlyModelViewSet):
    """
    GET /api/accounts/roles/
    GET /api/accounts/roles/{id}/
    Acesso exclusivo a PORTAL_ADMIN.
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
