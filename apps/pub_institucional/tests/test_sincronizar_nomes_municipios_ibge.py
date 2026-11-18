"""Testes da reconciliação dos nomes municipais com o IBGE."""

from io import StringIO
from unittest.mock import patch

import pytest
from django.core.management import call_command

from apps.pub_institucional.models import (EventoAuditoriaMunicipioEdocs,
                                           MunicipioEdocs)

pytestmark = pytest.mark.django_db


@patch(
    "apps.pub_institucional.management.commands."
    "sincronizar_nomes_municipios_ibge.listar_municipios_ibge"
)
def test_simula_e_aplica_nome_oficial_com_auditoria(listar_municipios):
    listar_municipios.return_value = [
        {"id": 3200102, "nome": "Afonso Cláudio", "codigo_uf": 32}
    ]
    municipio = MunicipioEdocs.objects.create(
        codigo_ibge=3200102,
        nome="3200102 - AFONSO CLAUDIO",
    )

    saida = StringIO()
    call_command("sincronizar_nomes_municipios_ibge", stdout=saida)
    municipio.refresh_from_db()
    assert municipio.nome == "3200102 - AFONSO CLAUDIO"
    assert "1 correção(ões) pendente(s)" in saida.getvalue()

    saida = StringIO()
    call_command(
        "sincronizar_nomes_municipios_ibge",
        "--aplicar",
        stdout=saida,
    )
    municipio.refresh_from_db()

    assert municipio.nome == "Afonso Cláudio"
    assert municipio.versao == 2
    evento = EventoAuditoriaMunicipioEdocs.objects.get(
        municipio=municipio,
        tipo_evento="CADASTRO_CORRIGIDO",
    )
    assert evento.dados_anteriores["nome"] == "3200102 - AFONSO CLAUDIO"
    assert evento.dados_atuais["nome"] == "Afonso Cláudio"
    assert evento.criado_por_nome == "sincronizacao_nomes_municipios_ibge"
    assert "1 alteração(ões)" in saida.getvalue()
