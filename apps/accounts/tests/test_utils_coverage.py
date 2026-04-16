"""
test_utils_coverage.py
=======================

Testes de cobertura para apps/accounts/utils.py.

Linhas alvo: 13-35, 45
  - log_frontend_error: caminho feliz (13-25), caminho de excecao (31-33)
  - get_client_ip: via X-Forwarded-For (45) e via REMOTE_ADDR

Meta: cobertura de utils.py de 50% → >= 80%
"""

import json
from unittest.mock import MagicMock

from apps.accounts.utils import get_client_ip, log_frontend_error


class TestGetClientIp:
    """Cobre a linha 45 de utils.py."""

    def test_retorna_ip_do_remote_addr(self):
        request = MagicMock()
        request.META = {"REMOTE_ADDR": "192.168.1.1"}
        assert get_client_ip(request) == "192.168.1.1"

    def test_retorna_primeiro_ip_do_x_forwarded_for(self):
        """Linha 45: prioriza X-Forwarded-For sobre REMOTE_ADDR."""
        request = MagicMock()
        request.META = {
            "HTTP_X_FORWARDED_FOR": "10.0.0.1, 172.16.0.1, 192.168.1.1",
            "REMOTE_ADDR": "192.168.1.99",
        }
        assert get_client_ip(request) == "10.0.0.1"

    def test_retorna_ip_unico_no_x_forwarded_for(self):
        request = MagicMock()
        request.META = {
            "HTTP_X_FORWARDED_FOR": "10.0.0.5",
            "REMOTE_ADDR": "192.168.1.99",
        }
        assert get_client_ip(request) == "10.0.0.5"

    def test_ip_com_espacos_e_removido(self):
        """strip() deve limpar espaços ao redor do IP."""
        request = MagicMock()
        request.META = {
            "HTTP_X_FORWARDED_FOR": "  10.0.0.1  , 172.16.0.1",
        }
        assert get_client_ip(request) == "10.0.0.1"


class TestLogFrontendError:
    """
    Cobre as linhas 13-35 de utils.py.
    Não requer db pois a função não usa o banco.
    """

    def test_caminho_feliz_retorna_logged(self):
        """Linhas 13-25: JSON válido com todos os campos."""
        payload = json.dumps(
            {
                "timestamp": "2026-04-09T10:00:00Z",
                "level": "ERROR",
                "message": "Uncaught TypeError",
                "context": "ACOES_PNGI",
                "url": "https://app.gpp.br/acoes",
                "userAgent": "Mozilla/5.0",
            }
        )
        result = log_frontend_error(payload)
        assert result["status"] == "logged"

    def test_caminho_feliz_json_parcial(self):
        """JSON com apenas message — campos opcionais devem ter default."""
        payload = json.dumps({"message": "Erro simples"})
        result = log_frontend_error(payload)
        assert result["status"] == "logged"

    def test_json_invalido_retorna_error(self):
        """Linhas 31-33: JSON inválido dispara except e retorna status=error."""
        result = log_frontend_error("nao-e-json-valido{{{")
        assert result["status"] == "error"

    def test_exception_interna_retorna_error(self):
        """
        Se json.loads lançar qualquer exceção, retorna status=error
        sem propagar.
        """
        result = log_frontend_error(None)  # type: ignore[arg-type]
        assert result["status"] == "error"
