"""
TokenService Centralizado para IAM
Implementa JWT com HS256 para monolito Django com tokens contextuais por aplicação.
"""

import logging
import uuid
from datetime import datetime, timedelta
from typing import Any

import jwt
from django.conf import settings
from django.contrib.auth.models import AbstractUser
from accounts.models import UserRole
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.hashers import check_password
from django.core.cache import cache
from django.utils import timezone



logger = logging.getLogger(__name__)


class TokenServiceException(Exception):
    """Exceção base para erros do TokenService"""

    pass


class InvalidTokenException(TokenServiceException):
    """Token inválido ou expirado"""

    pass


class UserRoleNotFoundException(TokenServiceException):
    """UserRole não encontrado ou inativo"""

    pass


class TokenService:
    """
    Serviço centralizado para gerenciamento de tokens JWT.

    Características:
    - JWT com HS256 (monolito)
    - Access token: 10 minutos
    - Refresh token: 30 minutos
    - Token contextual por aplicação
    - Claims: sub, app_code, active_role_id, role_code, exp, jti, token_type
    - Suporte a blacklist futura via cache/database
    """

    # Configurações de tempo de vida dos tokens
    ACCESS_TOKEN_LIFETIME = timedelta(minutes=10)
    REFRESH_TOKEN_LIFETIME = timedelta(minutes=30)

    # Algoritmo de assinatura
    ALGORITHM = "HS256"

    # Prefixos para cache de blacklist
    BLACKLIST_PREFIX = "token_blacklist:"
    REFRESH_BLACKLIST_PREFIX = "refresh_blacklist:"

    def __init__(self) -> None:
        """Inicializa o TokenService com a chave secreta do Django"""
        self.secret_key = settings.SECRET_KEY

        if not self.secret_key or len(self.secret_key) < 50:
            logger.warning(
                "SECRET_KEY muito curta. Use uma chave de pelo menos 50 caracteres "
                "para produção. Gere uma com: python -c 'from django.core.management.utils "
                "import get_random_secret_key; print(get_random_secret_key())'"
            )

    # ---------------------------------------------------------------------
    # Login de conveniência (para Web/API)
    # ---------------------------------------------------------------------
    def login(
        self,
        username_or_email: str,
        password: str,
        app_code: str,
        role_id: int,
    ) -> dict[str, Any] | None:
        """
        Autentica usuário e retorna tokens + user.

        Args:
            username_or_email: Email ou username
            password: Senha
            app_code: Código da aplicação (ex: 'ACOES_PNGI')
            role_id: ID da role ativa que será usada no contexto

        Returns:
            dict com:
                - user
                - access_token
                - refresh_token
                - expires_in (segundos)
            ou None se falhar autenticação.
        """
        UserModel = get_user_model()

        # 1) Autenticação via backend padrão
        user = authenticate(username=username_or_email, password=password)

        # 2) Fallback para login via email (como você já usa no GPP/SEGER)
        if user is None:
            try:
                user = UserModel.objects.get(email__iexact=username_or_email)
                if not (check_password(password, user.password) and user.is_active):
                    user = None
            except UserModel.DoesNotExist:
                user = None

        if not user or not user.is_active:
            logger.warning(f"Login falhou: {username_or_email}")
            return None

        # 3) Gera tokens usando os métodos oficiais de emissão
        try:
            access_token = self.issue_access_token(user, app_code, role_id)
            refresh_token = self.issue_refresh_token(user, app_code, role_id)
        except TokenServiceException as exc:
            logger.warning(f"Falha ao emitir tokens no login: {exc}")
            return None

        logger.info(
            f"Login OK: {user.email} (ID: {user.id}) app={app_code} role_id={role_id}"
        )

        return {
            "user": user,
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_in": int(self.ACCESS_TOKEN_LIFETIME.total_seconds()),
        }

    # ---------------------------------------------------------------------
    # Helpers de JTI e blacklist
    # ---------------------------------------------------------------------
    def _generate_jti(self) -> str:
        """
        Gera um JTI (JWT ID) único e seguro.

        Estratégia:
        - UUID4 (aleatório e único)
        - Timestamp para ordenação temporal

        Returns:
            str: JTI único no formato 'uuid4-timestamp'
        """
        unique_id = uuid.uuid4().hex
        timestamp = int(timezone.now().timestamp())
        return f"{unique_id}-{timestamp}"

    def _get_blacklist_key(self, jti: str, is_refresh: bool = False) -> str:
        """
        Gera chave de cache para blacklist.

        Args:
            jti: JWT ID
            is_refresh: Se é refresh token

        Returns:
            str: Chave de cache
        """
        prefix = self.REFRESH_BLACKLIST_PREFIX if is_refresh else self.BLACKLIST_PREFIX
        return f"{prefix}{jti}"

    def _is_blacklisted(self, jti: str, is_refresh: bool = False) -> bool:
        """
        Verifica se um token está na blacklist.

        Args:
            jti: JWT ID
            is_refresh: Se é refresh token

        Returns:
            bool: True se está na blacklist
        """
        key = self._get_blacklist_key(jti, is_refresh)
        return cache.get(key) is not None

    def blacklist_token(
        self, jti: str, exp: datetime, is_refresh: bool = False
    ) -> None:
        """
        Adiciona um token à blacklist.

        Estratégia:
        - Cache Redis/Memcached para performance
        - TTL automático igual ao tempo restante do token
        - Não armazena tokens expirados (economia de memória)

        Args:
            jti: JWT ID
            exp: Data de expiração do token
            is_refresh: Se é refresh token
        """
        now = timezone.now()

        # Não adiciona tokens já expirados
        if exp <= now:
            logger.debug(f"Token {jti} já expirado, não adicionado à blacklist")
            return

        # Calcula TTL (tempo até expiração)
        ttl_seconds = int((exp - now).total_seconds())

        key = self._get_blacklist_key(jti, is_refresh)

        # Armazena no cache com TTL
        cache.set(
            key,
            {
                "blacklisted_at": now.isoformat(),
                "expires_at": exp.isoformat(),
                "is_refresh": is_refresh,
            },
            timeout=ttl_seconds,
        )

        logger.info(
            f"Token {'refresh' if is_refresh else 'access'} {jti} "
            f"adicionado à blacklist (TTL: {ttl_seconds}s)"
        )

    # ---------------------------------------------------------------------
    # Emissão de tokens
    # ---------------------------------------------------------------------
    def _get_user_role(
        self,
        user: User,
        app_code: str,
        role_id: int,
    ) -> UserRole:
        """
        Helper central para buscar e validar UserRole.
        """
        try:
            return UserRole.objects.select_related("user", "aplicacao", "role").get(
                user=user,
                aplicacao__codigointerno=app_code,
                role_id=role_id,
            )
        except UserRole.DoesNotExist:
            raise UserRoleNotFoundException(
                f"UserRole não encontrado: user={user.id}, app={app_code}, role={role_id}"
            )

    def issue_access_token(
        self,
        user: User,
        app_code: str,
        role_id: int,
        extra_claims: dict[str, Any] | None = None,
    ) -> str:
        """
        Emite um access token JWT (10 minutos).

        Args:
            user: Instância do usuário
            app_code: Código da aplicação (ex: 'ACOES_PNGI')
            role_id: ID da role ativa
            extra_claims: Claims adicionais opcionais

        Returns:
            str: Access token JWT

        Raises:
            UserRoleNotFoundException: Se UserRole não existe
            TokenServiceException: Se usuário está inativo
        """
        user_role = self._get_user_role(user, app_code, role_id)

        # Valida se usuário está ativo
        if not user.is_active:
            raise TokenServiceException(f"Usuário {user.id} está inativo")

        now = timezone.now()
        exp = now + self.ACCESS_TOKEN_LIFETIME
        jti = self._generate_jti()

        payload: dict[str, Any] = {
            "sub": str(user.id),  # Subject: user_id
            "app_code": app_code,  # Código da aplicação
            "active_role_id": role_id,  # ID da role ativa
            "role_code": user_role.role.codigoperfil,  # Código da role (GESTOR_PNGI, etc.)
            "exp": int(exp.timestamp()),  # Expiração em timestamp
            "iat": int(now.timestamp()),  # Emissão
            "jti": jti,  # JWT ID (único)
            "token_type": "access",  # Tipo de token
            # "token_version": user.token_version,  # TODO: quando existir no modelo User
        }

        if extra_claims:
            payload.update(extra_claims)

        token = jwt.encode(payload, self.secret_key, algorithm=self.ALGORITHM)

        logger.info(
            f"Access token emitido: user={user.id}, app={app_code}, "
            f"role={user_role.role.codigoperfil}, jti={jti}"
        )

        return token

    def issue_refresh_token(
        self,
        user: User,
        app_code: str,
        role_id: int,
        extra_claims: dict[str, Any] | None = None,
    ) -> str:
        """
        Emite um refresh token JWT (30 minutos).

        Args:
            user: Instância do usuário
            app_code: Código da aplicação
            role_id: ID da role ativa
            extra_claims: Claims adicionais opcionais

        Returns:
            str: Refresh token JWT

        Raises:
            UserRoleNotFoundException: Se UserRole não existe
            TokenServiceException: Se usuário está inativo
        """
        user_role = self._get_user_role(user, app_code, role_id)

        if not user.is_active:
            raise TokenServiceException(f"Usuário {user.id} está inativo")

        now = timezone.now()
        exp = now + self.REFRESH_TOKEN_LIFETIME
        jti = self._generate_jti()

        payload: dict[str, Any] = {
            "sub": str(user.id),
            "app_code": app_code,
            "active_role_id": role_id,
            "role_code": user_role.role.codigoperfil,
            "exp": int(exp.timestamp()),
            "iat": int(now.timestamp()),
            "jti": jti,
            "token_type": "refresh",
            # "token_version": user.token_version,  # TODO: quando existir no modelo User
        }

        if extra_claims:
            payload.update(extra_claims)

        token = jwt.encode(payload, self.secret_key, algorithm=self.ALGORITHM)

        logger.info(
            f"Refresh token emitido: user={user.id}, app={app_code}, "
            f"role={user_role.role.codigoperfil}, jti={jti}"
        )

        return token

    # ---------------------------------------------------------------------
    # Validação e refresh
    # ---------------------------------------------------------------------
    def validate_access_token(self, token: str) -> dict[str, Any]:
        """
        Valida um access token JWT.

        Validações:
        1. Assinatura válida
        2. Não expirado
        3. Não está na blacklist
        4. UserRole ainda existe
        5. Usuário ainda está ativo
        6. (Opcional futuro) token_version

        Args:
            token: Token JWT

        Returns:
            Dict: Payload do token decodificado

        Raises:
            InvalidTokenException: Se token inválido
        """
        try:
            payload = jwt.decode(
                token,
                self.secret_key,
                algorithms=[self.ALGORITHM],
                options={"verify_exp": True},
            )
        except jwt.ExpiredSignatureError:
            raise InvalidTokenException("Token expirado")
        except jwt.InvalidTokenError as exc:
            raise InvalidTokenException(f"Token inválido: {exc}")

        if payload.get("token_type") != "access":
            raise InvalidTokenException("Token não é um access token")

        jti = payload.get("jti")
        if not jti:
            raise InvalidTokenException("Token sem JTI")

        if self._is_blacklisted(jti, is_refresh=False):
            raise InvalidTokenException("Token revogado (blacklist)")

        user_id = payload.get("sub")
        app_code = payload.get("app_code")
        role_id = payload.get("active_role_id")

        try:
            user_role = UserRole.objects.select_related(
                "user", "aplicacao", "role"
            ).get(
                user_id=user_id,
                aplicacao__codigointerno=app_code,
                role_id=role_id,
            )
        except UserRole.DoesNotExist:
            raise InvalidTokenException("UserRole não existe mais ou foi desativado")

        if not user_role.user.is_active:
            raise InvalidTokenException("Usuário inativo")

        # TODO (opcional): validar token_version quando existir no modelo User

        logger.debug(f"Access token válido: jti={jti}, user={user_id}")
        return payload

    def refresh(self, refresh_token: str) -> dict[str, str]:
        """
        Gera novos tokens a partir de um refresh token.

        Validações:
        1. Refresh token válido
        2. Não expirado
        3. Não está na blacklist
        4. UserRole ainda existe
        5. Usuário ainda está ativo
        6. Role ainda pertence ao usuário

        Comportamento:
        - Gera novo access token
        - Gera novo refresh token
        - Adiciona refresh token antigo à blacklist (rotation)

        Args:
            refresh_token: Refresh token JWT

        Returns:
            Dict com 'access_token' e 'refresh_token'

        Raises:
            InvalidTokenException: Se refresh token inválido
        """
        try:
            payload = jwt.decode(
                refresh_token,
                self.secret_key,
                algorithms=[self.ALGORITHM],
                options={"verify_exp": True},
            )
        except jwt.ExpiredSignatureError:
            raise InvalidTokenException("Refresh token expirado")
        except jwt.InvalidTokenError as exc:
            raise InvalidTokenException(f"Refresh token inválido: {exc}")

        if payload.get("token_type") != "refresh":
            raise InvalidTokenException("Token não é um refresh token")

        jti = payload.get("jti")
        if not jti:
            raise InvalidTokenException("Token sem JTI")

        if self._is_blacklisted(jti, is_refresh=True):
            raise InvalidTokenException("Refresh token revogado (blacklist)")

        user_id = payload.get("sub")
        app_code = payload.get("app_code")
        role_id = payload.get("active_role_id")

        try:
            user_role = UserRole.objects.select_related(
                "user", "aplicacao", "role"
            ).get(
                user_id=user_id,
                aplicacao__codigointerno=app_code,
                role_id=role_id,
            )
        except UserRole.DoesNotExist:
            raise InvalidTokenException(
                "UserRole não existe mais. Faça login novamente."
            )

        if not user_role.user.is_active:
            raise InvalidTokenException("Usuário inativo")

        # ADICIONA refresh token antigo à blacklist (rotation)
        exp_datetime = datetime.fromtimestamp(
            payload["exp"],
            tz=timezone.get_current_timezone(),
        )
        self.blacklist_token(jti, exp_datetime, is_refresh=True)

        # Gera novos tokens
        new_access_token = self.issue_access_token(user_role.user, app_code, role_id)
        new_refresh_token = self.issue_refresh_token(user_role.user, app_code, role_id)

        logger.info(f"Tokens renovados: user={user_id}, app={app_code}, old_jti={jti}")

        return {
            "access_token": new_access_token,
            "refresh_token": new_refresh_token,
        }

    # ---------------------------------------------------------------------
    # Revogação manual
    # ---------------------------------------------------------------------
    def revoke_token(self, token: str, is_refresh: bool = False) -> None:
        """
        Revoga um token adicionando-o à blacklist.

        Args:
            token: Token JWT
            is_refresh: Se é refresh token

        Raises:
            InvalidTokenException: Se token inválido
        """
        try:
            payload = jwt.decode(
                token,
                self.secret_key,
                algorithms=[self.ALGORITHM],
                options={"verify_exp": False},  # Permite revogar tokens expirados
            )
        except jwt.InvalidTokenError as exc:
            raise InvalidTokenException(f"Token inválido: {exc}")

        jti = payload.get("jti")
        if not jti:
            raise InvalidTokenException("Token sem JTI")

        exp_datetime = datetime.fromtimestamp(
            payload["exp"],
            tz=timezone.get_current_timezone(),
        )

        self.blacklist_token(jti, exp_datetime, is_refresh)

        logger.info(f"Token revogado manualmente: jti={jti}")

    def revoke_all_user_tokens(self, user_id: int, app_code: str | None = None) -> int:
        """
        Revoga todos os tokens de um usuário (estratégia futura via token_version).

        Estratégia recomendada:
        - Adicionar campo token_version no modelo User
        - Incluir token_version nos claims
        - Ao revogar, incrementar token_version
        - Na validação, rejeitar tokens com versão antiga

        Args:
            user_id: ID do usuário
            app_code: Código da aplicação (opcional, atualmente ignorado)

        Returns:
            int: Nova versão de token (quando implementado)
        """
        # TODO: implementar com campo User.token_version (ver docstring)
        logger.warning(
            "revoke_all_user_tokens não implementado ainda. "
            "Planeje invalidar via User.token_version. "
            f"user_id={user_id}, app_code={app_code}"
        )
        return 0


# Instância singleton
_token_service: TokenService | None = None


def get_token_service() -> TokenService:
    """
    Retorna instância singleton do TokenService.

    Returns:
        TokenService: Instância única
    """
    global _token_service
    if _token_service is None:
        _token_service = TokenService()
    return _token_service
