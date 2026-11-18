from uuid import UUID

import pytest

from apps.pub_institucional.models import (DescricaoTipoAgenteEdocs,
                                           TipoAgenteEdocs)
from apps.pub_institucional.services.patriarcas_edocs import (
    ErroValidacaoPatriarcasEdocs, _normalizar_registro)

ID_PATRIARCA = UUID("b817315b-63ea-417e-b191-6ecbc42e56e4")


@pytest.mark.parametrize(
    ("codigo", "descricao"),
    [
        (TipoAgenteEdocs.CIDADAO, DescricaoTipoAgenteEdocs.CIDADAO),
        (TipoAgenteEdocs.PAPEL, DescricaoTipoAgenteEdocs.PAPEL),
        (TipoAgenteEdocs.GRUPO, DescricaoTipoAgenteEdocs.GRUPO),
        (TipoAgenteEdocs.UNIDADE, DescricaoTipoAgenteEdocs.UNIDADE),
        (TipoAgenteEdocs.ORGANIZACAO, DescricaoTipoAgenteEdocs.ORGANIZACAO),
        (TipoAgenteEdocs.SISTEMA, DescricaoTipoAgenteEdocs.SISTEMA),
        (
            TipoAgenteEdocs.NAO_IDENTIFICADO,
            DescricaoTipoAgenteEdocs.NAO_IDENTIFICADO,
        ),
    ],
)
def test_normalizacao_aceita_tipos_oficiais(codigo, descricao):
    registro = _normalizar_registro(
        {
            "id": str(ID_PATRIARCA),
            "sigla": "TESTE",
            "nome": "AGENTE DE TESTE",
            "tipoAgente": codigo,
            "descricaoTipoAgente": descricao,
        }
    )

    assert registro["tipo_agente"] == codigo
    assert registro["descricao_tipo_agente"] == descricao


def test_normalizacao_recusa_codigo_e_descricao_divergentes():
    with pytest.raises(
        ErroValidacaoPatriarcasEdocs,
        match="código e a descrição",
    ):
        _normalizar_registro(
            {
                "id": str(ID_PATRIARCA),
                "sigla": "TESTE",
                "nome": "AGENTE DE TESTE",
                "tipoAgente": TipoAgenteEdocs.ORGANIZACAO,
                "descricaoTipoAgente": DescricaoTipoAgenteEdocs.SISTEMA,
            }
        )
