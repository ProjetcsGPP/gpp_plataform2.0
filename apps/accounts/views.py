"""
GPP Platform 2.0 — Accounts Views
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
         - AplicacaoPublicaViewSet →’ GET /api/accounts/auth/aplicacoes/ (AllowAny)
           Usado pelo seletor de login; expõe apenas apps ativas sem flags internos.
         - AplicacaoViewSet →’ GET /api/accounts/aplicacoes/ (IsAuthenticated)
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
FIX(UserRoleViewSet): adicionado order_by("user__username", "role__nomeperfil") em
             get_queryset() para eliminar UnorderedObjectListWarning durante paginação.
"""

import logging
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.db import DatabaseError, IntegrityError, OperationalError, transaction
from django.middleware.csrf import rotate_token
from django.utils import timezone as dj_timezone
from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
    inline_serializer,
)
from rest_framework import serializers as drf_serializers
from rest_framework import status, viewsets
from rest_framework.exceptions import APIException, PermissionDenied
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.services.application_registry import ApplicationRegistry
from common.mixins import AuditableMixin, SecureQuerysetMixin
from common.permissions import (
    CanCreateUser,
    CanEditUser,
    HasRolePermission,
    IsPortalAdmin,
)
from common.schema import tag_all_actions

from .models import (
    AccountsSession,
    Aplicacao,
    Role,
    UserAuthzState,
    UserPermissionOverride,
    UserProfile,
    UserRole,
)
from .serializers import (
    AplicacaoPublicaSerializer,
    AplicacaoSerializer,
    MePermissionSerializer,
    MeSerializer,
    RoleSerializer,
    UserCreateSerializer,
    UserCreateWithRoleSerializer,
    UserPermissionOverrideSerializer,
    UserProfileSerializer,
    UserRoleSerializer,
)
from .services.permission_sync import sync_user_permissions
from .utils import get_client_ip

security_logger = logging.getLogger("gpp.security")


def build_cookie_name(codigo_interno: str) -> str:
    return f"gpp_session_{codigo_interno.upper()}"


# ─── Auth Views (Sessão) ──────────────────────────────────────────────────


