from uuid import UUID

import pytest

from apps.pub_institucional.models import (DecisaoDivergenciaPatriarca,
                                           DivergenciaPatriarcaEdocs,
                                           EventoAuditoriaPatriarcaEdocs,
                                           PatriarcaEdocs,
                                           SituacaoColetaPatriarcas,
                                           SituacaoDivergenciaPatriarca,
                                           TipoComparacaoPatriarca,
                                           TipoEventoAuditoriaPatriarca)
from apps.pub_institucional.services.patriarcas_edocs import (
    AtorAuditoriaEdocs, ErroDecisaoPatriarcaEdocs,
    aplicar_decisao_divergencia_patriarca, definir_selecao_coleta_patriarca,
    sincronizar_patriarcas_edocs)

pytestmark = pytest.mark.django_db

ID_PATRIARCA = UUID("b817315b-63ea-417e-b191-6ecbc42e56e4")
ATOR = AtorAuditoriaEdocs(usuario_id=7, nome="gestor")


class ClienteSimulado:
    def __init__(self, resposta):
        self.resposta = resposta

    def listar_patriarcas(self):
        return self.resposta


def registro_remoto(**alteracoes):
    registro = {
        "id": str(ID_PATRIARCA),
        "sigla": "PMBJN",
        "nome": "MUNICÍPIO DE BOM JESUS DO NORTE",
        "tipoAgente": 5,
        "descricaoTipoAgente": "Organizacao",
    }
    registro.update(alteracoes)
    return registro


def criar_patriarca_catalogo(**alteracoes):
    valores = {
        "id_externo": ID_PATRIARCA,
        "sigla": "PMBJN",
        "nome": "MUNICÍPIO DE BOM JESUS DO NORTE",
        "tipo_agente": 5,
        "descricao_tipo_agente": "Organizacao",
    }
    valores.update(alteracoes)
    return PatriarcaEdocs.objects.create(**valores)


def test_sincronizacao_registra_novo_sem_alterar_catalogo():
    coleta = sincronizar_patriarcas_edocs(
        ator=ATOR,
        cliente=ClienteSimulado([registro_remoto()]),
    )

    assert coleta.situacao == SituacaoColetaPatriarcas.CONCLUIDA_COM_DIVERGENCIAS
    assert coleta.quantidade_novos == 1
    assert coleta.quantidade_pendentes == 1
    assert not PatriarcaEdocs.objects.exists()
    divergencia = DivergenciaPatriarcaEdocs.objects.get()
    assert divergencia.comparacao == TipoComparacaoPatriarca.NOVO
    assert divergencia.situacao == SituacaoDivergenciaPatriarca.PENDENTE
    assert divergencia.dados_observados["id_externo"] == str(ID_PATRIARCA)


def test_sincronizacao_registra_alteracao_e_preserva_catalogo():
    patriarca = criar_patriarca_catalogo(coletar_detalhes=True)

    coleta = sincronizar_patriarcas_edocs(
        ator=ATOR,
        cliente=ClienteSimulado([registro_remoto(nome="NOME ALTERADO")]),
    )

    patriarca.refresh_from_db()
    assert patriarca.nome == "MUNICÍPIO DE BOM JESUS DO NORTE"
    assert patriarca.coletar_detalhes is True
    assert coleta.quantidade_alterados == 1
    divergencia = DivergenciaPatriarcaEdocs.objects.get()
    assert divergencia.campos_alterados == ["nome"]


def test_sincronizacao_registra_patriarca_ativo_ausente_na_origem():
    patriarca = criar_patriarca_catalogo(coletar_detalhes=True)
    outro_id = "142e5085-4248-4211-80e5-f9e7d0ca4f9e"

    coleta = sincronizar_patriarcas_edocs(
        ator=ATOR,
        cliente=ClienteSimulado([registro_remoto(id=outro_id, sigla="PMAB")]),
    )

    patriarca.refresh_from_db()
    assert patriarca.ativo is True
    assert patriarca.coletar_detalhes is True
    assert coleta.quantidade_ausentes == 1
    assert coleta.divergencias.filter(
        comparacao=TipoComparacaoPatriarca.AUSENTE
    ).exists()


