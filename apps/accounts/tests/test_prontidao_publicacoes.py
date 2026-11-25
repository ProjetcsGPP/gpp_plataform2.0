"""Preflight local nunca requer serviços nem emite segredos."""

from types import SimpleNamespace
from unittest import TestCase

from config.prontidao_publicacoes import (
    verificar_configuracao_iam, verificar_configuracao_publicacoes,
)


def _configuracao(**alteracoes):
    valores = {
        "SETTINGS_MODULE": "config.settings.publicacoes_piloto",
        "IAM_DECISOES_INTERNAS_ATIVAS": True,
        "IAM_DECISOES_PUBLICACOES_ATIVAS": True,
        "IAM_TOKEN_SERVICO_PUBLICACOES": "p" * 40,
        "IAM_TOKEN_SERVICO_CARGA": "c" * 40,
        "IAM_URL_PUBLICACOES": (
            "http://127.0.0.1:8001/interno/iam/v1/decisoes-publicacoes/"
        ),
        "PUBLICACOES_IAM_IDENTIDADE_HTTP_REMOTA_ATIVA": True,
        "PUBLICACOES_IAM_WEBSOCKET_REMOTO_ATIVO": True,
        "PUBLICACOES_IAM_ATIVIDADES_REMOTAS_ATIVAS": True,
        "CELERY_BEAT_SCHEDULE": {},
        "GPP_CELERY_TASK_PACKAGES": ("apps.pub_institucional",),
        "GPP_BLOQUEAR_MIGRACOES_NO_PROCESSO_PUBLICACOES": True,
    }
    valores.update(alteracoes)
    return SimpleNamespace(**valores)


class TestProntidaoPublicacoes(TestCase):
    """Pode rodar sem o setup Django e sem tocar o PostgreSQL."""

    def test_configuracao_completa_passar_sem_acessar_servicos(self):
        self.assertEqual(verificar_configuracao_publicacoes(_configuracao()), [])

    def test_configuracao_incompleta_falha_sem_expor_segredos(self):
        configuracao = _configuracao(
            IAM_TOKEN_SERVICO_PUBLICACOES="c" * 40,
            IAM_URL_PUBLICACOES=(
                "http://iam.externo:8001/interno/iam/v1/decisoes-publicacoes/"
            ),
            PUBLICACOES_IAM_ATIVIDADES_REMOTAS_ATIVAS=False,
        )
        pendencias = verificar_configuracao_publicacoes(configuracao)
        self.assertEqual(len(pendencias), 3)
        self.assertFalse(any(
            "iam.externo" in item or "c" * 40 in item for item in pendencias
        ))

    def test_url_malformada_e_perfil_indevido_falham_fechados(self):
        configuracao = _configuracao(
            SETTINGS_MODULE="config.settings.development",
            IAM_URL_PUBLICACOES=(
                "http://127.0.0.1:invalida/interno/iam/v1/decisoes-publicacoes/"
            ),
        )
        self.assertEqual(len(verificar_configuracao_publicacoes(configuracao)), 2)

    def test_flag_produtor_nao_e_exigida_no_consumidor(self):
        configuracao = _configuracao(IAM_DECISOES_INTERNAS_ATIVAS=False)
        self.assertEqual(verificar_configuracao_publicacoes(configuracao), [])

    def test_produtor_e_verificado_em_seu_proprio_perfil(self):
        configuracao = _configuracao(
            SETTINGS_MODULE="config.settings.plataforma_separada_piloto",
            GPP_CELERY_TASK_PACKAGES=(),
            IAM_DECISOES_INTERNAS_ATIVAS=False,
        )
        self.assertEqual(verificar_configuracao_iam(configuracao), [])
        configuracao.IAM_DECISOES_PUBLICACOES_ATIVAS = False
        self.assertIn(
            "Produtor de decisões de Publicações desativado",
            verificar_configuracao_iam(configuracao),
        )
