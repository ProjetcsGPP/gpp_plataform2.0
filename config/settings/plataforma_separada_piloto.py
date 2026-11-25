"""Perfil local opt-in de IAM, Portal e Ações sem domínios isolados."""

# pylint: disable=wildcard-import,unused-wildcard-import
from .development import *  # noqa: F401,F403

from .segredo_iam_publicacoes_piloto import carregar_token

# Opt-in pelo perfil separado; o monólito não lê o segredo local do piloto.
IAM_TOKEN_SERVICO_PUBLICACOES = carregar_token(IAM_TOKEN_SERVICO_PUBLICACOES)
IAM_DECISOES_PUBLICACOES_ATIVAS = True

ROOT_URLCONF = "config.urls_plataforma_separada_piloto"
ASGI_APPLICATION = "config.asgi_plataforma_separada_piloto.application"

# Um Beat para os agendamentos das duas apps; o worker não consome suas filas.
CELERY_TASK_ROUTES = {
    "carga_org_lot.*": {"queue": "carga_org_lot"},
    "pub_institucional.*": {"queue": "pub_institucional"},
}
GPP_CELERY_TASK_PACKAGES = ()
