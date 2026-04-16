from django.db.models import F

from .models import UserAuthzState


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
        rows_updated = UserAuthzState.objects.filter(user_id=user_id).update(
            authz_version=F("authz_version") + 1
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
