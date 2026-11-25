"""Credencial local do piloto, compartilhada apenas pelos dois perfis separados."""

import os
import secrets
import stat
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured


CAMINHO_TOKEN = (
    Path(__file__).resolve().parents[2]
    / "infra/publicacoes-dev/runtime/secrets/iam_publicacoes_token"
)


def carregar_token(valor_ambiente="", caminho=CAMINHO_TOKEN):
    """Valor explícito do processo prevalece; senão lê arquivo 0600."""
    if valor_ambiente:
        return valor_ambiente
    try:
        descritor = os.open(caminho, os.O_RDONLY | os.O_NOFOLLOW)
    except FileNotFoundError:
        return valor_ambiente
    except OSError as exc:
        raise ImproperlyConfigured("Segredo IAM local inacessível") from exc
    try:
        metadados = os.fstat(descritor)
        if not (
            stat.S_ISREG(metadados.st_mode)
            and stat.S_IMODE(metadados.st_mode) == 0o600
            and metadados.st_uid == os.getuid()
            and metadados.st_size == 64
        ):
            raise ImproperlyConfigured("Segredo IAM local com proteção inválida")
        conteudo = os.read(descritor, 65)
    finally:
        os.close(descritor)
    try:
        token = conteudo.decode("ascii")
    except UnicodeDecodeError as exc:
        raise ImproperlyConfigured("Segredo IAM local inválido") from exc
    if len(token) != 64 or any(c not in "0123456789abcdef" for c in token):
        raise ImproperlyConfigured("Segredo IAM local inválido")
    return token


def provisionar_token(caminho=CAMINHO_TOKEN):
    """Cria uma vez, sem imprimir nem substituir a credencial existente."""
    diretorio = caminho.parent
    metadados = diretorio.stat()
    if not (
        stat.S_ISDIR(metadados.st_mode)
        and stat.S_IMODE(metadados.st_mode) == 0o700
        and metadados.st_uid == os.getuid()
    ):
        raise ImproperlyConfigured("Diretório local de segredos inseguro")
    if caminho.exists() or caminho.is_symlink():
        carregar_token(caminho=caminho)
        return False
    token = secrets.token_hex(32)
    try:
        descritor = os.open(
            caminho, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600,
        )
    except FileExistsError:
        carregar_token(caminho=caminho)
        return False
    try:
        os.write(descritor, token.encode("ascii"))
        os.fsync(descritor)
    finally:
        os.close(descritor)
    return True
