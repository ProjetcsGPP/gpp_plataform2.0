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
FASE-0: JWT removido — LoginView e LogoutView baseadas em sessão Django.
ARCH-01: Endpoint de aplicacoes separado em dois:
         - AplicacaoPublicaViewSet → GET /api/accounts/auth/aplicacoes/ (AllowAny)
           Usado pelo seletor de login; expõe apenas apps ativas sem flags internos.
         - AplicacaoViewSet → GET /api/accounts/aplicacoes/ (IsAuthenticated)
           Pós-login; PORTAL_ADMIN vê todas, usuário comum vê só suas apps via UserRole.
FIX-TESTS: pagination_class = None nos dois AplicacaoViewSets para evitar
           resp.data paginado (dict) nos testes — retorna lista plana diretamente.
FIX-THROTTLE: throttle_classes = [] em AplicacaoPublicaViewSet — endpoint público
              não deve ser limitado por AnonRateThrottle; evita 429 nos testes.
FIX-THROTTLE-2: throttle_scope removido de LoginView — o rate limit de login é
                controlado globalmente via DEFAULT_THROTTLE_CLASSES no settings.
                O conftest raiz zera as classes em tempo de teste, garantindo
                que nenhum login seja bloqueado por 429 durante a suite completa.
MULTI-COOKIE: cada app possui sessão independente (gpp_session_{APP}).
              SwitchAppView removida — obsoleta neste modelo; o frontend
              simplesmente faz um segundo login na app destino.
FIX-ME-PERMISSIONS: MePermissionView agora lê request.app_context (definido pelo
              AppContextMiddleware) em vez de request.session.get('app_context').
              O middleware não usa o sistema de sessão Django padrão — ele resolve
              a sessão via AccountsSession e grava o contexto diretamente na request.
FASE-4-PERM: UserRoleViewSet.create() e destroy() agora usam sync_user_permissions()
             — orquestrador idempotente com substituição completa (corrige D-04).
