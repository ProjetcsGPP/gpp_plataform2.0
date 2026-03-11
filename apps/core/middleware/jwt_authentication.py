"""
JWTAuthenticationMiddleware

Responsabilidade:
  Valida o Bearer token JWT na camada de middleware,
  ANTES que o RoleContextMiddleware tente carregar roles.

O que faz:
  - Extrai o token do header Authorization
  - Decodifica e valida a assinatura RS256
  - Verifica se a sessão (jti) não foi revogada (anti-replay)
  - Verifica se UserProfile.status_usuario = 1 (ativo); se inativo → 401 user_inactive
  - Injeta request.user autenticado e request.token_jti
  - Rotas isentas (AUTHORIZATION_EXEMPT_PATHS) passam direto;
    se houver token válido nelas, token_jti é injetado mesmo assim

Importante:
  Não substitui a autenticação do DRF — ambas coexistem.
  Este middleware garante que request.user está populado
  antes dos middlewares seguintes (RoleContext, Authorization).
"""
import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core.cache import cache
from django.http import JsonResponse
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.tokens import AccessToken

security_logger = logging.getLogger("gpp.security")
User = get_user_model()

EXEMPT_PATHS = getattr(
    settings,
    "AUTHORIZATION_EXEMPT_PATHS",
    ["/api/auth/token/", "/api/auth/token/refresh/", "/admin/", "/api/health/"],
)


class JWTAuthenticationMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Rotas isentas passam sem validação completa,
        # mas ainda tentamos injetar token_jti se token presente
        if self._is_exempt(request.path):
            self._try_inject_jti(request)
            return self.get_response(request)

        # Tenta autenticar via JWT; pode retornar JsonResponse em caso de erro de negócio
        result = self._authenticate(request)
        if result is not None:
            return result  # ex: 401 user_inactive

        return self.get_response(request)

    def _is_exempt(self, path):
        return any(path.startswith(p) for p in EXEMPT_PATHS)

    def _try_inject_jti(self, request):
        """
        Em rotas isentas, tenta injetar token_jti se houver token válido,
        sem bloquear a request em caso de falha.
        """
        raw_token = self._get_raw_token(request)
        if not raw_token:
            return
        try:
            validated = AccessToken(raw_token)
            jti = validated.get("jti")
            if jti:
                request.token_jti = jti
        except (InvalidToken, TokenError):
            pass

    def _authenticate(self, request):
        """
        Tenta extrair e validar o JWT.
        Em caso de sucesso injeta request.user e request.token_jti e loga LOGIN_SUCCESS.
        Em caso de usuário inativo retorna JsonResponse 401.
        Em caso de falha técnica mantém AnonymousUser (o AuthorizationMiddleware bloqueia).
        """
        raw_token = self._get_raw_token(request)
        if not raw_token:
            return None

        try:
            validated = AccessToken(raw_token)
        except (InvalidToken, TokenError) as exc:
            security_logger.warning(
                "JWT_INVALID path=%s error=%s",
                request.path, str(exc),
            )
            return None

        jti = validated.get("jti")
        user_id = validated.get("user_id")

        # Verifica revogação de sessão (anti-replay)
        if jti and self._is_revoked(jti):
            security_logger.warning(
                "JWT_REVOKED user_id=%s jti=%s path=%s",
                user_id, jti, request.path,
            )
            return None  # AnonymousUser → AuthorizationMiddleware bloqueia

        # Carrega o usuário
        try:
            user = User.objects.select_related("profile").get(pk=user_id, is_active=True)
        except User.DoesNotExist:
            security_logger.warning(
                "JWT_USER_NOT_FOUND user_id=%s path=%s",
                user_id, request.path,
            )
            return None

        # Verifica status_usuario no profile (1 = ativo)
        profile = getattr(user, "profile", None)
        if profile is not None and getattr(profile, "status_usuario", 1) != 1:
            security_logger.warning(
                "JWT_USER_INACTIVE user_id=%s path=%s reason=user_inactive",
                user_id, request.path,
            )
            return JsonResponse(
                {
                    "success": False,
                    "status_code": 401,
                    "errors": {
                        "code": "user_inactive",
                        "detail": "Usuário inativo. Contate o administrador.",
                    },
                },
                status=401,
            )

        # Injeta no request
        request.user = user
        request.token_jti = jti
        request.is_portal_admin = validated.get("is_portal_admin", False)

        security_logger.info(
            "LOGIN_SUCCESS user_id=%s jti=%s path=%s",
            user.id, jti, request.path,
        )

        return None

    @staticmethod
    def _get_raw_token(request):
        auth_header = request.META.get("HTTP_AUTHORIZATION", "")
        parts = auth_header.split()
        if len(parts) == 2 and parts[0].lower() == "bearer":
            return parts[1]
        return None

    @staticmethod
    def _is_revoked(jti):
        """
        Verifica revogação usando cache Memcached primeiro,
        depois consulta o banco se necessidade.
        """
        cache_key = f"session_revoked:{jti}"
        cached = cache.get(cache_key)

        if cached is not None:
            return cached  # True = revogado, False = ativo (em cache)

        # Cache miss: consulta banco
        from apps.accounts.models import AccountsSession
        try:
            session = AccountsSession.objects.get(jti=jti)
            is_revoked = session.revoked
        except AccountsSession.DoesNotExist:
            # Sessão não registrada — token válido mas sem registro de sessão
            # Considerado não-revogado para não bloquear tokens pré-existentes
            is_revoked = False

        # Cacheia resultado por 60s
        cache.set(cache_key, is_revoked, 60)
        return is_revoked