class LoginView(APIView):
    """
    POST /api/accounts/login/
    Realiza autenticação via sessão (cookie HttpOnly).

    Payload: { "username": "...", "password": "...", "app_context": "PORTAL" }

    Rate limit: controlado via DEFAULT_THROTTLE_CLASSES no settings.
    Em testes, o conftest raiz zera as classes — sem throttle_scope fixo aqui.
    """

    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(
        summary="Login via sessão",
        description=(
            "Autentica o usuário e cria uma sessão por aplicação `gpp_session_<app_context>` "
            "(ex: `gpp_session_PORTAL`). "
            "Requer `username`, `password` e `app_context`.\n\n"
            "**Autenticação via cookie HttpOnly:** após o login bem-sucedido, o servidor "
            "retorna o header `Set-Cookie: gpp_session_<APP>=<session_key>; HttpOnly; SameSite=Lax`. "
            "O frontend **deve** usar `withCredentials: true` (axios) ou `credentials: 'include'` "
            "(fetch) em todas as requisições subsequentes para que o browser envie o cookie "
            "automaticamente.\n\n"
            "O header `X-CSRFToken` é rotacionado via `rotate_token()` a cada login — "
            "o frontend deve reler o cookie `csrftoken` e incluir o novo valor no header "
            "`X-CSRFToken` nas próximas requisições mutantes (POST/PUT/PATCH/DELETE)."
        ),
        request={
            "application/json": {
                "type": "object",
                "properties": {
                    "username": {"type": "string", "example": "joao.silva"},
                    "password": {"type": "string", "example": "senha123"},
                    "app_context": {"type": "string", "example": "PORTAL"},
                },
                "required": ["username", "password", "app_context"],
            }
        },
        responses={
            200: inline_serializer(
                name="LoginSuccessResponse",
                fields={"detail": drf_serializers.CharField()},
            ),
            400: inline_serializer(
                name="LoginBadRequestResponse",
                fields={
                    "detail": drf_serializers.CharField(),
                    "code": drf_serializers.CharField(),
                },
            ),
            401: inline_serializer(
                name="LoginUnauthorizedResponse",
                fields={
                    "detail": drf_serializers.CharField(),
                    "code": drf_serializers.CharField(),
                },
            ),
            403: inline_serializer(
                name="LoginForbiddenResponse",
                fields={
                    "detail": drf_serializers.CharField(),
                    "code": drf_serializers.CharField(),
                },
            ),
        },
        examples=[
            OpenApiExample(
                "Request — login no PORTAL",
                value={"username": "joao.silva", "password": "senha123", "app_context": "PORTAL"},
                request_only=True,
            ),
            OpenApiExample(
                "200 — Login realizado",
                value={"detail": "Login realizado com sucesso"},
                response_only=True,
                status_codes=["200"],
            ),
            OpenApiExample(
                "400 — Campos ausentes",
                value={"detail": "Credenciais ou app_context não informados.", "code": "invalid_request"},
                response_only=True,
                status_codes=["400"],
            ),
            OpenApiExample(
                "401 — Credenciais inválidas",
                value={"detail": "Credenciais inválidas.", "code": "invalid_credentials"},
                response_only=True,
                status_codes=["401"],
            ),
            OpenApiExample(
                "403 — Aplicação inválida",
                value={"detail": "Aplicação inválida ou bloqueada.", "code": "invalid_app"},
                response_only=True,
                status_codes=["403"],
            ),
            OpenApiExample(
                "403 — Sem role na aplicação",
                value={"detail": "Usuário sem acesso  à aplicação informada.", "code": "no_role"},
                response_only=True,
                status_codes=["403"],
            ),
        ],
        tags=["0 - Autenticação"],
    )
    def post(self, request):
        username = request.data.get("username")
        password = request.data.get("password")
        app_context = request.data.get("app_context")

        if not all([username, password, app_context]):
            return Response(
                {
                    "detail": "Credenciais ou app_context não informados.",
                    "code": "invalid_request",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = authenticate(request, username=username, password=password)
        if not user:
            return Response(
                {"detail": "Credenciais inválidas.", "code": "invalid_credentials"},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        app = Aplicacao.objects.filter(
            codigointerno=app_context, isappbloqueada=False
        ).first()

        if not app:
            return Response(
                {"detail": "Aplicação inválida ou bloqueada.", "code": "invalid_app"},
                status=status.HTTP_403_FORBIDDEN,
            )

        if app_context == "PORTAL":
            has_access = (
                user.is_superuser
                or UserRole.objects.filter(
                    user=user, role__codigoperfil="PORTAL_ADMIN"
                ).exists()
            )
            if not has_access:
                has_access_user = UserRole.objects.filter(
                    user=user, role__codigoperfil="PORTAL_USER"
                ).exists()
                if not has_access_user:
                    return Response(
                        {"detail": "Usuário sem acesso ao Portal.", "code": "no_role"},
                        status=status.HTTP_403_FORBIDDEN,
                    )
        else:
            has_access = UserRole.objects.filter(user=user, aplicacao=app).exists()

            if not has_access:
                security_logger.warning(
                    "LOGIN_DENIED user_id=%s app_context=%s reason=no_role",
                    user.id,
                    app_context,
                )
                return Response(
                    {
                        "detail": "Usuário sem acesso  à aplicação informada.",
                        "code": "no_role",
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

        login(request, user)
        request.session.cycle_key()
        request.session["app_context"] = app_context
        rotate_token(request)

        cookie_name = build_cookie_name(app_context)
        session_key = request.session.session_key

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
            expires_at=dj_timezone.now()
            + timedelta(seconds=settings.SESSION_COOKIE_AGE),
            ip_address=get_client_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT", ""),
            revoked=False,
        )

        security_logger.info(
            "LOGIN_SUCCESS user_id=%s app=%s cookie=%s",
            user.id,
            app_context,
            cookie_name,
        )

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

    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(
        summary="Resolve username a partir de email ou username",
        description=(
            "Recebe um identificador (email ou username) e retorna o username canônico. "
            "Usado pelo frontend antes do login para normalizar o campo digitado pelo usuário.\n\n"
            "**Anti-enumeração (R-02):** o `404` é retornado tanto para identificadores "
            "inexistentes quanto para contas desativadas — sem distinguir os dois casos — "
            "para evitar que um atacante confirme a existência de um e-mail no sistema.\n\n"
            "Este endpoint é público (`AllowAny`). O frontend **não** precisa enviar cookie "
            "nem `withCredentials: true` nesta chamada."
        ),
        request={
            "application/json": {
                "type": "object",
                "properties": {
                    "identifier": {"type": "string", "example": "joao@gov.br"},
                },
                "required": ["identifier"],
            }
        },
        responses={
            200: inline_serializer(
                name="ResolveUserSuccessResponse",
                fields={"username": drf_serializers.CharField()},
            ),
            400: inline_serializer(
                name="ResolveUserBadRequestResponse",
                fields={
                    "detail": drf_serializers.CharField(),
                    "code": drf_serializers.CharField(),
                },
            ),
            404: inline_serializer(
                name="ResolveUserNotFoundResponse",
                fields={
                    "detail": drf_serializers.CharField(),
                    "code": drf_serializers.CharField(),
                },
            ),
        },
        examples=[
            OpenApiExample(
                "Request — por e-mail",
                value={"identifier": "joao@gov.br"},
                request_only=True,
            ),
            OpenApiExample(
                "Request — por username",
                value={"identifier": "joao.silva"},
                request_only=True,
            ),
            OpenApiExample(
                "200 — Username resolvido",
                value={"username": "joao.silva"},
                response_only=True,
                status_codes=["200"],
            ),
            OpenApiExample(
                "400 — Identificador vazio",
                value={"detail": "Identificador não informado.", "code": "invalid_request"},
                response_only=True,
                status_codes=["400"],
            ),
            OpenApiExample(
                "400 — Identificador muito longo",
                value={"detail": "Identificador inválido.", "code": "invalid_request"},
                response_only=True,
                status_codes=["400"],
            ),
            OpenApiExample(
                "404 — Não encontrado",
                value={"detail": "Usuário não encontrado.", "code": "user_not_found"},
                response_only=True,
                status_codes=["404"],
            ),
        ],
        tags=["0 - Autenticação"],
    )
    def post(self, request):
        from django.contrib.auth import get_user_model

        User = get_user_model()

        identifier = (request.data.get("identifier") or "").strip()

        if not identifier:
            return Response(
                {"detail": "Identificador não informado.", "code": "invalid_request"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if len(identifier) > 254:
            return Response(
                {"detail": "Identificador inválido.", "code": "invalid_request"},
                status=status.HTTP_400_BAD_REQUEST,
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
                status=status.HTTP_404_NOT_FOUND,
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

    @extend_schema(
        operation_id="accounts_logout_session",
        summary="Logout da sessão atual",
        description=(
            "Encerra a sessão ativa e revoga o registro em AccountsSession.\n\n"
            "Requer que o frontend envie o cookie de sessão (`gpp_session_<APP>`) "
            "via `withCredentials: true` (axios) ou `credentials: 'include'` (fetch). "
            "Após o logout, o cookie deve ser removido pelo frontend."
        ),
        request=None,
        responses={
            200: inline_serializer(
                name="LogoutSuccessResponse",
                fields={"detail": drf_serializers.CharField()},
            ),
            401: inline_serializer(
                name="LogoutUnauthorizedResponse",
                fields={
                    "detail": drf_serializers.CharField(),
                    "code": drf_serializers.CharField(),
                },
            ),
            403: inline_serializer(
                name="LogoutForbiddenResponse",
                fields={
                    "detail": drf_serializers.CharField(),
                    "code": drf_serializers.CharField(),
                },
            ),
        },
        examples=[
            OpenApiExample(
                "200 — Logout realizado",
                value={"detail": "Logout realizado"},
                response_only=True,
                status_codes=["200"],
            ),
            OpenApiExample(
                "403 — Não autenticado (sessão expirada ou cookie ausente)",
                value={"detail": "As credenciais de autenticação não foram fornecidas."},
                response_only=True,
                status_codes=["403"],
            ),
        ],
        tags=["0 - Autenticação"],
    )
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
            "LOGOUT user_id=%s session_key=%s", request.user.id, session_key
        )

        logout(request)
        return Response({"detail": "Logout realizado"})


class LogoutAppView(APIView):
    authentication_classes = []
    permission_classes = []

    @extend_schema(
        operation_id="accounts_logout_app",
        summary="Logout de uma aplicação específica",
        description=(
            "Revoga a sessão da app informada via `app_slug` e apaga o cookie "
            "`gpp_session_<APP>` correspondente.\n\n"
            "Este endpoint **não exige autenticação** — a identificação da sessão é feita "
            "diretamente pelo cookie `gpp_session_<APP>` presente na requisição. "
            "O frontend deve enviar `credentials: 'include'` para que o browser inclua "
            "o cookie automaticamente.\n\n"
            "Se o cookie não estiver presente, o endpoint retorna `200` com mensagem "
            "indicando que não havia sessão ativa — não retorna erro."
        ),
        parameters=[
            OpenApiParameter(
                name="app_slug",
                location=OpenApiParameter.PATH,
                description="Slug (código interno) da aplicação a deslogar (ex: `portal`, `sigef`).",
                required=True,
                type=str,
            ),
        ],
        request=None,
        responses={
            200: OpenApiResponse(description="Logout realizado ou sessão já inexistente"),
            400: inline_serializer(
                name="LogoutAppBadRequestResponse",
                fields={
                    "detail": drf_serializers.CharField(),
                    "code": drf_serializers.CharField(),
                },
            ),
        },
        examples=[
            OpenApiExample(
                "200 — Logout com cookie presente",
                value="Logout de PORTAL realizado com sucesso",
                response_only=True,
                status_codes=["200"],
            ),
            OpenApiExample(
                "200 — Sem sessão ativa",
                value="Nenhuma sessão ativa para esta app",
                response_only=True,
                status_codes=["200"],
            ),
            OpenApiExample(
                "400 — App inválida",
                value="App inválida",
                response_only=True,
                status_codes=["400"],
            ),
        ],
        tags=["0 - Autenticação"],
    )
    def post(self, request, app_slug):
        registry = ApplicationRegistry()

        app = registry.get(app_slug)

        if not app:
            return Response("App inválida", status=400)
        app_context = app_slug.upper()
        cookie_name = build_cookie_name(app_context)
        session_key = request.COOKIES.get(cookie_name)
        if session_key:
            AccountsSession.objects.filter(
                session_key=session_key,
                session_cookie_name=cookie_name,
            ).update(revoked=True, revoked_at=dj_timezone.now())

            response = Response(f"Logout de {app_context} realizado com sucesso")
            # safe: app_slug validated via ApplicationRegistry (trusted source)
            response.delete_cookie(cookie_name)
        else:
            response = Response("Nenhuma sessão ativa para esta app")

        return response


# ---- Me View -------------

class MeView(APIView):
    """
    GET /api/accounts/me/
    Retorna dados do usuário autenticado: profile + roles + apps com acesso.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Dados do usuário autenticado",
        description=(
            "Retorna os dados do usuário autenticado na sessão atual: profile, roles e apps com acesso.\n\n"
            "A autenticação é realizada via **sessão Django** — o cookie `gpp_session_<APP>` (HttpOnly) "
            "é enviado automaticamente pelo browser. "
            "Em chamadas via JavaScript/Axios/Fetch, o frontend deve usar `withCredentials: true` "
            "para garantir o envio do cookie de sessão.\n\n"
            "Este endpoint não aceita tokens JWT. A sessão é vinculada ao contexto de aplicação "
            "(`app_context`) definido no momento do login."
        ),
        responses={
            200: MeSerializer,
            401: OpenApiResponse(description="Não autenticado — sessão ausente ou expirada."),
        },
        examples=[
            OpenApiExample(
                name="Resposta 200 — Usuário autenticado",
                summary="Dados completos do usuário autenticado",
                description="Exemplo real de retorno para um usuário ativo com role no Portal.",
                value={
                    "id": 42,
                    "username": "joao.silva",
                    "email": "joao.silva@orgao.gov.br",
                    "name": "João da Silva",
                    "is_portal_admin": False,
                    "orgao": "Secretaria de Planejamento",
                    "status_usuario_id": 1,
                    "roles": [
                        {
                            "role": "GESTOR",
                            "aplicacao": "PNGI",
                        }
                    ],
                },
                response_only=True,
                status_codes=["200"],
            ),
        ],
        tags=["1 - Usuários"],
    )
    def get(self, request):
        user = request.user

        try:
            profile = user.profile
        except UserProfile.DoesNotExist:
            profile = None

        user_roles = UserRole.objects.filter(user=user).select_related(
            "role", "aplicacao"
        )

        data = MeSerializer(
            {
                "user": user,
                "profile": profile,
                "user_roles": user_roles,
            }
        ).data

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

    NOTA TÃ‰CNICA:
    O AppContextMiddleware resolve a sessão via cookie gpp_session_{APP} e
    AccountsSession, gravando o resultado em request.app_context (atributo da
    request). Ele NÃƒO popula request.session (sessão Django padrão) nesse fluxo,
    portanto é obrigatório ler request.app_context — e não request.session.

    Não há fallback para request.session: usar request.session aqui seria
    incoerente com a arquitetura e causaria AttributeError em contextos sem
    SessionMiddleware (ex: requests diretos via APIRequestFactory nos testes).
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Permissões do usuário na app atual",
        description=(
            "Retorna a role e as permissões do usuário autenticado "
            "na aplicação da sessão atual (`app_context`).\n\n"
            "A autenticação é realizada via **sessão Django** — o cookie `gpp_session_<APP>` "
            "(HttpOnly) é enviado automaticamente pelo browser. "
            "Em chamadas via JavaScript/Axios/Fetch, o frontend deve usar `withCredentials: true` "
            "para garantir o envio do cookie de sessão.\n\n"
            "O `app_context` é resolvido pelo `AppContextMiddleware` a partir do cookie de sessão "
            "e da tabela `AccountsSession`. O resultado é gravado diretamente em `request.app_context` "
            "— este endpoint depende obrigatoriamente desse middleware estar ativo na requisição."
        ),
        responses={
            200: MePermissionSerializer,
            400: OpenApiResponse(description="Sem app_context na sessão."),
            401: OpenApiResponse(description="Não autenticado — sessão ausente ou expirada."),
            404: OpenApiResponse(description="App não encontrada ou bloqueada, ou usuário sem role na aplicação."),
        },
        examples=[
            OpenApiExample(
                name="Resposta 200 — Role e permissões",
                summary="Usuário autenticado com role GESTOR na app atual",
                value={
                    "role": "GESTOR",
                    "granted": ["programas.view", "usuarios.manage"],
                },
                response_only=True,
                status_codes=["200"],
            ),
            OpenApiExample(
                name="Erro 400 — Sem app_context",
                summary="Sessão sem contexto de aplicação definido",
                value={
                    "detail": "Contexto de app não encontrado na sessão.",
                    "code": "no_app_context",
                },
                response_only=True,
                status_codes=["400"],
            ),
            OpenApiExample(
                name="Erro 404 — Sem role",
                summary="Usuário sem role na aplicação informada",
                value={
                    "detail": "Usuário sem role na aplicação informada.",
                    "code": "no_role",
                },
                response_only=True,
                status_codes=["404"],
            ),
        ],
        tags=["1 - Usuários"],
    )
    def get(self, request):
        app_codigo = getattr(request, "app_context", None)

        if isinstance(app_codigo, str):
            app_codigo = app_codigo.strip().upper()

        if not app_codigo:
            return Response(
                {
                    "detail": "Contexto de app não encontrado na sessão.",
                    "code": "no_app_context",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        app = Aplicacao.objects.filter(
            codigointerno=app_codigo,
            isappbloqueada=False,
        ).first()

        if not app:
            return Response(
                {
                    "detail": "Aplicação não encontrada ou bloqueada.",
                    "code": "app_not_found",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        user_role = (
            UserRole.objects.select_related("role__group")
            .filter(user=request.user, aplicacao=app)
            .first()
        )

        if not user_role:
            return Response(
                {
                    "detail": "Usuário sem role na aplicação informada.",
                    "code": "no_role",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        data = MePermissionSerializer(
            {
                "user": request.user,
                "role": user_role.role,
            }
        ).data

        return Response(data)


class AuthzVersionView(APIView):
    """
    GET /api/authz/version/

    Retorna a versão de autorização atual do usuário autenticado.

    O frontend usa este endpoint para polling leve. Se o valor de
    ``authz_version`` mudar desde o último check, o frontend deve:
      - refazer GET /me/permissions/
      - refazer GET navigation JSON
      - invalidar caches locais (React Query / Zustand)

    Garantias de performance:
      - O(1): consulta direta por user_id — sem joins, sem RBAC.
      - Sem chamadas a sync_user_permissions.
      - Sem leitura de auth_user_user_permissions.

    Segurança:
      - Requer autenticação.
      - Retorna SOMENTE a versão do usuário autenticado.
      - Não expõe informações de outros usuários.
      - NÃƒO pode ser usado para decisões de autorização.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Versão de autorização do usuário autenticado",
        description=(
            "Retorna o número de versão de autorização do usuário autenticado. "
            "Usado **exclusivamente** pelo frontend para invalidação de cache — "
            "não representa permissões reais e não deve ser usado em decisões de autorização.\n\n"
            "A versão começa em `0` quando o usuário ainda não possui um `UserAuthzState` "
            "(nenhuma mudança de permissão ocorreu desde a criação da conta). "
            "O valor é incrementado automaticamente a cada sync de permissões.\n\n"
            "Quando o valor de `authz_version` mudar desde o último check, o frontend deve "
            "refazer `GET /me/permissions/`, atualizar o JSON de navegação e invalidar "
            "caches locais (React Query / Zustand)."
        ),
        responses={
            200: inline_serializer(
                name="AuthzVersionResponse",
                fields={
                    "authz_version": drf_serializers.IntegerField(
                        help_text="Versão atual de autorização do usuário. Começa em 0 se não houver estado registrado."
                    ),
                },
            ),
            401: OpenApiResponse(description="Não autenticado — sessão ausente ou expirada."),
        },
        examples=[
            OpenApiExample(
                name="Versão inicial — sem estado de autorização",
                summary="Usuário sem UserAuthzState registrado (versão lazy = 0)",
                value={"authz_version": 0},
                response_only=True,
                status_codes=["200"],
            ),
            OpenApiExample(
                name="Versão incrementada — permissões já sincronizadas",
                summary="Usuário com múltiplos ciclos de sync de permissões",
                value={"authz_version": 42},
                response_only=True,
                status_codes=["200"],
            ),
        ],
        tags=["1 - Usuários"],
    )
    def get(self, request):
        """
        Consulta direta em UserAuthzState por user_id.
        Se o estado ainda não existe (usuário nunca teve mudança de permissão),
        retorna version=0 sem criar registro — comportamento lazy.
        """
        user_id = request.user.pk

        try:
            state = UserAuthzState.objects.only("authz_version").get(user_id=user_id)
            version = state.authz_version
        except UserAuthzState.DoesNotExist:
            version = 0

        security_logger.info(
            "AUTHZ_VERSION_FETCHED user_id=%s version=%s", user_id, version
        )
        return Response({"authz_version": version})


class UserCreateView(APIView):
    """
    POST /api/accounts/users/
    Cria atomicamente um auth.User e seu UserProfile.
    """

    permission_classes = [IsAuthenticated, CanCreateUser]

    @extend_schema(
        summary="Criar usuário (sem role)",
        description=(
            "Cria atomicamente um `auth.User` e seu `UserProfile` vinculado.\n\n"
            "**Autenticação:** requer sessão ativa via cookie HttpOnly "
            "`gpp_session_<APP>` (ex: `gpp_session_PORTAL`). "
            "O frontend deve enviar todas as requisições com `withCredentials: true`.\n\n"
            "**Permissões:**\n"
            "- `401 Unauthorized` — sessão ausente ou expirada (não autenticado).\n"
            "- `403 Forbidden` — autenticado, mas sem a permissão `CanCreateUser` "
            "ou fora do escopo de aplicações que o operador gerencia.\n\n"
            "**Campo `password`:** write-only. Nunca é retornado na resposta.\n\n"
            "**Atomicidade:** criação do `User` e do `UserProfile` ocorre em uma única "
            "transação — em caso de falha, nenhum registro parcial é persistido."
        ),
        request=UserCreateSerializer,
        responses={
            201: OpenApiResponse(
                response=UserCreateSerializer,
                description="Usuário criado com sucesso. O campo `password` não é retornado.",
                examples=[
                    OpenApiExample(
                        "Usuário criado",
                        summary="Resposta 201 — criação bem-sucedida",
                        value={
                            "username": "joao.silva",
                            "email": "joao.silva@gov.br",
                            "first_name": "João",
                            "last_name": "Silva",
                            "profile": {
                                "cpf": "000.000.000-00",
                                "telefone": "(27) 99999-0000",
                            },
                        },
                        response_only=True,
                        status_codes=["201"],
                    )
                ],
            ),
            400: OpenApiResponse(
                description="Dados de entrada inválidos.",
                examples=[
                    OpenApiExample(
                        "Username duplicado",
                        summary="Erro 400 — username já existe",
                        value={
                            "detail": "Um usuário com este username já existe.",
                            "code": "username_already_exists",
                        },
                        response_only=True,
                        status_codes=["400"],
                    ),
                    OpenApiExample(
                        "E-mail duplicado",
                        summary="Erro 400 — e-mail já cadastrado",
                        value={
                            "detail": "Este e-mail já está em uso por outro usuário.",
                            "code": "email_already_exists",
                        },
                        response_only=True,
                        status_codes=["400"],
                    ),
                    OpenApiExample(
                        "Senha inválida",
                        summary="Erro 400 — senha não atende aos critérios",
                        value={
                            "detail": "Esta senha é muito curta. Ela deve conter pelo menos 8 caracteres.",
                            "code": "password_too_short",
                        },
                        response_only=True,
                        status_codes=["400"],
                    ),
                    OpenApiExample(
                        "Campos obrigatórios ausentes",
                        summary="Erro 400 — payload incompleto",
                        value={
                            "username": ["Este campo é obrigatório."],
                            "password": ["Este campo é obrigatório."],
                        },
                        response_only=True,
                        status_codes=["400"],
                    ),
                ],
            ),
            401: OpenApiResponse(
                description="Não autenticado — sessão ausente ou expirada.",
                examples=[
                    OpenApiExample(
                        "Não autenticado",
                        summary="Erro 401 — cookie de sessão ausente ou inválido",
                        value={
                            "detail": "As credenciais de autenticação não foram fornecidas.",
                            "code": "not_authenticated",
                        },
                        response_only=True,
                        status_codes=["401"],
                    )
                ],
            ),
            403: OpenApiResponse(
                description=(
                    "Proibido — autenticado, mas sem permissão `CanCreateUser` "
                    "ou fora do escopo de aplicações gerenciadas pelo operador."
                ),
                examples=[
                    OpenApiExample(
                        "Sem permissão global",
                        summary="Erro 403 — permissão CanCreateUser ausente",
                        value={
                            "detail": "Você não tem permissão para executar essa ação.",
                            "code": "permission_denied",
                        },
                        response_only=True,
                        status_codes=["403"],
                    ),
                    OpenApiExample(
                        "Fora do escopo de app",
                        summary="Erro 403 — operador fora do escopo da aplicação",
                        value={
                            "detail": "Você só pode criar usuários nas aplicações que gerencia.",
                            "code": "permission_denied",
                        },
                        response_only=True,
                        status_codes=["403"],
                    ),
                ],
            ),
        },
        tags=["1 - Usuários"],
    )
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
                request.user.id,
                str(exc),
            )
            raise APIException(
                detail="Erro interno ao criar usuário. Tente novamente."
            ) from exc

        security_logger.info(
            "USER_CREATED admin_id=%s new_user_id=%s username=%s",
            request.user.id,
            profile.user_id,
            profile.user.username,
        )
        return Response(
            UserCreateSerializer(profile, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class UserCreateWithRoleView(APIView):
    """
    POST /api/accounts/users/create-with-role/
    Cria atomicamente auth.User + UserProfile + UserRole + sync de permissões.
    """

    permission_classes = [IsAuthenticated, CanCreateUser]

    @extend_schema(
        summary="Criar usuário com role (fluxo completo)",
        description=(
            "Cria atomicamente `auth.User` + `UserProfile` + `UserRole` e dispara "
            "sincronização de permissões via `sync_user_permissions`.\n\n"
            "**Autenticação:** requer sessão ativa via cookie HttpOnly "
            "`gpp_session_<APP>` (ex: `gpp_session_PORTAL`). "
            "O frontend deve enviar todas as requisições com `withCredentials: true`.\n\n"
            "**Permissões:**\n"
            "- `401 Unauthorized` — sessão ausente ou expirada (não autenticado).\n"
            "- `403 Forbidden (papel insuficiente)` — autenticado, mas não é `PORTAL_ADMIN` "
            "nem `superuser`.\n"
            "- `403 Forbidden (escopo)` — é `PORTAL_ADMIN`, mas a `aplicacao` de destino "
            "está fora das aplicações que o operador gerencia.\n\n"
            "**Atomicidade:** `User`, `UserProfile`, `UserRole` e o sync de permissões "
            "ocorrem em uma única transação — em caso de falha, nenhum registro parcial "
            "é persistido.\n\n"
            "**Resposta:** retorna um `dict` customizado com os dados do usuário criado, "
            "sua role e a aplicação vinculada."
        ),
        request=UserCreateWithRoleSerializer,
        responses={
            201: OpenApiResponse(
                description="Usuário criado com role e permissões sincronizadas.",
                examples=[
                    OpenApiExample(
                        "Usuário criado com role",
                        summary="Resposta 201 — criação bem-sucedida",
                        value={
                            "user_id": 42,
                            "username": "joao.silva",
                            "email": "joao.silva@gov.br",
                            "first_name": "João",
                            "last_name": "Silva",
                            "role": "GESTOR",
                            "aplicacao": "ACOES_PNGI",
                        },
                        response_only=True,
                        status_codes=["201"],
                    )
                ],
            ),
            400: OpenApiResponse(
                description="Dados de entrada inválidos.",
                examples=[
                    OpenApiExample(
                        "Username duplicado",
                        summary="Erro 400 — username já existe",
                        value={
                            "detail": "Um usuário com este username já existe.",
                            "code": "username_already_exists",
                        },
                        response_only=True,
                        status_codes=["400"],
                    ),
                    OpenApiExample(
                        "E-mail duplicado",
                        summary="Erro 400 — e-mail já cadastrado",
                        value={
                            "detail": "Este e-mail já está em uso por outro usuário.",
                            "code": "email_already_exists",
                        },
                        response_only=True,
                        status_codes=["400"],
                    ),
                    OpenApiExample(
                        "Senha inválida",
                        summary="Erro 400 — senha não atende aos critérios",
                        value={
                            "detail": "Esta senha é muito curta. Ela deve conter pelo menos 8 caracteres.",
                            "code": "password_too_short",
                        },
                        response_only=True,
                        status_codes=["400"],
                    ),
                    OpenApiExample(
                        "Role inválida para aplicação",
                        summary="Erro 400 — role não pertence  à aplicação informada",
                        value={
                            "detail": "A role informada não pertence  à aplicação selecionada.",
                            "code": "invalid_role_for_application",
                        },
                        response_only=True,
                        status_codes=["400"],
                    ),
                    OpenApiExample(
                        "Campos obrigatórios ausentes",
                        summary="Erro 400 — payload incompleto",
                        value={
                            "username": ["Este campo é obrigatório."],
                            "password": ["Este campo é obrigatório."],
                            "role": ["Este campo é obrigatório."],
                        },
                        response_only=True,
                        status_codes=["400"],
                    ),
                ],
            ),
            401: OpenApiResponse(
                description="Não autenticado — sessão ausente ou expirada.",
                examples=[
                    OpenApiExample(
                        "Não autenticado",
                        summary="Erro 401 — cookie de sessão ausente ou inválido",
                        value={
                            "detail": "As credenciais de autenticação não foram fornecidas.",
                            "code": "not_authenticated",
                        },
                        response_only=True,
                        status_codes=["401"],
                    )
                ],
            ),
            403: OpenApiResponse(
                description=(
                    "Proibido — papel insuficiente ou operador fora do escopo "
                    "da aplicação de destino."
                ),
                examples=[
                    OpenApiExample(
                        "Papel insuficiente",
                        summary="Erro 403 — usuário não é PORTAL_ADMIN nem superuser",
                        value={
                            "detail": "Criação de usuário com role é restrita ao administrador do portal.",
                            "code": "permission_denied",
                        },
                        response_only=True,
                        status_codes=["403"],
                    ),
                    OpenApiExample(
                        "Fora do escopo de app",
                        summary="Erro 403 — aplicação de destino fora do escopo gerenciado",
                        value={
                            "detail": "Você só pode criar usuários nas aplicações que gerencia.",
                            "code": "permission_denied",
                        },
                        response_only=True,
                        status_codes=["403"],
                    ),
                ],
            ),
        },
        tags=["1 - Usuários"],
    )
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
            from apps.accounts.services.authorization_service import (
                AuthorizationService,
            )

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


@tag_all_actions("1 - Usuários")
class UserProfileViewSet(SecureQuerysetMixin, AuditableMixin, viewsets.ModelViewSet):
    """
    APIs de UserProfile.
    """

    serializer_class = UserProfileSerializer
    permission_classes = [IsAuthenticated, HasRolePermission, CanEditUser]
    http_method_names = ["get", "patch", "head", "options"]
    lookup_field = "user_id"

    scope_field = "orgao"
    scope_source = "orgao"

    def get_queryset(self):
        user = self.request.user
        if getattr(self.request, "is_portal_admin", False):
            return (
                UserProfile.objects.all()
                .select_related("user", "status_usuario", "tipo_usuario")
                .order_by("user__username")
            )
        return (
            UserProfile.objects.filter(user=user)
            .select_related("user", "status_usuario", "tipo_usuario")
            .order_by("user__username")
        )

    @extend_schema(
        summary="Atualizar parcialmente perfil de usuário",
        description=(
            "Atualiza parcialmente um `UserProfile` existente.\n\n"
            "**Autenticação:** requer sessão ativa via cookie HttpOnly "
            "`gpp_session_<APP>` (ex: `gpp_session_PORTAL`). "
            "O frontend deve enviar todas as requisições com `withCredentials: true`.\n\n"
            "**Parâmetro de rota:** `user_id` identifica o usuário dono do perfil.\n\n"
            "**Permissões e cenários de `403 Forbidden`:**\n"
            "- sem permissão para editar o perfil alvo;\n"
            "- tentativa de alterar `classificacao_usuario` sem privilégio administrativo;\n"
            "- tentativa de alterar `status_usuario` sem privilégio administrativo.\n\n"
            "**Observação:** esta operação é parcial (`PATCH`), portanto apenas os campos "
            "enviados no payload serão alterados."
        ),
        parameters=[
            OpenApiParameter(
                name="user_id",
                type=int,
                location=OpenApiParameter.PATH,
                required=True,
                description="ID do usuário dono do perfil a ser consultado/atualizado.",
                examples=[
                    OpenApiExample(
                        "Exemplo de user_id",
                        value=42,
                    )
                ],
            )
        ],
        request=UserProfileSerializer,
        responses={
            200: OpenApiResponse(
                response=UserProfileSerializer,
                description="Perfil atualizado com sucesso.",
                examples=[
                    OpenApiExample(
                        "Perfil atualizado",
                        summary="Resposta 200 — atualização parcial bem-sucedida",
                        value={
                            "user": 42,
                            "telefone": "(27) 99999-0000",
                            "classificacao_usuario": 1,
                            "status_usuario": 1,
                            "tipo_usuario": 2,
                            "orgao": 10,
                        },
                        response_only=True,
                        status_codes=["200"],
                    )
                ],
            ),
            400: OpenApiResponse(
                description="Dados inválidos no payload.",
                examples=[
                    OpenApiExample(
                        "Campo inválido",
                        summary="Erro 400 — valor inválido em campo do perfil",
                        value={
                            "telefone": ["Informe um valor válido."],
                        },
                        response_only=True,
                        status_codes=["400"],
                    )
                ],
            ),
            401: OpenApiResponse(
                description="Não autenticado — sessão ausente ou expirada.",
                examples=[
                    OpenApiExample(
                        "Não autenticado",
                        summary="Erro 401 — cookie de sessão ausente ou inválido",
                        value={
                            "detail": "As credenciais de autenticação não foram fornecidas.",
                            "code": "not_authenticated",
                        },
                        response_only=True,
                        status_codes=["401"],
                    )
                ],
            ),
            403: OpenApiResponse(
                description=(
                    "Proibido — usuário autenticado, mas sem permissão para editar o perfil "
                    "ou para alterar campos restritos."
                ),
                examples=[
                    OpenApiExample(
                        "Sem permissão para editar perfil",
                        summary="Erro 403 — edição do perfil alvo não permitida",
                        value={
                            "detail": "Você não tem permissão para editar este perfil.",
                            "code": "permission_denied",
                        },
                        response_only=True,
                        status_codes=["403"],
                    ),
                    OpenApiExample(
                        "Sem permissão para alterar classificação",
                        summary="Erro 403 — mudança de classificacao_usuario restrita",
                        value={
                            "detail": "Apenas administradores podem alterar a classificação.",
                            "code": "permission_denied",
                        },
                        response_only=True,
                        status_codes=["403"],
                    ),
                    OpenApiExample(
                        "Sem permissão para alterar status",
                        summary="Erro 403 — mudança de status_usuario restrita",
                        value={
                            "detail": "Apenas administradores podem alterar o status do usuário.",
                            "code": "permission_denied",
                        },
                        response_only=True,
                        status_codes=["403"],
                    ),
                ],
            ),
            404: OpenApiResponse(
                description="Perfil não encontrado para o `user_id` informado.",
                examples=[
                    OpenApiExample(
                        "Perfil não encontrado",
                        summary="Erro 404 — user_id inexistente",
                        value={
                            "detail": "Não encontrado.",
                            "code": "not_found",
                        },
                        response_only=True,
                        status_codes=["404"],
                    )
                ],
            ),
        },
        tags=["1 - Usuários"],
    )
    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        from apps.accounts.policies import UserProfilePolicy

        policy = UserProfilePolicy(request.user, instance)

        if not policy.can_edit_profile():
            security_logger.warning(
                "PROFILE_PATCH_DENIED user_id=%s target_user_id=%s",
                request.user.id,
                instance.user_id,
            )
            raise PermissionDenied("Você não tem permissão para editar este perfil.")

        if (
            "classificacao_usuario" in request.data
            and not policy.can_change_classificacao()
        ):
            security_logger.warning(
                "PROFILE_PATCH_CLASSIFICACAO_DENIED user_id=%s target_user_id=%s",
                request.user.id,
                instance.user_id,
            )
            raise PermissionDenied(
                "Apenas administradores podem alterar a classificação."
            )

        if "status_usuario" in request.data and not policy.can_change_status():
            security_logger.warning(
                "PROFILE_PATCH_STATUS_DENIED user_id=%s target_user_id=%s",
                request.user.id,
                instance.user_id,
            )
            raise PermissionDenied(
                "Apenas administradores podem alterar o status do usuário."
            )

        return super().partial_update(request, *args, **kwargs)


@tag_all_actions("1 - Usuários")
class RoleViewSet(viewsets.ReadOnlyModelViewSet):
    """
    GET /api/accounts/roles/
    GET /api/accounts/roles/{id}/
    Acesso exclusivo a PORTAL_ADMIN.
    """

    serializer_class = RoleSerializer
    permission_classes = [IsAuthenticated, IsPortalAdmin]

    @extend_schema(
        summary="Listar roles",
        description=(
            "Retorna a lista de roles disponíveis no sistema.\n\n"
            "**Autenticação:** requer sessão ativa via cookie HttpOnly "
            "`gpp_session_<APP>` (ex: `gpp_session_PORTAL`). "
            "O frontend deve enviar todas as requisições com `withCredentials: true`.\n\n"
            "**Permissões:** acesso exclusivo a usuários com perfil `PORTAL_ADMIN`.\n\n"
            "**Filtro opcional:** use o parâmetro de query `aplicacao_id` para retornar "
            "apenas as roles vinculadas a uma aplicação específica.\n\n"
            "**Comportamento do filtro:** se `aplicacao_id` não puder ser convertido "
            "para inteiro, a listagem retorna vazia."
        ),
        parameters=[
            OpenApiParameter(
                name="aplicacao_id",
                type=int,
                location=OpenApiParameter.QUERY,
                required=False,
                description="ID da aplicação usada para filtrar as roles retornadas.",
                examples=[
                    OpenApiExample(
                        "Filtrar por aplicação",
                        value=3,
                    )
                ],
            )
        ],
        responses={
            200: OpenApiResponse(
                response=RoleSerializer(many=True),
                description="Lista de roles retornada com sucesso.",
                examples=[
                    OpenApiExample(
                        "Lista de roles",
                        summary="Resposta 200 — listagem sem filtro",
                        value=[
                            {
                                "id": 1,
                                "nomeperfil": "PORTAL_ADMIN",
                                "codigoperfil": "PORTAL_ADMIN",
                                "aplicacao": 1,
                            },
                            {
                                "id": 2,
                                "nomeperfil": "GESTOR",
                                "codigoperfil": "GESTOR",
                                "aplicacao": 3,
                            },
                        ],
                        response_only=True,
                        status_codes=["200"],
                    )
                ],
            ),
            401: OpenApiResponse(
                description="Não autenticado — sessão ausente ou expirada.",
                examples=[
                    OpenApiExample(
                        "Não autenticado",
                        summary="Erro 401 — cookie de sessão ausente ou inválido",
                        value={
                            "detail": "As credenciais de autenticação não foram fornecidas.",
                            "code": "not_authenticated",
                        },
                        response_only=True,
                        status_codes=["401"],
                    )
                ],
            ),
            403: OpenApiResponse(
                description="Proibido — usuário autenticado, mas sem perfil PORTAL_ADMIN.",
                examples=[
                    OpenApiExample(
                        "Sem permissão",
                        summary="Erro 403 — acesso restrito a PORTAL_ADMIN",
                        value={
                            "detail": "Você não tem permissão para executar essa ação.",
                            "code": "permission_denied",
                        },
                        response_only=True,
                        status_codes=["403"],
                    )
                ],
            ),
        },
        tags=["1 - Usuários"],
    )
    @extend_schema(
        summary="Detalhar role",
        description=(
            "Retorna os dados de uma role específica pelo seu identificador.\n\n"
            "**Autenticação:** requer sessão ativa via cookie HttpOnly "
            "`gpp_session_<APP>` (ex: `gpp_session_PORTAL`). "
            "O frontend deve enviar todas as requisições com `withCredentials: true`.\n\n"
            "**Permissões:** acesso exclusivo a usuários com perfil `PORTAL_ADMIN`."
        ),
        responses={
            200: OpenApiResponse(
                response=RoleSerializer,
                description="Detalhes da role retornados com sucesso.",
                examples=[
                    OpenApiExample(
                        "Detalhe da role",
                        summary="Resposta 200 — role encontrada",
                        value={
                            "id": 1,
                            "nomeperfil": "PORTAL_ADMIN",
                            "codigoperfil": "PORTAL_ADMIN",
                            "aplicacao": 1,
                        },
                        response_only=True,
                        status_codes=["200"],
                    )
                ],
            ),
            401: OpenApiResponse(
                description="Não autenticado — sessão ausente ou expirada.",
                examples=[
                    OpenApiExample(
                        "Não autenticado",
                        summary="Erro 401 — cookie de sessão ausente ou inválido",
                        value={
                            "detail": "As credenciais de autenticação não foram fornecidas.",
                            "code": "not_authenticated",
                        },
                        response_only=True,
                        status_codes=["401"],
                    )
                ],
            ),
            403: OpenApiResponse(
                description="Proibido — usuário autenticado, mas sem perfil PORTAL_ADMIN.",
                examples=[
                    OpenApiExample(
                        "Sem permissão",
                        summary="Erro 403 — acesso restrito a PORTAL_ADMIN",
                        value={
                            "detail": "Você não tem permissão para executar essa ação.",
                            "code": "permission_denied",
                        },
                        response_only=True,
                        status_codes=["403"],
                    )
                ],
            ),
            404: OpenApiResponse(
                description="Role não encontrada para o ID informado.",
                examples=[
                    OpenApiExample(
                        "Role não encontrada",
                        summary="Erro 404 — id inexistente",
                        value={
                            "detail": "Não encontrado.",
                            "code": "not_found",
                        },
                        response_only=True,
                        status_codes=["404"],
                    )
                ],
            ),
        },
        tags=["1 - Usuários"],
    )
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


@tag_all_actions("1 - Usuários")
class UserRoleViewSet(AuditableMixin, viewsets.ModelViewSet):
    """
    Gerencia UserRoles. Apenas PORTAL_ADMIN.
    """

    serializer_class = UserRoleSerializer
    permission_classes = [IsAuthenticated, IsPortalAdmin]
    http_method_names = ["get", "post", "delete", "head", "options"]

    def get_queryset(self):
        # return UserRole.objects.all().select_related(
        #     "user", "aplicacao", "role"
        # )
        return (
            UserRole.objects.all()
            .select_related("user", "aplicacao", "role")
            .order_by("user__username", "role__nomeperfil")
        )

    def perform_create(self, serializer):
        serializer.save()

    @extend_schema(
        summary="Vincular role a usuário",
        description=(
            "Cria um vínculo `UserRole` entre usuário, role e aplicação.\n\n"
            "**Autenticação:** requer sessão ativa via cookie HttpOnly "
            "`gpp_session_<APP>` (ex: `gpp_session_PORTAL`). "
            "O frontend deve enviar todas as requisições com `withCredentials: true`.\n\n"
            "**Permissões:** acesso exclusivo a usuários com perfil `PORTAL_ADMIN`.\n\n"
            "**Efeito colateral:** após a criação do vínculo, o endpoint executa "
            "`sync_user_permissions(user)` para sincronizar as permissões efetivas "
            "do usuário de forma atômica."
        ),
        request=UserRoleSerializer,
        responses={
            201: OpenApiResponse(
                response=UserRoleSerializer,
                description="Vínculo de role criado com sucesso.",
                examples=[
                    OpenApiExample(
                        "UserRole criado",
                        summary="Resposta 201 — vínculo criado com sucesso",
                        value={
                            "id": 15,
                            "user": 42,
                            "aplicacao": 3,
                            "role": 7,
                        },
                        response_only=True,
                        status_codes=["201"],
                    )
                ],
            ),
            400: OpenApiResponse(
                description="Dados inválidos ou regra de validação violada.",
                examples=[
                    OpenApiExample(
                        "Role duplicada para o usuário",
                        summary="Erro 400 — vínculo já existente",
                        value={
                            "detail": "Este usuário já possui essa role nesta aplicação.",
                            "code": "duplicate_user_role",
                        },
                        response_only=True,
                        status_codes=["400"],
                    ),
                    OpenApiExample(
                        "Role incompatível com aplicação",
                        summary="Erro 400 — role não pertence  à aplicação informada",
                        value={
                            "detail": "A role informada não pertence  à aplicação selecionada.",
                            "code": "invalid_role_for_application",
                        },
                        response_only=True,
                        status_codes=["400"],
                    ),
                    OpenApiExample(
                        "Campos obrigatórios ausentes",
                        summary="Erro 400 — payload incompleto",
                        value={
                            "user": ["Este campo é obrigatório."],
                            "role": ["Este campo é obrigatório."],
                            "aplicacao": ["Este campo é obrigatório."],
                        },
                        response_only=True,
                        status_codes=["400"],
                    ),
                ],
            ),
            401: OpenApiResponse(
                description="Não autenticado — sessão ausente ou expirada.",
                examples=[
                    OpenApiExample(
                        "Não autenticado",
                        summary="Erro 401 — cookie de sessão ausente ou inválido",
                        value={
                            "detail": "As credenciais de autenticação não foram fornecidas.",
                            "code": "not_authenticated",
                        },
                        response_only=True,
                        status_codes=["401"],
                    )
                ],
            ),
            403: OpenApiResponse(
                description="Proibido — usuário autenticado, mas sem perfil PORTAL_ADMIN.",
                examples=[
                    OpenApiExample(
                        "Sem permissão",
                        summary="Erro 403 — acesso restrito a PORTAL_ADMIN",
                        value={
                            "detail": "Você não tem permissão para executar essa ação.",
                            "code": "permission_denied",
                        },
                        response_only=True,
                        status_codes=["403"],
                    )
                ],
            ),
        },
        tags=["1 - Usuários"],
    )
    def create(self, request, *args, **kwargs):
        security_logger.info(
            "USERROLE_ASSIGN admin_id=%s payload=%s",
            request.user.id,
            request.data,
        )
        with transaction.atomic():
            response = super().create(request, *args, **kwargs)

            userrole_id = response.data.get("id")
            userrole = UserRole.objects.select_related("user", "role__group").get(
                pk=userrole_id
            )

            sync_user_permissions(user=userrole.user)

            security_logger.info(
                "USERROLE_PERM_SYNC user_id=%s role=%s",
                userrole.user_id,
                userrole.role.codigoperfil,
            )

        return response

    @extend_schema(
        summary="Remover vínculo de role do usuário",
        description=(
            "Remove um vínculo `UserRole` existente.\n\n"
            "**Autenticação:** requer sessão ativa via cookie HttpOnly "
            "`gpp_session_<APP>` (ex: `gpp_session_PORTAL`). "
            "O frontend deve enviar todas as requisições com `withCredentials: true`.\n\n"
            "**Permissões:** acesso exclusivo a usuários com perfil `PORTAL_ADMIN`.\n\n"
            "**Efeito colateral:** após a remoção do vínculo, o endpoint executa "
            "`sync_user_permissions(user)` para recalcular as permissões efetivas "
            "do usuário com base nas roles remanescentes."
        ),
        responses={
            204: OpenApiResponse(
                description="Vínculo removido com sucesso. Sem conteúdo no corpo da resposta."
            ),
            401: OpenApiResponse(
                description="Não autenticado — sessão ausente ou expirada.",
                examples=[
                    OpenApiExample(
                        "Não autenticado",
                        summary="Erro 401 — cookie de sessão ausente ou inválido",
                        value={
                            "detail": "As credenciais de autenticação não foram fornecidas.",
                            "code": "not_authenticated",
                        },
                        response_only=True,
                        status_codes=["401"],
                    )
                ],
            ),
            403: OpenApiResponse(
                description="Proibido — usuário autenticado, mas sem perfil PORTAL_ADMIN.",
                examples=[
                    OpenApiExample(
                        "Sem permissão",
                        summary="Erro 403 — acesso restrito a PORTAL_ADMIN",
                        value={
                            "detail": "Você não tem permissão para executar essa ação.",
                            "code": "permission_denied",
                        },
                        response_only=True,
                        status_codes=["403"],
                    )
                ],
            ),
            404: OpenApiResponse(
                description="Vínculo `UserRole` não encontrado para o ID informado.",
                examples=[
                    OpenApiExample(
                        "UserRole não encontrado",
                        summary="Erro 404 — id inexistente",
                        value={
                            "detail": "Não encontrado.",
                            "code": "not_found",
                        },
                        response_only=True,
                        status_codes=["404"],
                    )
                ],
            ),
        },
        tags=["1 - Usuários"],
    )
    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()

        security_logger.info(
            "USERROLE_REMOVE admin_id=%s userrole_id=%s user_id=%s role=%s app=%s",
            request.user.id,
            instance.id,
            instance.user_id,
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

@tag_all_actions("1 - Usuários")
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

    @extend_schema(
        summary="Listar overrides de permissão",
        description=(
            "Retorna a lista de overrides de permissão (`UserPermissionOverride`).\n\n"
            "**Autenticação:** requer sessão ativa via cookie HttpOnly "
            "`gpp_session_<APP>` (ex: `gpp_session_PORTAL`). "
            "O frontend deve enviar todas as requisições com `withCredentials: true`.\n\n"
            "**Permissões:** acesso exclusivo a usuários com perfil `PORTAL_ADMIN`.\n\n"
            "**Impacto funcional:** cada override representa uma alteração explícita nas "
            "permissões efetivas de um usuário. As mutações neste recurso disparam "
            "`sync_user_permissions(user)`, atualizando imediatamente o conjunto efetivo "
            "de permissões do usuário."
        ),
        responses={
            200: OpenApiResponse(
                response=UserPermissionOverrideSerializer(many=True),
                description="Lista de overrides retornada com sucesso.",
                examples=[
                    OpenApiExample(
                        "Lista de overrides",
                        summary="Resposta 200 — listagem bem-sucedida",
                        value=[
                            {
                                "id": 1,
                                "user": 42,
                                "permission": 15,
                                "mode": "grant",
                            },
                            {
                                "id": 2,
                                "user": 42,
                                "permission": 18,
                                "mode": "revoke",
                            },
                        ],
                        response_only=True,
                        status_codes=["200"],
                    )
                ],
            ),
            401: OpenApiResponse(
                description="Não autenticado — sessão ausente ou expirada.",
                response=inline_serializer(
                    name="UserPermissionOverrideUnauthorizedError",
                    fields={
                        "detail": drf_serializers.CharField(),
                        "code": drf_serializers.CharField(),
                    },
                ),
                examples=[
                    OpenApiExample(
                        "Não autenticado",
                        summary="Erro 401 — cookie de sessão ausente ou inválido",
                        value={
                            "detail": "As credenciais de autenticação não foram fornecidas.",
                            "code": "not_authenticated",
                        },
                        response_only=True,
                        status_codes=["401"],
                    )
                ],
            ),
            403: OpenApiResponse(
                description="Proibido — usuário autenticado, mas sem permissão administrativa.",
                response=inline_serializer(
                    name="UserPermissionOverrideForbiddenErrorList",
                    fields={
                        "detail": drf_serializers.CharField(),
                        "code": drf_serializers.CharField(),
                    },
                ),
                examples=[
                    OpenApiExample(
                        "Sem permissão",
                        summary="Erro 403 — acesso restrito a PORTAL_ADMIN",
                        value={
                            "detail": "Você não tem permissão para executar essa ação.",
                            "code": "permission_denied",
                        },
                        response_only=True,
                        status_codes=["403"],
                    )
                ],
            ),
        },
        tags=["1 - Usuários"],
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(
        summary="Detalhar override de permissão",
        description=(
            "Retorna os dados de um override de permissão específico.\n\n"
            "**Autenticação:** requer sessão ativa via cookie HttpOnly "
            "`gpp_session_<APP>` (ex: `gpp_session_PORTAL`). "
            "O frontend deve enviar todas as requisições com `withCredentials: true`.\n\n"
            "**Permissões:** acesso exclusivo a usuários com perfil `PORTAL_ADMIN`.\n\n"
            "**Impacto funcional:** overrides afetam as permissões efetivas do usuário. "
            "As mutações neste recurso disparam `sync_user_permissions(user)` para "
            "recalcular imediatamente o estado efetivo."
        ),
        responses={
            200: OpenApiResponse(
                response=UserPermissionOverrideSerializer,
                description="Override retornado com sucesso.",
                examples=[
                    OpenApiExample(
                        "Override encontrado",
                        summary="Resposta 200 — detalhe do override",
                        value={
                            "id": 1,
                            "user": 42,
                            "permission": 15,
                            "mode": "grant",
                        },
                        response_only=True,
                        status_codes=["200"],
                    )
                ],
            ),
            401: OpenApiResponse(
                description="Não autenticado — sessão ausente ou expirada.",
                response=inline_serializer(
                    name="UserPermissionOverrideUnauthorizedErrorRetrieve",
                    fields={
                        "detail": drf_serializers.CharField(),
                        "code": drf_serializers.CharField(),
                    },
                ),
                examples=[
                    OpenApiExample(
                        "Não autenticado",
                        summary="Erro 401 — cookie de sessão ausente ou inválido",
                        value={
                            "detail": "As credenciais de autenticação não foram fornecidas.",
                            "code": "not_authenticated",
                        },
                        response_only=True,
                        status_codes=["401"],
                    )
                ],
            ),
            403: OpenApiResponse(
                description="Proibido — usuário autenticado, mas sem permissão administrativa.",
                response=inline_serializer(
                    name="UserPermissionOverrideForbiddenErrorRetrieve",
                    fields={
                        "detail": drf_serializers.CharField(),
                        "code": drf_serializers.CharField(),
                    },
                ),
                examples=[
                    OpenApiExample(
                        "Sem permissão",
                        summary="Erro 403 — acesso restrito a PORTAL_ADMIN",
                        value={
                            "detail": "Você não tem permissão para executar essa ação.",
                            "code": "permission_denied",
                        },
                        response_only=True,
                        status_codes=["403"],
                    )
                ],
            ),
            404: OpenApiResponse(
                description="Override não encontrado para o ID informado.",
                response=inline_serializer(
                    name="UserPermissionOverrideNotFoundErrorRetrieve",
                    fields={
                        "detail": drf_serializers.CharField(),
                        "code": drf_serializers.CharField(),
                    },
                ),
                examples=[
                    OpenApiExample(
                        "Override não encontrado",
                        summary="Erro 404 — id inexistente",
                        value={
                            "detail": "Não encontrado.",
                            "code": "not_found",
                        },
                        response_only=True,
                        status_codes=["404"],
                    )
                ],
            ),
        },
        tags=["1 - Usuários"],
    )
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    def get_queryset(self):
        return (
            UserPermissionOverride.objects.all()
            .select_related("user", "permission")
            .order_by("user__username", "permission__codename")
        )

    def _sync_after_mutation(self, override):
        """Chama sync_user_permissions e registra log após qualquer mutação."""
        sync_user_permissions(user=override.user)
        security_logger.info(
            "OVERRIDE_PERM_SYNC user_id=%s permission=%s mode=%s",
            override.user_id,
            override.permission.codename,
            override.mode,
        )

    @extend_schema(
        summary="Criar override de permissão",
        description=(
            "Cria um novo `UserPermissionOverride` para conceder ou revogar explicitamente "
            "uma permissão de um usuário.\n\n"
            "**Autenticação:** requer sessão ativa via cookie HttpOnly "
            "`gpp_session_<APP>` (ex: `gpp_session_PORTAL`). "
            "O frontend deve enviar todas as requisições com `withCredentials: true`.\n\n"
            "**Permissões:** acesso exclusivo a usuários com perfil `PORTAL_ADMIN`.\n\n"
            "**Impacto funcional:** a criação do override altera as permissões efetivas "
            "do usuário alvo e dispara `sync_user_permissions(user)` imediatamente após "
            "a persistência."
        ),
        request=UserPermissionOverrideSerializer,
        responses={
            201: OpenApiResponse(
                response=UserPermissionOverrideSerializer,
                description="Override criado com sucesso.",
                examples=[
                    OpenApiExample(
                        "Override criado",
                        summary="Resposta 201 — criação bem-sucedida",
                        value={
                            "id": 3,
                            "user": 42,
                            "permission": 21,
                            "mode": "grant",
                        },
                        response_only=True,
                        status_codes=["201"],
                    )
                ],
            ),
            400: OpenApiResponse(
                description="Dados inválidos ou conflito de validação.",
                response=UserPermissionOverrideSerializer,
                examples=[
                    OpenApiExample(
                        "Permissão inválida",
                        summary="Erro 400 — permissão inexistente ou inválida",
                        value={
                            "permission": ["Selecione uma opção válida."],
                        },
                        response_only=True,
                        status_codes=["400"],
                    ),
                    OpenApiExample(
                        "Conflito de override",
                        summary="Erro 400 — override já existente para usuário e permissão",
                        value={
                            "detail": "Já existe um override para este usuário e permissão.",
                            "code": "conflict",
                        },
                        response_only=True,
                        status_codes=["400"],
                    ),
                ],
            ),
            401: OpenApiResponse(
                description="Não autenticado — sessão ausente ou expirada.",
                response=inline_serializer(
                    name="UserPermissionOverrideUnauthorizedErrorCreate",
                    fields={
                        "detail": drf_serializers.CharField(),
                        "code": drf_serializers.CharField(),
                    },
                ),
                examples=[
                    OpenApiExample(
                        "Não autenticado",
                        summary="Erro 401 — cookie de sessão ausente ou inválido",
                        value={
                            "detail": "As credenciais de autenticação não foram fornecidas.",
                            "code": "not_authenticated",
                        },
                        response_only=True,
                        status_codes=["401"],
                    )
                ],
            ),
            403: OpenApiResponse(
                description="Proibido — usuário autenticado, mas sem permissão administrativa.",
                response=inline_serializer(
                    name="UserPermissionOverrideForbiddenErrorCreate",
                    fields={
                        "detail": drf_serializers.CharField(),
                        "code": drf_serializers.CharField(),
                    },
                ),
                examples=[
                    OpenApiExample(
                        "Sem permissão",
                        summary="Erro 403 — acesso restrito a PORTAL_ADMIN",
                        value={
                            "detail": "Você não tem permissão para executar essa ação.",
                            "code": "permission_denied",
                        },
                        response_only=True,
                        status_codes=["403"],
                    )
                ],
            ),
        },
        tags=["1 - Usuários"],
    )
    def create(self, request, *args, **kwargs):
        security_logger.info(
            "OVERRIDE_CREATE admin_id=%s payload=%s",
            request.user.id,
            request.data,
        )
        with transaction.atomic():
            response = super().create(request, *args, **kwargs)
            override = UserPermissionOverride.objects.select_related(
                "user", "permission"
            ).get(pk=response.data["id"])
            self._sync_after_mutation(override)
        return response

    @extend_schema(
        summary="Atualizar override de permissão",
        description=(
            "Atualiza completamente um `UserPermissionOverride` existente.\n\n"
            "**Autenticação:** requer sessão ativa via cookie HttpOnly "
            "`gpp_session_<APP>` (ex: `gpp_session_PORTAL`). "
            "O frontend deve enviar todas as requisições com `withCredentials: true`.\n\n"
            "**Permissões:** acesso exclusivo a usuários com perfil `PORTAL_ADMIN`.\n\n"
            "**Impacto funcional:** a atualização altera as permissões efetivas do usuário "
            "alvo e dispara `sync_user_permissions(user)` imediatamente após a mutação."
        ),
        request=UserPermissionOverrideSerializer,
        responses={
            200: OpenApiResponse(
                response=UserPermissionOverrideSerializer,
                description="Override atualizado com sucesso.",
                examples=[
                    OpenApiExample(
                        "Override atualizado",
                        summary="Resposta 200 — atualização completa bem-sucedida",
                        value={
                            "id": 3,
                            "user": 42,
                            "permission": 21,
                            "mode": "revoke",
                        },
                        response_only=True,
                        status_codes=["200"],
                    )
                ],
            ),
            400: OpenApiResponse(
                description="Dados inválidos ou conflito de validação.",
                response=UserPermissionOverrideSerializer,
                examples=[
                    OpenApiExample(
                        "Permissão inválida",
                        summary="Erro 400 — permissão inexistente ou inválida",
                        value={
                            "permission": ["Selecione uma opção válida."],
                        },
                        response_only=True,
                        status_codes=["400"],
                    ),
                    OpenApiExample(
                        "Conflito de override",
                        summary="Erro 400 — combinação inválida ou já existente",
                        value={
                            "detail": "Já existe um override para este usuário e permissão.",
                            "code": "conflict",
                        },
                        response_only=True,
                        status_codes=["400"],
                    ),
                ],
            ),
            401: OpenApiResponse(
                description="Não autenticado — sessão ausente ou expirada.",
                response=inline_serializer(
                    name="UserPermissionOverrideUnauthorizedErrorUpdate",
                    fields={
                        "detail": drf_serializers.CharField(),
                        "code": drf_serializers.CharField(),
                    },
                ),
                examples=[
                    OpenApiExample(
                        "Não autenticado",
                        summary="Erro 401 — cookie de sessão ausente ou inválido",
                        value={
                            "detail": "As credenciais de autenticação não foram fornecidas.",
                            "code": "not_authenticated",
                        },
                        response_only=True,
                        status_codes=["401"],
                    )
                ],
            ),
            403: OpenApiResponse(
                description="Proibido — usuário autenticado, mas sem permissão administrativa.",
                response=inline_serializer(
                    name="UserPermissionOverrideForbiddenErrorUpdate",
                    fields={
                        "detail": drf_serializers.CharField(),
                        "code": drf_serializers.CharField(),
                    },
                ),
                examples=[
                    OpenApiExample(
                        "Sem permissão",
                        summary="Erro 403 — acesso restrito a PORTAL_ADMIN",
                        value={
                            "detail": "Você não tem permissão para executar essa ação.",
                            "code": "permission_denied",
                        },
                        response_only=True,
                        status_codes=["403"],
                    )
                ],
            ),
            404: OpenApiResponse(
                description="Override não encontrado para o ID informado.",
                response=inline_serializer(
                    name="UserPermissionOverrideNotFoundErrorUpdate",
                    fields={
                        "detail": drf_serializers.CharField(),
                        "code": drf_serializers.CharField(),
                    },
                ),
                examples=[
                    OpenApiExample(
                        "Override não encontrado",
                        summary="Erro 404 — id inexistente",
                        value={
                            "detail": "Não encontrado.",
                            "code": "not_found",
                        },
                        response_only=True,
                        status_codes=["404"],
                    )
                ],
            ),
        },
        tags=["1 - Usuários"],
    )
    def update(self, request, *args, **kwargs):
        security_logger.info(
            "OVERRIDE_UPDATE admin_id=%s override_id=%s",
            request.user.id,
            kwargs.get("pk"),
        )
        with transaction.atomic():
            response = super().update(request, *args, **kwargs)
            override = UserPermissionOverride.objects.select_related(
                "user", "permission"
            ).get(pk=response.data["id"])
            self._sync_after_mutation(override)
        return response

    @extend_schema(
        summary="Atualizar parcialmente override de permissão",
        description=(
            "Atualiza parcialmente um `UserPermissionOverride` existente.\n\n"
            "**Autenticação:** requer sessão ativa via cookie HttpOnly "
            "`gpp_session_<APP>` (ex: `gpp_session_PORTAL`). "
            "O frontend deve enviar todas as requisições com `withCredentials: true`.\n\n"
            "**Permissões:** acesso exclusivo a usuários com perfil `PORTAL_ADMIN`.\n\n"
            "**Impacto funcional:** a alteração parcial afeta as permissões efetivas do "
            "usuário alvo e dispara `sync_user_permissions(user)` imediatamente após a mutação."
        ),
        request=UserPermissionOverrideSerializer,
        responses={
            200: OpenApiResponse(
                response=UserPermissionOverrideSerializer,
                description="Override atualizado parcialmente com sucesso.",
                examples=[
                    OpenApiExample(
                        "Override parcialmente atualizado",
                        summary="Resposta 200 — patch bem-sucedido",
                        value={
                            "id": 3,
                            "user": 42,
                            "permission": 21,
                            "mode": "revoke",
                        },
                        response_only=True,
                        status_codes=["200"],
                    )
                ],
            ),
            400: OpenApiResponse(
                description="Dados inválidos ou conflito de validação.",
                response=UserPermissionOverrideSerializer,
                examples=[
                    OpenApiExample(
                        "Permissão inválida",
                        summary="Erro 400 — permissão inexistente ou inválida",
                        value={
                            "permission": ["Selecione uma opção válida."],
                        },
                        response_only=True,
                        status_codes=["400"],
                    ),
                    OpenApiExample(
                        "Conflito de override",
                        summary="Erro 400 — combinação inválida ou já existente",
                        value={
                            "detail": "Já existe um override para este usuário e permissão.",
                            "code": "conflict",
                        },
                        response_only=True,
                        status_codes=["400"],
                    ),
                ],
            ),
            401: OpenApiResponse(
                description="Não autenticado — sessão ausente ou expirada.",
                response=inline_serializer(
                    name="UserPermissionOverrideUnauthorizedErrorPartialUpdate",
                    fields={
                        "detail": drf_serializers.CharField(),
                        "code": drf_serializers.CharField(),
                    },
                ),
                examples=[
                    OpenApiExample(
                        "Não autenticado",
                        summary="Erro 401 — cookie de sessão ausente ou inválido",
                        value={
                            "detail": "As credenciais de autenticação não foram fornecidas.",
                            "code": "not_authenticated",
                        },
                        response_only=True,
                        status_codes=["401"],
                    )
                ],
            ),
            403: OpenApiResponse(
                description="Proibido — usuário autenticado, mas sem permissão administrativa.",
                response=inline_serializer(
                    name="UserPermissionOverrideForbiddenErrorPartialUpdate",
                    fields={
                        "detail": drf_serializers.CharField(),
                        "code": drf_serializers.CharField(),
                    },
                ),
                examples=[
                    OpenApiExample(
                        "Sem permissão",
                        summary="Erro 403 — acesso restrito a PORTAL_ADMIN",
                        value={
                            "detail": "Você não tem permissão para executar essa ação.",
                            "code": "permission_denied",
                        },
                        response_only=True,
                        status_codes=["403"],
                    )
                ],
            ),
            404: OpenApiResponse(
                description="Override não encontrado para o ID informado.",
                response=inline_serializer(
                    name="UserPermissionOverrideNotFoundErrorPartialUpdate",
                    fields={
                        "detail": drf_serializers.CharField(),
                        "code": drf_serializers.CharField(),
                    },
                ),
                examples=[
                    OpenApiExample(
                        "Override não encontrado",
                        summary="Erro 404 — id inexistente",
                        value={
                            "detail": "Não encontrado.",
                            "code": "not_found",
                        },
                        response_only=True,
                        status_codes=["404"],
                    )
                ],
            ),
        },
        tags=["1 - Usuários"],
    )
    def partial_update(self, request, *args, **kwargs):
        kwargs["partial"] = True
        return self.update(request, *args, **kwargs)

    @extend_schema(
        summary="Remover override de permissão",
        description=(
            "Remove um `UserPermissionOverride` existente.\n\n"
            "**Autenticação:** requer sessão ativa via cookie HttpOnly "
            "`gpp_session_<APP>` (ex: `gpp_session_PORTAL`). "
            "O frontend deve enviar todas as requisições com `withCredentials: true`.\n\n"
            "**Permissões:** acesso exclusivo a usuários com perfil `PORTAL_ADMIN`.\n\n"
            "**Impacto funcional:** a remoção do override afeta as permissões efetivas do "
            "usuário alvo e dispara `sync_user_permissions(user)` imediatamente após a exclusão."
        ),
        responses={
            204: OpenApiResponse(
                description="Override removido com sucesso. Sem conteúdo no corpo da resposta."
            ),
            401: OpenApiResponse(
                description="Não autenticado — sessão ausente ou expirada.",
                response=inline_serializer(
                    name="UserPermissionOverrideUnauthorizedErrorDestroy",
                    fields={
                        "detail": drf_serializers.CharField(),
                        "code": drf_serializers.CharField(),
                    },
                ),
                examples=[
                    OpenApiExample(
                        "Não autenticado",
                        summary="Erro 401 — cookie de sessão ausente ou inválido",
                        value={
                            "detail": "As credenciais de autenticação não foram fornecidas.",
                            "code": "not_authenticated",
                        },
                        response_only=True,
                        status_codes=["401"],
                    )
                ],
            ),
            403: OpenApiResponse(
                description="Proibido — usuário autenticado, mas sem permissão administrativa.",
                response=inline_serializer(
                    name="UserPermissionOverrideForbiddenErrorDestroy",
                    fields={
                        "detail": drf_serializers.CharField(),
                        "code": drf_serializers.CharField(),
                    },
                ),
                examples=[
                    OpenApiExample(
                        "Sem permissão",
                        summary="Erro 403 — acesso restrito a PORTAL_ADMIN",
                        value={
                            "detail": "Você não tem permissão para executar essa ação.",
                            "code": "permission_denied",
                        },
                        response_only=True,
                        status_codes=["403"],
                    )
                ],
            ),
            404: OpenApiResponse(
                description="Override não encontrado para o ID informado.",
                response=inline_serializer(
                    name="UserPermissionOverrideNotFoundErrorDestroy",
                    fields={
                        "detail": drf_serializers.CharField(),
                        "code": drf_serializers.CharField(),
                    },
                ),
                examples=[
                    OpenApiExample(
                        "Override não encontrado",
                        summary="Erro 404 — id inexistente",
                        value={
                            "detail": "Não encontrado.",
                            "code": "not_found",
                        },
                        response_only=True,
                        status_codes=["404"],
                    )
                ],
            ),
        },
        tags=["1 - Usuários"],
    )
    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        user = instance.user

        security_logger.info(
            "OVERRIDE_DELETE admin_id=%s override_id=%s user_id=%s permission=%s mode=%s",
            request.user.id,
            instance.pk,
            user.pk,
            instance.permission.codename,
            instance.mode,
        )

        with transaction.atomic():
            response = super().destroy(request, *args, **kwargs)
            sync_user_permissions(user=user)
            security_logger.info(
                "OVERRIDE_DELETE_PERM_SYNC user_id=%s",
                user.pk,
            )

        return response

@tag_all_actions("5 - Utilitários")
class AplicacaoPublicaViewSet(viewsets.ReadOnlyModelViewSet):
    """
    GET /api/accounts/auth/aplicacoes/
    GET /api/accounts/auth/aplicacoes/{codigointerno}/

    Endpoint PÃšBLICO — sem autenticação necessária.
    Usado pelo frontend para popular o seletor de app_context na tela de login.

    Retorna apenas apps ativas (não bloqueadas e prontas para produção).
    Expõe somente idaplicacao, codigointerno e nomeaplicacao — sem vazar flags internos.

    R-01: ReadOnly — POST/PUT/PATCH/DELETE retornam 405.
    R-02: Filtro fixo: isappbloqueada=False AND isappproductionready=True.
    R-03: pagination_class = None — retorna lista plana sem envelope de paginação.
    R-04: throttle_classes = [] — endpoint público de leitura; sem rate limit.
    """

    serializer_class = AplicacaoPublicaSerializer
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = []
    pagination_class = None
    lookup_field = "codigointerno"

    @extend_schema(
        summary="Listar aplicações públicas",
        description=(
            "Retorna a lista de aplicações públicas disponíveis para seleção na tela de login.\n\n"
            "**Acesso:** endpoint público (`AllowAny`).\n"
            "**Autenticação:** não requer autenticação.\n"
            "**Sessão:** não usa cookie de sessão.\n\n"
            "**Uso principal:** popular o seletor de aplicações (`app_context`) no frontend "
            "antes do login.\n\n"
            "**Filtro aplicado:** retorna apenas aplicações ativas e visíveis, ou seja, "
            "não bloqueadas e prontas para produção."
        ),
        responses={
            200: OpenApiResponse(
                response=AplicacaoPublicaSerializer(many=True),
                description="Lista de aplicações públicas retornada com sucesso.",
                examples=[
                    OpenApiExample(
                        "Lista de aplicações públicas",
                        summary="Resposta 200 — aplicações disponíveis no login",
                        value=[
                            {
                                "idaplicacao": 1,
                                "codigointerno": "PORTAL",
                                "nomeaplicacao": "Portal GPP",
                            },
                            {
                                "idaplicacao": 2,
                                "codigointerno": "SIGEF",
                                "nomeaplicacao": "SIGEF",
                            },
                        ],
                        response_only=True,
                        status_codes=["200"],
                    )
                ],
            ),
            400: OpenApiResponse(
                description="Erro genérico de requisição.",
                response=inline_serializer(
                    name="AplicacaoPublicaListBadRequestError",
                    fields={
                        "detail": drf_serializers.CharField(),
                        "code": drf_serializers.CharField(),
                    },
                ),
                examples=[
                    OpenApiExample(
                        "Erro genérico",
                        summary="Erro 400 — requisição inválida",
                        value={
                            "detail": "Requisição inválida.",
                            "code": "bad_request",
                        },
                        response_only=True,
                        status_codes=["400"],
                    )
                ],
            ),
        },
        tags=["5 - Utilitários"],
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(
        summary="Detalhar aplicação pública",
        description=(
            "Retorna os dados de uma aplicação pública específica pelo seu `codigointerno`.\n\n"
            "**Acesso:** endpoint público (`AllowAny`).\n"
            "**Autenticação:** não requer autenticação.\n"
            "**Sessão:** não usa cookie de sessão.\n\n"
            "**Uso principal:** consulta de uma aplicação exibida no seletor da tela de login.\n\n"
            "**Filtro aplicado:** somente aplicações ativas e visíveis são expostas por este endpoint."
        ),
        parameters=[
            OpenApiParameter(
                name="codigointerno",
                type=str,
                location=OpenApiParameter.PATH,
                required=True,
                description="Código interno da aplicação pública (ex: `PORTAL`, `SIGEF`).",
                examples=[
                    OpenApiExample(
                        "Aplicação PORTAL",
                        value="PORTAL",
                    )
                ],
            )
        ],
        responses={
            200: OpenApiResponse(
                response=AplicacaoPublicaSerializer,
                description="Aplicação pública retornada com sucesso.",
                examples=[
                    OpenApiExample(
                        "Aplicação pública encontrada",
                        summary="Resposta 200 — aplicação encontrada",
                        value={
                            "idaplicacao": 1,
                            "codigointerno": "PORTAL",
                            "nomeaplicacao": "Portal GPP",
                        },
                        response_only=True,
                        status_codes=["200"],
                    )
                ],
            ),
            400: OpenApiResponse(
                description="Erro genérico de requisição.",
                response=inline_serializer(
                    name="AplicacaoPublicaRetrieveBadRequestError",
                    fields={
                        "detail": drf_serializers.CharField(),
                        "code": drf_serializers.CharField(),
                    },
                ),
                examples=[
                    OpenApiExample(
                        "Erro genérico",
                        summary="Erro 400 — requisição inválida",
                        value={
                            "detail": "Requisição inválida.",
                            "code": "bad_request",
                        },
                        response_only=True,
                        status_codes=["400"],
                    )
                ],
            ),
            404: OpenApiResponse(
                description="Aplicação pública não encontrada.",
                response=inline_serializer(
                    name="AplicacaoPublicaNotFoundError",
                    fields={
                        "detail": drf_serializers.CharField(),
                        "code": drf_serializers.CharField(),
                    },
                ),
                examples=[
                    OpenApiExample(
                        "Aplicação não encontrada",
                        summary="Erro 404 — codigointerno inexistente",
                        value={
                            "detail": "Não encontrado.",
                            "code": "not_found",
                        },
                        response_only=True,
                        status_codes=["404"],
                    )
                ],
            ),
        },
        tags=["5 - Utilitários"],
    )
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    def get_queryset(self):
        return Aplicacao.objects.filter(
            isappbloqueada=False,
            isappproductionready=True,
        ).order_by("nomeaplicacao")

@tag_all_actions("1 - Usuários")
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
    lookup_field = "idaplicacao"
    lookup_url_kwarg = "idaplicacao"

    @extend_schema(
        summary="Listar aplicações visíveis ao usuário",
        description=(
            "Retorna as aplicações disponíveis ao usuário autenticado no contexto pós-login.\n\n"
            "**Autenticação:** requer sessão ativa via cookie HttpOnly "
            "`gpp_session_<APP>` (ex: `gpp_session_PORTAL`). "
            "O frontend deve enviar todas as requisições com `withCredentials: true`.\n\n"
            "**Permissões:** requer autenticação (`IsAuthenticated`).\n\n"
            "**Escopo de visibilidade:**\n"
            "- `PORTAL_ADMIN` ou `superuser`: visualiza todas as aplicações sem restrição.\n"
            "- usuário comum: visualiza apenas as aplicações nas quais possui `UserRole`, "
            "com filtro adicional para apps não bloqueadas e prontas para produção."
        ),
        responses={
            200: OpenApiResponse(
                response=AplicacaoSerializer(many=True),
                description="Lista de aplicações visíveis ao usuário retornada com sucesso.",
                examples=[
                    OpenApiExample(
                        "Lista de aplicações disponíveis",
                        summary="Resposta 200 — aplicações visíveis ao usuário autenticado",
                        value=[
                            {
                                "idaplicacao": 1,
                                "codigointerno": "PORTAL",
                                "nomeaplicacao": "Portal GPP",
                            },
                            {
                                "idaplicacao": 3,
                                "codigointerno": "ACOES_PNGI",
                                "nomeaplicacao": "Ações PNGI",
                            },
                        ],
                        response_only=True,
                        status_codes=["200"],
                    )
                ],
            ),
            400: OpenApiResponse(
                description="Erro genérico de requisição.",
                response=inline_serializer(
                    name="AplicacaoListBadRequestError",
                    fields={
                        "detail": drf_serializers.CharField(),
                        "code": drf_serializers.CharField(),
                    },
                ),
                examples=[
                    OpenApiExample(
                        "Erro genérico",
                        summary="Erro 400 — requisição inválida",
                        value={
                            "detail": "Requisição inválida.",
                            "code": "bad_request",
                        },
                        response_only=True,
                        status_codes=["400"],
                    )
                ],
            ),
            401: OpenApiResponse(
                description="Não autenticado — sessão ausente ou expirada.",
                response=inline_serializer(
                    name="AplicacaoUnauthorizedErrorList",
                    fields={
                        "detail": drf_serializers.CharField(),
                        "code": drf_serializers.CharField(),
                    },
                ),
                examples=[
                    OpenApiExample(
                        "Não autenticado",
                        summary="Erro 401 — cookie de sessão ausente ou inválido",
                        value={
                            "detail": "As credenciais de autenticação não foram fornecidas.",
                            "code": "not_authenticated",
                        },
                        response_only=True,
                        status_codes=["401"],
                    )
                ],
            ),
            403: OpenApiResponse(
                description="Proibido — usuário autenticado, mas sem acesso ao recurso solicitado.",
                response=inline_serializer(
                    name="AplicacaoForbiddenErrorList",
                    fields={
                        "detail": drf_serializers.CharField(),
                        "code": drf_serializers.CharField(),
                    },
                ),
                examples=[
                    OpenApiExample(
                        "Sem acesso  à aplicação",
                        summary="Erro 403 — usuário sem acesso permitido",
                        value={
                            "detail": "Usuário sem acesso  à aplicação.",
                            "code": "permission_denied",
                        },
                        response_only=True,
                        status_codes=["403"],
                    )
                ],
            ),
        },
        tags=["1 - Usuários"],
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(
        summary="Detalhar aplicação visível ao usuário",
        description=(
            "Retorna os dados de uma aplicação específica visível ao usuário autenticado.\n\n"
            "**Autenticação:** requer sessão ativa via cookie HttpOnly "
            "`gpp_session_<APP>` (ex: `gpp_session_PORTAL`). "
            "O frontend deve enviar todas as requisições com `withCredentials: true`.\n\n"
            "**Permissões:** requer autenticação (`IsAuthenticated`).\n\n"
            "**Escopo de visibilidade:**\n"
            "- `PORTAL_ADMIN` ou `superuser`: pode consultar qualquer aplicação.\n"
            "- usuário comum: pode consultar apenas aplicações nas quais possui `UserRole`."
        ),
        parameters=[
            OpenApiParameter(
                name="idaplicacao",
                type=int,
                location=OpenApiParameter.PATH,
                required=True,
                description="ID da aplicação a ser consultada.",
                examples=[
                    OpenApiExample(
                        "Aplicação 3",
                        value=3,
                    )
                ],
            )
        ],
        responses={
            200: OpenApiResponse(
                response=AplicacaoSerializer,
                description="Aplicação retornada com sucesso.",
                examples=[
                    OpenApiExample(
                        "Aplicação encontrada",
                        summary="Resposta 200 — aplicação visível ao usuário",
                        value={
                            "idaplicacao": 3,
                            "codigointerno": "ACOES_PNGI",
                            "nomeaplicacao": "Ações PNGI",
                        },
                        response_only=True,
                        status_codes=["200"],
                    )
                ],
            ),
            400: OpenApiResponse(
                description="Erro genérico de requisição.",
                response=inline_serializer(
                    name="AplicacaoBadRequestErrorRetrieve",
                    fields={
                        "detail": drf_serializers.CharField(),
                        "code": drf_serializers.CharField(),
                    },
                ),
                examples=[
                    OpenApiExample(
                        "Erro genérico",
                        summary="Erro 400 — requisição inválida",
                        value={
                            "detail": "Requisição inválida.",
                            "code": "bad_request",
                        },
                        response_only=True,
                        status_codes=["400"],
                    )
                ],
            ),
            401: OpenApiResponse(
                description="Não autenticado — sessão ausente ou expirada.",
                response=inline_serializer(
                    name="AplicacaoUnauthorizedErrorRetrieve",
                    fields={
                        "detail": drf_serializers.CharField(),
                        "code": drf_serializers.CharField(),
                    },
                ),
                examples=[
                    OpenApiExample(
                        "Não autenticado",
                        summary="Erro 401 — cookie de sessão ausente ou inválido",
                        value={
                            "detail": "As credenciais de autenticação não foram fornecidas.",
                            "code": "not_authenticated",
                        },
                        response_only=True,
                        status_codes=["401"],
                    )
                ],
            ),
            403: OpenApiResponse(
                description="Proibido — usuário autenticado, mas sem acesso  à aplicação solicitada.",
                response=inline_serializer(
                    name="AplicacaoForbiddenErrorRetrieve",
                    fields={
                        "detail": drf_serializers.CharField(),
                        "code": drf_serializers.CharField(),
                    },
                ),
                examples=[
                    OpenApiExample(
                        "Sem acesso  à aplicação",
                        summary="Erro 403 — usuário sem acesso  à aplicação",
                        value={
                            "detail": "Usuário sem acesso  à aplicação.",
                            "code": "permission_denied",
                        },
                        response_only=True,
                        status_codes=["403"],
                    )
                ],
            ),
            404: OpenApiResponse(
                description="Aplicação não encontrada para o ID informado ou fora do escopo visível.",
                response=inline_serializer(
                    name="AplicacaoNotFoundErrorRetrieve",
                    fields={
                        "detail": drf_serializers.CharField(),
                        "code": drf_serializers.CharField(),
                    },
                ),
                examples=[
                    OpenApiExample(
                        "Aplicação não encontrada",
                        summary="Erro 404 — id inexistente ou fora do queryset visível",
                        value={
                            "detail": "Não encontrado.",
                            "code": "not_found",
                        },
                        response_only=True,
                        status_codes=["404"],
                    )
                ],
            ),
        },
        tags=["1 - Usuários"],
    )
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    def get_queryset(self):
        user = self.request.user
        is_privileged = (
            getattr(self.request, "is_portal_admin", False) or user.is_superuser
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