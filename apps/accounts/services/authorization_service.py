"""
AuthorizationService

Responsabilidade:
  Valida se um usuário pode executar uma ação em determinado recurso,
  combinando RBAC (roles/permissions do Django) com ABAC (atributos).

Método principal:
    service = AuthorizationService(user, application)
    pode = service.can("view_acao")      # True / False
    pode = service.can("change_acao", context={"eixo": "X"})  # com ABAC

Estratégia de cache:
    Chave: authz:{user_id}:{version}:{app_code}
    TTL:   300s
    Version key: authz_version:{user_id}  (incrementado pelos signals)
    Invalidação: signals em UserRole, Role, auth_group_permissions
"""
import logging
from typing import Optional

from django.core.cache import cache

security_logger = logging.getLogger("gpp.security")

CACHE_TTL = 300  # 5 minutos


class AuthorizationService:
    def __init__(self, user, application=None):
        """
        Args:
            user: instância de auth.User (autenticado)
            application: instância de Aplicacao ou None
        """
        self.user = user
        self.application = application
        self._permissions: Optional[set] = None
        self._attributes: Optional[dict] = None
        self._roles: Optional[list] = None

    # ─── API pública ────────────────────────────────────────────────────────

    def can(self, permission_codename: str, context: dict = None) -> bool:
        """
        Verifica se o usuário pode executar a ação.

        Fluxo:
          1. PORTAL_ADMIN → True sempre
          2. Valida UserRole no banco (nunca confia só no JWT)
          3. Verifica permission_codename via RBAC (auth_group_permissions)
          4. Aplica filtros ABAC se context fornecido
        """
        if not self.user or not self.user.is_authenticated:
            return False

        # 1. PORTAL_ADMIN tem acesso irrestrito
        if self._is_portal_admin():
            security_logger.info(
                "AUTHZ_ALLOW user_id=%s perm=%s reason=portal_admin",
                self.user.id, permission_codename,
            )
            return True

        # 2. Valida que existe UserRole no banco para esta aplicação
        if not self._has_valid_role():
            security_logger.warning(
                "AUTHZ_DENY user_id=%s perm=%s reason=no_valid_role app=%s",
                self.user.id, permission_codename,
                getattr(self.application, "codigointerno", "none"),
            )
            return False

        # 3. RBAC: verifica permissão via grupos do Django
        permissions = self._load_permissions()
        if permission_codename not in permissions:
            security_logger.warning(
                "AUTHZ_DENY user_id=%s perm=%s reason=no_permission app=%s",
                self.user.id, permission_codename,
                getattr(self.application, "codigointerno", "none"),
            )
            return False

        # 4. ABAC: refina com atributos se context fornecido
        if context:
            if not self._check_abac(permission_codename, context):
                security_logger.warning(
                    "AUTHZ_DENY user_id=%s perm=%s reason=abac_filter app=%s context=%s",
                    self.user.id, permission_codename,
                    getattr(self.application, "codigointerno", "none"),
                    context,
                )
                return False

        security_logger.info(
            "AUTHZ_ALLOW user_id=%s perm=%s app=%s",
            self.user.id, permission_codename,
            getattr(self.application, "codigointerno", "none"),
        )
        return True

    def get_permissions(self) -> set:
        """Retorna o set de codenames de permissões do usuário para esta app."""
        return self._load_permissions()

    def get_attributes(self) -> dict:
        """Retorna os atributos ABAC do usuário para esta app."""
        return self._load_attributes()

    def get_roles(self) -> list:
        """Retorna as roles ativas do usuário para esta app."""
        return self._load_roles()


    # ─── Verificações internas ──────────────────────────────────────────────

    def _is_portal_admin(self) -> bool:
        from apps.accounts.models import UserRole
        return UserRole.objects.filter(
            user=self.user,
            role__codigoperfil="PORTAL_ADMIN",
        ).exists()

    # ─── Autorização baseada em ClassificacaoUsuario ────────────────────────
    # Responsabilidade: gerenciamento de usuários da plataforma.
    # Separado do RBAC por Role/UserRole, que controla recursos das apps.

    def _get_classificacao(self):
        """
        Retorna ClassificacaoUsuario do perfil do usuário.

        Usa o related_name 'profile' definido em UserProfile.
        Comportamento fail-closed: qualquer falha retorna None,
        causando negação de permissão nas chamadas downstream.
        """
        try:
            return self.user.profile.classificacao_usuario
        except Exception:
            return None

    def user_can_create_users(self) -> bool:
        """
        Verifica se o usuário pode criar novos usuários na plataforma.

        Hierarquia:
          1. PORTAL_ADMIN → True (bootstrap/compatibilidade — @deprecated)
          2. ClassificacaoUsuario.pode_criar_usuario == True → True
          3. Qualquer outro caso → False (fail-closed)

        Não verifica Role/UserRole — essa é uma permissão de plataforma,
        não de aplicação específica.
        """
        if self._is_portal_admin():
            security_logger.info(
                "AUTHZ_USER_CREATE user_id=%s reason=portal_admin",
                self.user.id,
            )
            return True

        classificacao = self._get_classificacao()
        if classificacao is None:
            security_logger.warning(
                "AUTHZ_DENY_USER_CREATE user_id=%s reason=no_classificacao",
                self.user.id,
            )
            return False

        
        result = bool(classificacao.pode_criar_usuario)
        log_level = security_logger.info if result else security_logger.warning
        log_level(
            "AUTHZ_USER_CREATE user_id=%s classificacao_id=%s "
            "classificacao=%s result=%s",
            self.user.id,
            classificacao.pk,
            classificacao.strdescricao,
            result,
        )
        return result

    def user_can_edit_users(self) -> bool:
        """
        Verifica se o usuário pode editar usuários existentes na plataforma.

        Hierarquia:
          1. PORTAL_ADMIN → True (bootstrap/compatibilidade — @deprecated)
          2. ClassificacaoUsuario.pode_editar_usuario == True → True
          3. Qualquer outro caso → False (fail-closed)
        """
        if self._is_portal_admin():
            security_logger.info(
                "AUTHZ_USER_EDIT user_id=%s reason=portal_admin",
                self.user.id,
            )
            return True

        classificacao = self._get_classificacao()
        if classificacao is None:
            security_logger.warning(
                "AUTHZ_DENY_USER_EDIT user_id=%s reason=no_classificacao",
                self.user.id,
            )
            return False

        result = bool(classificacao.pode_editar_usuario)
        log_level = security_logger.info if result else security_logger.warning
        log_level(
            "AUTHZ_USER_EDIT user_id=%s classificacao_id=%s "
            "classificacao=%s result=%s",
            self.user.id,
            classificacao.pk,
            classificacao.strdescricao,
            result,
        )
        return result

    def user_can_manage_target_user(self, target_user) -> bool:
        """
        Verifica se o usuário autenticado pode gerenciar (criar/editar) o target_user,
        aplicando escopo por aplicação para gestores.

        Regras:
          1. PORTAL_ADMIN → True (acesso irrestrito a todas as aplicações)
          2. Gestor sem user_can_edit_users() → False (fail-closed)
          3. Gestor com user_can_edit_users() → True somente se existir interseção
             entre as aplicações do gestor e as aplicações do target_user via UserRole.

        Segurança:
          - A aplicação alvo NUNCA é obtida da request.
          - Toda validação é baseada exclusivamente em UserRole no banco.
          - Isso evita manipulação de parâmetros da requisição.

        Performance:
          - Executa uma única query com subquery IN, resolvida no banco.
          - Escala bem mesmo com muitos UserRole registrados.

        Args:
            target_user: instância de auth.User que se deseja gerenciar.

        Returns:
            True se o acesso for permitido, False caso contrário.
        """
        # 1. PORTAL_ADMIN tem acesso irrestrito
        if self._is_portal_admin():
            security_logger.info(
                "AUTHZ_MANAGE_USER_ALLOW user_id=%s target_user_id=%s reason=portal_admin",
                self.user.id, target_user.id,
            )
            return True

        # 2. Gestor sem permissão de edição → nega imediatamente
        if not self.user_can_edit_users():
            security_logger.warning(
                "AUTHZ_MANAGE_USER_DENY user_id=%s target_user_id=%s "
                "reason=no_edit_permission",
                self.user.id, target_user.id,
            )
            return False

        # 3. Verifica interseção de aplicações via UserRole (DB-only, sem request)
        from apps.accounts.models import UserRole

        gestor_apps = UserRole.objects.filter(user=self.user).values("aplicacao")

        has_intersection = UserRole.objects.filter(
            user=target_user,
            aplicacao__in=gestor_apps,
        ).exists()

        if has_intersection:
            security_logger.info(
                "AUTHZ_MANAGE_USER_ALLOW user_id=%s target_user_id=%s "
                "reason=app_intersection",
                self.user.id, target_user.id,
            )
        else:
            security_logger.warning(
                "AUTHZ_MANAGE_USER_DENY user_id=%s target_user_id=%s "
                "reason=no_app_intersection",
                self.user.id, target_user.id,
            )

        return has_intersection

    def _has_valid_role(self) -> bool:
        """
        Verifica no banco se o usuário tem ao menos 1 UserRole
        para a aplicação atual. NUNCA confia apenas no JWT.
        """
        roles = self._load_roles()
        return len(roles) > 0

    def _check_abac(self, permission_codename: str, context: dict) -> bool:
        """
        Verifica atributos ABAC.
        Cada chave do context é comparada com o atributo do usuário.
        Se o atributo não existir para o usuário, o acesso é negado (fail-closed).
        """
        attributes = self._load_attributes()
        for key, expected_value in context.items():
            user_value = attributes.get(key)
            if user_value is None:
                return False  # atributo não definido → nega
            if str(user_value) != str(expected_value):
                return False
        return True

    # ─── Carregamento com cache ──────────────────────────────────────────────

    def _load_permissions(self) -> set:
        if self._permissions is not None:
            return self._permissions

        cache_key = self._permissions_cache_key()
        cached = cache.get(cache_key)
        if cached is not None:
            self._permissions = cached
            return self._permissions

        # Carrega via roles → groups → permissions
        from django.contrib.auth.models import Permission
        from apps.accounts.models import UserRole

        roles = self._load_roles()
        group_ids = [
            ur.role.group_id for ur in roles
            if ur.role.group_id is not None
        ]

        if group_ids:
            perms = (
                Permission.objects
                .filter(group__id__in=group_ids)
                .values_list("codename", flat=True)
            )
            self._permissions = set(perms)
        else:
            self._permissions = set()

        cache.set(cache_key, self._permissions, CACHE_TTL)
        return self._permissions

    def _load_roles(self) -> list:
        if self._roles is not None:
            return self._roles

        from apps.accounts.models import UserRole

        qs = (
            UserRole.objects
            .filter(user=self.user)
            .select_related("role", "role__group", "aplicacao")
        )
        if self.application:
            qs = qs.filter(aplicacao=self.application)

        self._roles = list(qs)
        return self._roles

    def _load_attributes(self) -> dict:
        if self._attributes is not None:
            return self._attributes

        from apps.accounts.models import Attribute

        qs = Attribute.objects.filter(user=self.user)
        if self.application:
            qs = qs.filter(aplicacao=self.application)

        self._attributes = {a.key: a.value for a in qs}
        return self._attributes

    def _permissions_cache_key(self) -> str:
        app_code = self.application.codigointerno if self.application else "all"
        version = cache.get(f"authz_version:{self.user.id}") or 1
        return f"authz:{self.user.id}:v{version}:{app_code}"