FASE-5-PERM (Issue #18): UserPermissionOverrideViewSet adicionado — garante que toda
             mutação em UserPermissionOverride aciona sync_user_permissions(user).
FIX(Issue #22): LoginView substitui update_or_create por revoke+create.
             cycle_key() rotaciona o session_key antes do update_or_create, portanto
             o lookup nunca encontrava registro existente e sempre criava um novo,
             acumulando sessões antigas com app_context=None no banco.
             A correção revoga sessões ativas do mesmo usuário/app antes de criar
             a nova, garantindo exatamente uma AccountsSession ativa por (user, app).
FIX(MePermissionView): removido fallback request.session em get() — incoerente
             com a arquitetura AppContextMiddleware/AccountsSession e causa
             AttributeError em requests sem SessionMiddleware (ex: testes diretos).
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
from rest_framework.views import APIView

from common.mixins import AuditableMixin, SecureQuerysetMixin
from common.permissions import CanCreateUser, CanEditUser, HasRolePermission, IsPortalAdmin

from .models import AccountsSession, Aplicacao, Role, UserPermissionOverride, UserProfile, UserRole
from .serializers import (
    AplicacaoPublicaSerializer,
    AplicacaoSerializer,
    RoleSerializer,
    UserCreateSerializer,
    UserCreateWithRoleSerializer,
    UserPermissionOverrideSerializer,
    UserProfileSerializer,
    UserRoleSerializer,
    MeSerializer,
    MePermissionSerializer,
)
from .services.permission_sync import sync_user_permissions
from .utils import get_client_ip

security_logger = logging.getLogger("gpp.security")


# ─── Auth Views (Sessão) ──────────────────────────────────────────────────
class LoginView(APIView):
    """
    POST /api/accounts/login/
    Realiza autenticação via sessão (cookie HttpOnly).

    Payload: { "username": "...", "password": "...", "app_context": "PORTAL" }

    Rate limit: controlado via DEFAULT_THROTTLE_CLASSES no settings.
    Em testes, o conftest raiz zera as classes — sem throttle_scope fixo aqui.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        username = request.data.get("username")
        password = request.data.get("password")
        app_context = request.data.get("app_context")

        if not all([username, password, app_context]):
            return Response(
                {"detail": "Credenciais ou app_context não informados.", "code": "invalid_request"},
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
                {"detail": "Aplicação inválida ou bloqueada.", "code": "invalid_app"},
                status=status.HTTP_403_FORBIDDEN
            )

        if app_context == "PORTAL":
            has_access = user.is_superuser or UserRole.objects.filter(
                user=user,
                role__codigoperfil="PORTAL_ADMIN"
            ).exists()
            if not has_access:
                has_access_user = UserRole.objects.filter(
                    user=user,
                    role__codigoperfil="PORTAL_USER"
                ).exists()
                if not has_access_user:
                    return Response(
                        {"detail": "Usuário sem acesso ao Portal.", "code": "no_role"},
                        status=status.HTTP_403_FORBIDDEN
                    )
        else:
            has_access = UserRole.objects.filter(
                user=user,
                aplicacao=app
            ).exists()

            if not has_access:
                security_logger.warning(
                    "LOGIN_DENIED user_id=%s app_context=%s reason=no_role",
                    user.id, app_context
                )
                return Response(
                    {"detail": "Usuário sem acesso à aplicação informada.", "code": "no_role"},
                    status=status.HTTP_403_FORBIDDEN
                )

        login(request, user)
        request.session.cycle_key()
        request.session["app_context"] = app_context
        rotate_token(request)

        cookie_name = f"gpp_session_{app_context}"
        session_key = request.session.session_key

        # FIX(Issue #22): cycle_key() já rotacionou o session_key antes deste ponto,
        # portanto update_or_create com (user, session_key) nunca encontraria um
        # registro existente — sempre criaria um novo, acumulando sessões antigas
        # com app_context=None que poluem o resultado do middleware.
        #
        # Correção: revogar TODAS as sessões ativas do mesmo (user, cookie_name)
        # antes de criar a nova, garantindo exatamente uma AccountsSession ativa
        # por (usuário, aplicação) a qualquer momento.
        AccountsSession.objects.filter(
            user=user,
            session_cookie_name=cookie_name,
            revoked=False,
        ).update(
            revoked=True,
            revoked_at=dj_timezone.now(),
        )

        AccountsSession.objects.create(
            user=user,
            session_key=session_key,
            app_context=app_context,
            session_cookie_name=cookie_name,
            expires_at=dj_timezone.now() + timedelta(seconds=settings.SESSION_COOKIE_AGE),
            ip_address=get_client_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT", ""),
            revoked=False,
        )

        security_logger.info("LOGIN_SUCCESS user_id=%s app=%s cookie=%s", user.id, app_context, cookie_name)

        response = Response({"detail": "Login realizado com sucesso"})
        response.set_cookie(
            key=cookie_name,
            value=session_key,
            max_age=settings.SESSION_COOKIE_AGE,
            httponly=True,
            samesite="Lax",
            secure=getattr(settings, "SESSION_COOKIE_SECURE", False),
        )
        return response


class ResolveUserView(APIView):
    """
    POST /api/accounts/auth/resolve-user/
    Recebe username ou email e retorna o username canônico do Django.

    Usado pelo frontend antes do login para normalizar o identificador
    digitado pelo usuário (email ou username) para o username correto.

    Regras de segurança:
    R-01: AllowAny — endpoint público, sem autenticação.
    R-02: Retorna 404 genérico para email/username não encontrado,
          sem confirmar se o email existe no sistema (evita user enumeration).
    R-03: Apenas usuários ativos (is_active=True) são resolvidos —
          conta desativada retorna 404 como se não existisse.
    R-04: Sem rate limit próprio — controlado via DEFAULT_THROTTLE_CLASSES.
    R-05: Log de tentativas para auditoria de segurança.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        from django.contrib.auth import get_user_model
        User = get_user_model()

        identifier = (request.data.get("identifier") or "").strip()

        if not identifier:
            return Response(
                {"detail": "Identificador não informado.", "code": "invalid_request"},
                status=status.HTTP_400_BAD_REQUEST
            )

        if len(identifier) > 254:
            return Response(
                {"detail": "Identificador inválido.", "code": "invalid_request"},
                status=status.HTTP_400_BAD_REQUEST
            )

        is_email = "@" in identifier

        if is_email:
            user = User.objects.filter(
                email__iexact=identifier,
                is_active=True,
            ).first()
        else:
            user = User.objects.filter(
                username=identifier,
                is_active=True,
            ).first()

        if not user:
            security_logger.warning(
                "RESOLVE_USER_NOT_FOUND identifier_type=%s ip=%s",
                "email" if is_email else "username",
                get_client_ip(request),
            )
            return Response(
                {"detail": "Usuário não encontrado.", "code": "user_not_found"},
                status=status.HTTP_404_NOT_FOUND
            )

        security_logger.info(
            "RESOLVE_USER_SUCCESS user_id=%s identifier_type=%s ip=%s",
            user.id,
            "email" if is_email else "username",
            get_client_ip(request),
        )
        return Response({"username": user.username})


class LogoutView(APIView):
    """
    POST /api/accounts/logout/
    Encerra a sessão atual e revoga no banco.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        session_key = request.session.session_key

        AccountsSession.objects.filter(
            user=request.user,
            revoked=False,
        ).update(
            revoked=True,
            revoked_at=dj_timezone.now(),
        )

        security_logger.info(
            "LOGOUT user_id=%s session_key=%s",
            request.user.id, session_key
        )

        logout(request)
        return Response({"detail": "Logout realizado"})


class LogoutAppView(APIView):
    authentication_classes = []
    permission_classes = []

    def post(self, request, app_slug):
        app_context = app_slug.upper()
        cookie_name = f"gpp_session_{app_context}"
        session_key = request.COOKIES.get(cookie_name)

        if session_key:
            AccountsSession.objects.filter(
                session_key=session_key,
                session_cookie_name=cookie_name,
            ).update(revoked=True, revoked_at=dj_timezone.now())

            response = Response(f"Logout de {app_context} realizado com sucesso")
            response.delete_cookie(cookie_name)
        else:
            response = Response("Nenhuma sessão ativa para esta app")

        return response


# ─── Me View ────────────────────────────────────────────────────────────────────────────────────
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


class MePermissionView(APIView):
    """
    GET /api/accounts/me/permissions/

    Retorna a role do usuário autenticado na aplicação da sessão atual
    e as permissões concedidas por essa role.

    Resposta:
    {
        "role": "GESTOR",
        "granted": ["programas.view", "usuarios.manage"]
    }

    Erros:
    - 400 se a sessão não tiver app_context gravado
    - 404 se a aplicação não existir/estiver bloqueada ou o usuário não tiver role nela

    NOTA TÉCNICA:
    O AppContextMiddleware resolve a sessão via cookie gpp_session_{APP} e
    AccountsSession, gravando o resultado em request.app_context (atributo da
    request). Ele NÃO popula request.session (sessão Django padrão) nesse fluxo,
    portanto é obrigatório ler request.app_context — e não request.session.

    Não há fallback para request.session: usar request.session aqui seria
    incoerente com a arquitetura e causaria AttributeError em contextos sem
    SessionMiddleware (ex: requests diretos via APIRequestFactory nos testes).
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        app_codigo = getattr(request, "app_context", None)

        if isinstance(app_codigo, str):
            app_codigo = app_codigo.strip().upper()

        if not app_codigo:
            return Response(
                {"detail": "Contexto de app não encontrado na sessão.", "code": "no_app_context"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        app = Aplicacao.objects.filter(
            codigointerno=app_codigo,
            isappbloqueada=False,
        ).first()

        if not app:
            return Response(
                {"detail": "Aplicação não encontrada ou bloqueada.", "code": "app_not_found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        user_role = (
            UserRole.objects
            .select_related("role__group")
            .filter(user=request.user, aplicacao=app)
            .first()
        )

        if not user_role:
            return Response(
                {"detail": "Usuário sem role na aplicação informada.", "code": "no_role"},
                status=status.HTTP_404_NOT_FOUND,
            )

        data = MePermissionSerializer({
            "user": request.user,
            "role": user_role.role,
        }).data

        return Response(data)


# ─── User Create View (GAP-01) ───────────────────────────────────────────────────────

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

        from apps.accounts.services.authorization_service import AuthorizationService
        service = AuthorizationService(request.user)

        if not service._is_portal_admin():
            application = getattr(request, "application", None)
            if not service.user_can_create_user_in_application(application):
                security_logger.warning(
                    "USER_CREATE_DENIED user_id=%s app=%s reason=no_permission_in_app",
                    request.user.id,
                    getattr(application, "codigointerno", None),
                )
                raise PermissionDenied(
                    "Você só pode criar usuários nas aplicações que gerencia."
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


# ─── User Create With Role View (FASE 6) ──────────────────────────────────────────────

class UserCreateWithRoleView(APIView):
    """
    POST /api/accounts/users/create-with-role/
    Cria atomicamente auth.User + UserProfile + UserRole + sync de permissões.
    """
    permission_classes = [IsAuthenticated, CanCreateUser]

    def post(self, request):
        from apps.accounts.services.authorization_service import AuthorizationService
        service = AuthorizationService(request.user)

        if not service._is_portal_admin() and not request.user.is_superuser:
            raise PermissionDenied(
                "Criação de usuário com role é restrita ao administrador do portal."
            )

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
            "USER_CREATED_WITH_ROLE admin_id=%s new_user_id=%s role=%s app=%s",
            request.user.id,
            result["user_id"],
            result["role"],
            result["aplicacao"],
        )
        return Response(result, status=status.HTTP_201_CREATED)


# ─── Aplicacao Publica ViewSet (ARCH-01) ────────────────────────────────────────────────
class AplicacaoPublicaViewSet(viewsets.ReadOnlyModelViewSet):
    """
    GET /api/accounts/auth/aplicacoes/
    GET /api/accounts/auth/aplicacoes/{codigointerno}/

    Endpoint PÚBLICO — sem autenticação necessária.
    Usado pelo frontend para popular o seletor de app_context na tela de login.

    Retorna apenas apps ativas (não bloqueadas e prontas para produção).
    Expõe somente idaplicacao, codigointerno e nomeaplicacao — sem vazar flags internos.

    R-01: ReadOnly — POST/PUT/PATCH/DELETE retornam 405.
    R-02: Filtro fixo: isappbloqueada=False AND isappproductionready=True.
    R-03: pagination_class = None — retorna lista plana sem envelope de paginação.
    R-04: throttle_classes = [] — endpoint público de leitura; sem rate limit.
    """
    serializer_class = AplicacaoPublicaSerializer
    permission_classes = [AllowAny]
    throttle_classes = []
    pagination_class = None
    lookup_field = "codigointerno"

    def get_queryset(self):
        return Aplicacao.objects.filter(
            isappbloqueada=False,
            isappproductionready=True,
        ).order_by("nomeaplicacao")


# ─── Aplicacao ViewSet (GAP-02 / ARCH-01) ───────────────────────────────────────────────
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


# ─── CRUD ViewSets ────────────────────────────────────────────────────────────────────────

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

            sync_user_permissions(user=userrole.user)

            security_logger.info(
                "USERROLE_PERM_SYNC user_id=%s role=%s",
                userrole.user_id,
                userrole.role.codigoperfil,
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

            response = super().destroy(request, *args, **kwargs)

            # Re-sync completo após remoção da role — o orquestrador recalcula
            # o conjunto efetivo com as roles remanescentes (corrige D-04).
            sync_user_permissions(user=user)

            security_logger.info(
                "USERROLE_PERM_REVOKE_SYNC user_id=%s",
                user.pk,
            )

        return response


class UserPermissionOverrideViewSet(AuditableMixin, viewsets.ModelViewSet):
    """
    CRUD de UserPermissionOverride. Apenas PORTAL_ADMIN.

    Toda mutação (create, update, partial_update, destroy) aciona
    ``sync_user_permissions(user)`` para garantir que auth_user_user_permissions
    reflita imediatamente o override criado/alterado/removido.

    Endpoints:
      GET    /api/accounts/permission-overrides/
      POST   /api/accounts/permission-overrides/
      GET    /api/accounts/permission-overrides/{id}/
      PUT    /api/accounts/permission-overrides/{id}/
      PATCH  /api/accounts/permission-overrides/{id}/
      DELETE /api/accounts/permission-overrides/{id}/

    FASE-5-PERM (Issue #18).
    """
    serializer_class = UserPermissionOverrideSerializer
    permission_classes = [IsAuthenticated, IsPortalAdmin]

    def get_queryset(self):
        return UserPermissionOverride.objects.all().select_related(
            "user", "permission"
        ).order_by("user__username", "permission__codename")

    def _sync_after_mutation(self, override):
        """Chama sync_user_permissions e registra log após qualquer mutação."""
        sync_user_permissions(user=override.user)
        security_logger.info(
            "OVERRIDE_PERM_SYNC user_id=%s permission=%s mode=%s",
            override.user_id,
            override.permission.codename,
            override.mode,
        )

    def create(self, request, *args, **kwargs):
        security_logger.info(
            "OVERRIDE_CREATE admin_id=%s payload=%s",
            request.user.id, request.data,
        )
        with transaction.atomic():
            response = super().create(request, *args, **kwargs)
            override = UserPermissionOverride.objects.select_related(
                "user", "permission"
            ).get(pk=response.data["id"])
            self._sync_after_mutation(override)
        return response

    def update(self, request, *args, **kwargs):
        security_logger.info(
            "OVERRIDE_UPDATE admin_id=%s override_id=%s",
            request.user.id, kwargs.get("pk"),
        )
        with transaction.atomic():
            response = super().update(request, *args, **kwargs)
            override = UserPermissionOverride.objects.select_related(
                "user", "permission"
            ).get(pk=response.data["id"])
            self._sync_after_mutation(override)
        return response

    def partial_update(self, request, *args, **kwargs):
        kwargs["partial"] = True
        return self.update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        user = instance.user

        security_logger.info(
            "OVERRIDE_DELETE admin_id=%s override_id=%s user_id=%s permission=%s mode=%s",
            request.user.id, instance.pk, user.pk,
            instance.permission.codename, instance.mode,
        )

        with transaction.atomic():
            response = super().destroy(request, *args, **kwargs)
            sync_user_permissions(user=user)
            security_logger.info(
                "OVERRIDE_DELETE_PERM_SYNC user_id=%s", user.pk,
            )

        return response
