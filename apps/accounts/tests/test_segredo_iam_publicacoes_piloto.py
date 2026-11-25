"""Garantias do segredo local do piloto, sem serviços externos."""

import os
import tempfile
from pathlib import Path
from unittest import TestCase

from django.core.exceptions import ImproperlyConfigured

from config.settings.segredo_iam_publicacoes_piloto import (
    carregar_token, provisionar_token,
)


class TestSegredoIAMPublicacoesPiloto(TestCase):
    """A criação é idempotente e não revela nem substitui o token."""

    def test_provisionamento_e_leitura(self):
        with tempfile.TemporaryDirectory() as temporario:
            diretorio = Path(temporario)
            caminho = diretorio / "token"
            self.assertTrue(provisionar_token(caminho))
            token = carregar_token(caminho=caminho)
            self.assertEqual(len(token), 64)
            self.assertEqual(caminho.stat().st_mode & 0o777, 0o600)
            self.assertFalse(provisionar_token(caminho))
            self.assertEqual(carregar_token(caminho=caminho), token)
            self.assertEqual(carregar_token(valor_ambiente="outro", caminho=caminho), "outro")

    def test_arquivo_inseguro_ou_symlink_e_recusado(self):
        with tempfile.TemporaryDirectory() as temporario:
            diretorio = Path(temporario)
            caminho = diretorio / "token"
            self.assertTrue(provisionar_token(caminho))
            os.chmod(caminho, 0o644)
            with self.assertRaises(ImproperlyConfigured):
                carregar_token(caminho=caminho)
            atalho = diretorio / "atalho"
            atalho.symlink_to(caminho)
            with self.assertRaises(ImproperlyConfigured):
                carregar_token(caminho=atalho)

    def test_sem_arquivo_preserva_valor_do_ambiente(self):
        with tempfile.TemporaryDirectory() as temporario:
            caminho = Path(temporario) / "ausente"
            self.assertEqual(carregar_token("valor", caminho), "valor")

    def test_diretorio_inseguro_e_recusado(self):
        with tempfile.TemporaryDirectory() as temporario:
            diretorio = Path(temporario)
            diretorio.chmod(0o755)
            with self.assertRaises(ImproperlyConfigured):
                provisionar_token(diretorio / "token")
