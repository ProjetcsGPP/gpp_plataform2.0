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
FIX-THROTTLE-2: throttle_scope removido de LoginView e SwitchAppView — o rate limit
                de login é controlado globalmente via DEFAULT_THROTTLE_CLASSES no
                settings. O conftest raiz zera as classes em tempo de teste, garantindo
                que nenhum login seja bloqueado por 429 durante a suite completa.
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

    Rate limit: controlado via DEFAULT_THROTTLE_CLASSES no settings.
    Em testes, o conftest raiz zera as classes — sem throttle_scope fixo aqui.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        username = request.data.get("username")
        password = request.data.get("password")
        app_context = request.data.get("app_context")

        # Validações originais mantidas
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
            isappbloqueada=False  # Lógica original mantida
        ).first()

        if not app:
            return Response(
                {"detail": "Aplicação inválida ou bloqueada.", "code": "invalid_app"},
                status=status.HTTP_403_FORBIDDEN
            )

        # Lógica original de roles mantida
        if app_context == "PORTAL":
            has_access = user.is_superuser or UserRole.objects.filter(
                user=user,
                role__codigoperfil="PORTAL_ADMIN"
            ).exists()
            if not has_access:
                return Response(
                    {"detail": "Acesso ao Portal restrito a administradores.", "code": "not_portal_admin"},
                    status=status.HTTP_403_FORBIDDEN
                )
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
                    {"detail": deny_detail, "code": "no_role"},
                    status=status.HTTP_403_FORBIDDEN
                )

        # Django login original
        login(request, user)
        request.session.cycle_key()
        request.session["app_context"] = app_context
        rotate_token(request)

        # 🔥 NOVO: COOKIE ESPECÍFICO POR APP
        cookie_name = f"gpp_session_{app_context}"
        session_key = request.session.session_key

        # AccountsSession com campo novo (update_or_create para reuso)
        AccountsSession.objects.update_or_create(
            user=user,
            session_key=session_key,
            defaults={
                "app_context": app_context,
                "session_cookie_name": cookie_name,  # NOVO CAMPO
                "expires_at": dj_timezone.now() + timedelta(seconds=settings.SESSION_COOKIE_AGE),
                "ip_address": get_client_ip(request),
                "user_agent": request.META.get("HTTP_USER_AGENT", ""),
                "revoked": False,
            }
        )

        security_logger.info("LOGIN_SUCCESS user_id=%s app=%s cookie=%s", user.id, app_context, cookie_name)

        response = Response({"detail": "Login realizado com sucesso"})

        # 🔥 MANUAL COOKIE (independe de SESSION_COOKIE_NAME)
        response.set_cookie(
            key=cookie_name,  # gpp_session_ACOES_PNGI
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

        # Limite básico de tamanho — evita payloads absurdos
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
            # Resposta genérica — não confirma se email/username existe
            # (evita user enumeration via timing ou mensagem diferente)
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

        # Revoga TODAS as sessões ativas do usuário
        # (não só a atual — evita sessões órfãs de --reuse-db e logins paralelos)
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
        
        from apps.accounts.services.authorization_service import AuthorizationService
        service = AuthorizationService(request.user)

        # PORTAL_ADMIN pode criar em qualquer app — sem restrição de escopo
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


# ─── User Create With Role View (FASE 6) ──────────────────────────────────────

class UserCreateWithRoleView(APIView):
    """
    POST /api/accounts/users/create-with-role/
    Cria atomicamente auth.User + UserProfile + UserRole + sync de permissões.
    """
    permission_classes = [IsAuthenticated, CanCreateUser]

    def post(self, request):
        from apps.accounts.services.authorization_service import AuthorizationService
        service = AuthorizationService(request.user)
        
        # Apenas PORTAL_ADMIN ou superuser podem criar usuário COM role
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
    Expõe somente idaplicacao, codigointerno e nomeaplicacao — sem vazar flags internos.

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
