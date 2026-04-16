"""
GPP Plataform 2.0 — AuthZ Versioning Layer

Este módulo implementa uma camada LEVE de versionamento de autorização
por usuário, usada EXCLUSIVAMENTE para invalidação de cache no frontend.

IMPORTANTE:
  - NÃO é parte do sistema de segurança.
  - NÃO substitui permissões reais (auth_user_user_permissions).
  - NÃO é usado em decisões de autorização.
  - É apenas um sinal de mudança (invalidator) para o frontend.

Fluxo de uso:
  1. Qualquer mudança de autorização (UserRole, UserPermissionOverride,
     group permissions, Role) chama bump_authz_version(user).
  2. O frontend faz polling leve em GET /api/authz/version/.
  3. Se a versão mudou, o frontend refaz fetch de /me/permissions/,
     navigation JSON, e invalida caches locais (React Query / Zustand).

Garantias:
  - Persistido em banco (não cache) — sobrevive restart de servidor.
  - Não depende de Redis.
  - Atomicidade via F() expression — sem race condition.
  - O(1) por request — sem joins em permissões.
"""
from django.conf import settings
from django.db import models
from django.db.models import F


class UserAuthzState(models.Model):
    """
    Estado de versionamento de autorização por usuário.

    Mantém um contador (authz_version) que é incrementado sempre que
    o conjunto de permissões do usuário muda. O frontend usa este valor
    para decidir se deve refazer o fetch de permissões.

    Regras:
      - Relação 1:1 com auth.User.
      - Persistido em banco — não depende de Redis.
      - Sobrevive restart de servidor.
      - NÃO é fonte de verdade de permissões — apenas invalidador.
    """
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="authz_state",
    )
    authz_version = models.BigIntegerField(
        default=0,
        help_text=(
            "Contador de versão de autorização. Incrementado atomicamente "
            "a cada mudança de permissão. Usado APENAS pelo frontend para "
            "invalidação de cache — não representa permissões reais."
        ),
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "accounts_userauthzstate"
        managed = True
        verbose_name = "User AuthZ State"
        verbose_name_plural = "User AuthZ States"

    def __str__(self):
        return f"AuthZState(user_id={self.user_id}, version={self.authz_version})"


def bump_authz_version(user) -> None:
    """
    Incrementa atomicamente a versão de autorização do usuário.

    Usado APENAS para invalidação de cache no frontend. Não afeta
    permissões reais nem o sistema RBAC.

    Usa F("authz_version") + 1 para garantir atomicidade em nível de
    banco de dados, evitando race conditions em ambientes concorrentes.

    Args:
        user: instância de auth.User ou user_id (int).
              Aceita ambos para flexibilidade de chamada nos signals.

    Comportamento:
        - Se UserAuthzState não existir para o usuário, cria com version=1.
        - Se existir, incrementa atomicamente via UPDATE ... SET version = version + 1.
        - Silencia exceções para não comprometer o fluxo principal de RBAC.
    """
    import logging
    logger = logging.getLogger("gpp.security")

    try:
        user_id = user.pk if hasattr(user, "pk") else int(user)
        rows_updated = (
            UserAuthzState.objects
            .filter(user_id=user_id)
            .update(authz_version=F("authz_version") + 1)
        )
        if rows_updated == 0:
            # Registro não existe ainda — cria com version=1.
            # get_or_create + update garante que não haverá duplicata
            # mesmo em concorrência (a constraint OneToOne protege).
            UserAuthzState.objects.get_or_create(
                user_id=user_id,
                defaults={"authz_version": 1},
            )
        logger.debug("AUTHZ_VERSION_BUMPED user_id=%s", user_id)
    except Exception:
        logger.exception("AUTHZ_VERSION_BUMP_ERROR user=%s", user)
