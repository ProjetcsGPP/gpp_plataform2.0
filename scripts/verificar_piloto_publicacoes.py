"""Preflight local de configuração: não acessa IAM, banco ou broker.

Uso: DJANGO_SETTINGS_MODULE=config.settings.publicacoes_piloto \
    .venv/bin/python -m scripts.verificar_piloto_publicacoes
Ou: DJANGO_SETTINGS_MODULE=config.settings.plataforma_separada_piloto \
    .venv/bin/python -m scripts.verificar_piloto_publicacoes
"""

import os

from django.conf import settings

from config.prontidao_publicacoes import (
    verificar_configuracao_iam, verificar_configuracao_publicacoes,
)


def main():
    """Mostra apenas nomes de pendências, nunca valores sensíveis."""
    perfil = os.environ.get("DJANGO_SETTINGS_MODULE")
    verificacoes = {
        "config.settings.publicacoes_piloto": verificar_configuracao_publicacoes,
        "config.settings.plataforma_separada_piloto": verificar_configuracao_iam,
    }
    if perfil not in verificacoes:
        print("PENDENTE: selecione um perfil piloto de Publicações ou IAM/plataforma")
        return 1
    pendencias = verificacoes[perfil](settings)
    for pendencia in pendencias:
        print(f"PENDENTE: {pendencia}")
    if pendencias:
        print("Configuração local incompleta; nenhum serviço foi iniciado.")
        return 1
    print("Configuração local coerente; ainda faltam ensaios operacionais antes do cutover.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