def test_decisao_adicionar_cria_catalogo_e_evento_auditoria():
    coleta = sincronizar_patriarcas_edocs(
        ator=ATOR,
        cliente=ClienteSimulado([registro_remoto()]),
    )
    divergencia = coleta.divergencias.get()

    aplicar_decisao_divergencia_patriarca(
        divergencia.pk,
        decisao=DecisaoDivergenciaPatriarca.ADICIONAR,
        justificativa="Cadastro confirmado junto à PRODEST.",
        ator=ATOR,
        coletar_detalhes=True,
    )

    patriarca = PatriarcaEdocs.objects.get()
    divergencia.refresh_from_db()
    assert patriarca.coletar_detalhes is True
    assert divergencia.situacao == SituacaoDivergenciaPatriarca.APLICADA
    assert divergencia.revisado_por_id == ATOR.usuario_id
    assert EventoAuditoriaPatriarcaEdocs.objects.filter(
        tipo_evento=TipoEventoAuditoriaPatriarca.CATALOGO_INCLUIDO,
        patriarca=patriarca,
    ).exists()


def test_decisao_atualizar_preserva_selecao_de_coleta():
    patriarca = criar_patriarca_catalogo(coletar_detalhes=True)
    coleta = sincronizar_patriarcas_edocs(
        ator=ATOR,
        cliente=ClienteSimulado([registro_remoto(nome="NOME CONFIRMADO")]),
    )

    aplicar_decisao_divergencia_patriarca(
        coleta.divergencias.get().pk,
        decisao=DecisaoDivergenciaPatriarca.ATUALIZAR,
        justificativa="Alteração confirmada junto à PRODEST.",
        ator=ATOR,
    )

    patriarca.refresh_from_db()
    assert patriarca.nome == "NOME CONFIRMADO"
    assert patriarca.coletar_detalhes is True
    assert patriarca.versao == 2


def test_decisao_manter_nao_altera_catalogo():
    patriarca = criar_patriarca_catalogo()
    coleta = sincronizar_patriarcas_edocs(
        ator=ATOR,
        cliente=ClienteSimulado([registro_remoto(nome="NOME NÃO CONFIRMADO")]),
    )

    divergencia = aplicar_decisao_divergencia_patriarca(
        coleta.divergencias.get().pk,
        decisao=DecisaoDivergenciaPatriarca.MANTER,
        justificativa="Aguardando correção da origem pela PRODEST.",
        ator=ATOR,
    )

    patriarca.refresh_from_db()
    assert patriarca.nome == "MUNICÍPIO DE BOM JESUS DO NORTE"
    assert divergencia.situacao == SituacaoDivergenciaPatriarca.MANTIDA


def test_selecao_detalhada_exige_ativo_e_gera_auditoria():
    patriarca = criar_patriarca_catalogo()

    definir_selecao_coleta_patriarca(
        patriarca.pk,
        coletar_detalhes=True,
        justificativa="Município incluído na coleta mensal.",
        ator=ATOR,
    )

    patriarca.refresh_from_db()
    assert patriarca.coletar_detalhes is True
    assert patriarca.versao == 2
    assert EventoAuditoriaPatriarcaEdocs.objects.filter(
        patriarca=patriarca,
        tipo_evento=TipoEventoAuditoriaPatriarca.SELECAO_COLETA_ALTERADA,
    ).exists()

    patriarca.ativo = False
    patriarca.coletar_detalhes = False
    patriarca.save()
    with pytest.raises(ErroDecisaoPatriarcaEdocs):
        definir_selecao_coleta_patriarca(
            patriarca.pk,
            coletar_detalhes=True,
            justificativa="Tentativa inválida.",
            ator=ATOR,
        )


def test_resposta_remota_invalida_marca_falha():
    coleta = sincronizar_patriarcas_edocs(
        ator=ATOR,
        cliente=ClienteSimulado([registro_remoto(id="não-é-uuid")]),
    )

    assert coleta.situacao == SituacaoColetaPatriarcas.FALHOU
    assert coleta.codigo_erro == "ErroValidacaoPatriarcasEdocs"
    assert not PatriarcaEdocs.objects.exists()
    assert not DivergenciaPatriarcaEdocs.objects.exists()
