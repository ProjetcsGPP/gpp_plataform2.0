"""Lança um perfil ASGI real exclusivamente contra o PostgreSQL de testes.

Não é um launcher operacional. Falha antes do import ASGI se o nome do banco
não for de teste ou se coincidir com o banco configurado normalmente.
"""

import os
import sys


def main():
    if len(sys.argv) != 4 or sys.argv[1] not in {
        "carga", "plataforma", "publicacoes", "plataforma_separada",
        "acoes", "plataforma_quatro",
    }:
        raise SystemExit("Uso: asgi_ensaio_runner PERFIL PORTA PORTA_PROXY")
    perfil, porta, porta_proxy = sys.argv[1:]
    nome_banco = os.environ.get("GPP_ENSAIO_TEST_DB_NAME", "")
    if nome_banco != "test_gpp_plataform":
        raise SystemExit("Ensaio ASGI exige test_gpp_plataform")

    modulo = f"config.settings.{perfil}_piloto"
    os.environ["DJANGO_SETTINGS_MODULE"] = modulo

    from django.conf import settings  # pylint: disable=import-outside-toplevel

    banco_normal = settings.DATABASES["default"]["NAME"]
    if nome_banco == banco_normal:
        raise SystemExit("Ensaio ASGI não pode usar o banco operacional")
    settings.DATABASES["default"]["NAME"] = nome_banco
    settings.ALLOWED_HOSTS = ["127.0.0.1", "localhost"]
    settings.DEBUG = False
    settings.CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": f"gpp-ensaio-asgi-{perfil}",
        },
        "cargarh_tokens": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": f"gpp-ensaio-asgi-{perfil}-tokens",
        },
    }
    settings.CHANNEL_LAYERS = {
        "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}
    }
    settings.EMAIL_BACKEND = "django.core.mail.backends.dummy.EmailBackend"
    settings.SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    settings.SESSION_COOKIE_SECURE = True
    settings.CSRF_COOKIE_SECURE = True
    settings.CSRF_TRUSTED_ORIGINS = [f"https://localhost:{porta_proxy}"]
    settings.IAM_TOKEN_SERVICO_CARGA = (
        "credencial-m2m-sintetica-para-testes-de-integracao"
    )
    settings.IAM_TOKEN_SERVICO_PUBLICACOES = (
        "credencial-publicacoes-sintetica-de-integracao"
    )
    settings.IAM_TOKEN_SERVICO_ACOES = (
        "credencial-acoes-sintetica-de-integracao"
    )
    settings.IAM_DECISOES_INTERNAS_ATIVAS = True
    settings.IAM_DECISOES_PUBLICACOES_ATIVAS = True
    if perfil == "plataforma_quatro":
        settings.IAM_DECISOES_ACOES_ATIVAS = True
    if perfil == "carga":
        settings.IAM_URL_CARGA = os.environ["GPP_ENSAIO_IAM_URL"]
        settings.CARGA_IAM_IDENTIDADE_HTTP_REMOTA_ATIVA = True
        settings.CARGA_IAM_DECISAO_REMOTA_ATIVA = True
        settings.CARGA_IAM_WEBSOCKET_REMOTO_ATIVO = True
    if perfil == "publicacoes":
        settings.IAM_URL_PUBLICACOES = os.environ["GPP_ENSAIO_IAM_URL"]
        settings.PUBLICACOES_IAM_IDENTIDADE_HTTP_REMOTA_ATIVA = True
        settings.PUBLICACOES_IAM_WEBSOCKET_REMOTO_ATIVO = True
    if perfil == "acoes":
        settings.IAM_URL_ACOES = os.environ["GPP_ENSAIO_IAM_URL"]
        settings.ACOES_IAM_IDENTIDADE_HTTP_REMOTA_ATIVA = True

    from daphne.cli import CommandLineInterface  # pylint: disable=import-outside-toplevel

    CommandLineInterface().run(
        [
            "-b", "127.0.0.1", "-p", porta, "-v", "0",
            f"config.asgi_{perfil}_piloto:application",
        ]
    )


if __name__ == "__main__":
    main()
