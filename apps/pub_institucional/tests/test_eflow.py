"""Testes da importação e do contrato HTTP do E-Flow."""

from uuid import UUID

import pytest
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import resolve
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.accounts.models import Aplicacao, Role, UserRole
from apps.pub_institucional.models import (ColetaEflow, DefinicaoFluxoEflow,
                                           EventoAuditoriaEflow,
                                           EventoAuditoriaPreferenciaEflow,
                                           PatriarcaEdocs, PerfilCalculoEflow,
                                           PreferenciaExibicaoEflow,
                                           ResultadoCalculoEflow,
                                           SituacaoColetaEflow)
from apps.pub_institucional.services.eflow import (AtorAuditoriaEflow,
                                                   importar_csv_eflow)
from apps.pub_institucional.services.recursos_funcionais import \
    semear_recursos_funcionais_publicacoes
from apps.pub_institucional.visoes import (
    VisaoColetaEflow, VisaoDefinicaoFluxoEflow, VisaoEventoAuditoriaEflow,
    VisaoEventoAuditoriaPreferenciaEflow, VisaoPreferenciaExibicaoEflow,
    VisaoResultadoCalculoEflow)

pytestmark = pytest.mark.django_db

ID_PATRIARCA = UUID("142e5085-4248-4211-80e5-f9e7d0ca4f9e")


def _csv(*linhas):
    cabecalho = "ID;Nome;Versão;Público-alvo;Patriarca;Órgão;Setor"
    return ("\ufeff" + "\r\n".join((cabecalho, *linhas)) + "\r\n").encode()


@pytest.fixture
def patriarca():
    return PatriarcaEdocs.objects.create(
        id_externo=ID_PATRIARCA,
        sigla="PMAB",
        nome="MUNICÍPIO DE ÁGUIA BRANCA",
        tipo_agente=5,
        descricao_tipo_agente="Organizacao",
    )


@pytest.fixture
def gestor_publicacoes_eflow():
    semear_recursos_funcionais_publicacoes()
    aplicacao = Aplicacao.objects.get(codigointerno="PUB_INSTITUCIONAL")
    perfil = Role.objects.get(
        aplicacao=aplicacao,
        codigoperfil="GESTOR_PUBLICACOES",
    )
    usuario = User.objects.create_user(username="gestor_publicacoes_eflow")
    UserRole.objects.create(user=usuario, aplicacao=aplicacao, role=perfil)
    usuario.refresh_from_db()
    return usuario


def test_importacao_preserva_snapshot_normaliza_e_calcula_indicadores(patriarca):
    conteudo = _csv(
        "00000000-0000-0000-0000-000000000001;Fluxo A;1;Cidadão;"
        "PMAB - MUNICÍPIO DE ÁGUIA BRANCA;Órgão A;Setor 1",
        "00000000-0000-0000-0000-000000000002;Fluxo B;2;Órgão;"
        "PMAB - MUNICÍPIO DE ÁGUIA BRANCA;Órgão A;Setor 2",
        "00000000-0000-0000-0000-000000000003;Fluxo C;1;Cidadão;"
        "PMAB - MUNICÍPIO DE ÁGUIA BRANCA;Órgão B;Setor 1",
    )

    coleta = importar_csv_eflow(
        nome_arquivo="definicoes.csv",
        conteudo=conteudo,
        ator=AtorAuditoriaEflow(usuario_id=7, nome="Gestor"),
    )

    assert coleta.situacao == SituacaoColetaEflow.CONCLUIDA
    assert bytes(coleta.arquivo_conteudo) == conteudo
    assert coleta.quantidade_fluxos == 3
    assert coleta.quantidade_orgaos_participantes == 2
    assert coleta.quantidade_setores_ativos == 3
    assert coleta.orgaos_maior_quantidade_fluxos == [
        {
            "patriarca": "PMAB - MUNICÍPIO DE ÁGUIA BRANCA",
            "orgao": "Órgão A",
            "quantidade_fluxos": 2,
            "percentual": "66.67",
        },
        {
            "patriarca": "PMAB - MUNICÍPIO DE ÁGUIA BRANCA",
            "orgao": "Órgão B",
            "quantidade_fluxos": 1,
            "percentual": "33.33",
        },
    ]
    assert coleta.distribuicao_publico_alvo == [
        {
            "publico_alvo": "Cidadão",
            "quantidade_fluxos": 2,
            "percentual": "66.67",
        },
        {
            "publico_alvo": "Órgão",
            "quantidade_fluxos": 1,
            "percentual": "33.33",
        },
    ]
    assert DefinicaoFluxoEflow.objects.filter(
        coleta=coleta,
        patriarca=patriarca,
    ).count() == 3
    assert set(
        EventoAuditoriaEflow.objects.filter(coleta=coleta).values_list(
            "tipo_evento",
            flat=True,
        )
    ) == {"COLETA_CONCLUIDA", "COLETA_INICIADA", "RESULTADOS_CALCULADOS"}

    completo = ResultadoCalculoEflow.objects.get(
        coleta=coleta,
        perfil=PerfilCalculoEflow.COMPLETO_TECNICO,
    )
    consolidado = ResultadoCalculoEflow.objects.get(
        coleta=coleta,
        perfil=PerfilCalculoEflow.CONSOLIDADO_PUBLICACAO,
    )
    assert completo.quantidade_orgaos_participantes == 2
    assert completo.orgaos_maior_quantidade_fluxos[0]["percentual"] == "66.67"
    assert consolidado.quantidade_orgaos_participantes == 2
    assert consolidado.orgaos_maior_quantidade_fluxos[0]["percentual"] == "66.67"
    assert [
        item["publico_alvo"]
        for item in consolidado.distribuicao_publico_alvo
    ] == ["Cidadão", "Órgão"]


def test_importacao_invalida_preserva_arquivo_e_falha_sem_linhas():
    coleta = importar_csv_eflow(
        nome_arquivo="definicoes.csv",
        conteudo=_csv(
            "00000000-0000-0000-0000-000000000001;Fluxo;1;Cidadão;"
            "DESCONHECIDO - Patriarca;Órgão;Setor"
        ),
        ator=AtorAuditoriaEflow(nome="teste"),
    )

    assert coleta.situacao == SituacaoColetaEflow.FALHOU
    assert coleta.codigo_erro == "PATRIARCA_NAO_RECONCILIADO"
    assert coleta.definicoes.count() == 0
    assert coleta.eventos_auditoria.filter(
        tipo_evento="COLETA_FALHOU"
    ).exists()


def test_perfil_consolidado_usa_texto_global_e_oculta_publicos_nao_exibidos(
    patriarca,
):
    PatriarcaEdocs.objects.create(
        id_externo=UUID("b817315b-63ea-417e-b191-6ecbc42e56e4"),
        sigla="PMBJN",
        nome="MUNICÍPIO DE BOM JESUS DO NORTE",
        tipo_agente=5,
        descricao_tipo_agente="Organizacao",
    )
    coleta = importar_csv_eflow(
        nome_arquivo="dois-patriarcas.csv",
        conteudo=_csv(
            "00000000-0000-0000-0000-000000000011;Fluxo A;1;Cidadão;"
            "PMAB - MUNICÍPIO DE ÁGUIA BRANCA;Órgão comum;Setor comum",
            "00000000-0000-0000-0000-000000000012;Fluxo B;1;Órgão;"
            "PMBJN - MUNICÍPIO DE BOM JESUS DO NORTE;Órgão comum;Setor comum",
            "00000000-0000-0000-0000-000000000013;Fluxo C;1;Setor;"
            "PMAB - MUNICÍPIO DE ÁGUIA BRANCA;Órgão comum;Setor comum",
            "00000000-0000-0000-0000-000000000014;Fluxo D;1;Lista de Permissão;"
            "PMBJN - MUNICÍPIO DE BOM JESUS DO NORTE;Órgão comum;Setor comum",
        ),
        ator=AtorAuditoriaEflow(nome="teste"),
    )

    completo = coleta.resultados_calculo.get(perfil="COMPLETO_TECNICO")
    consolidado = coleta.resultados_calculo.get(
        perfil="CONSOLIDADO_PUBLICACAO"
    )
    assert completo.quantidade_orgaos_participantes == 2
    assert completo.quantidade_setores_ativos == 2
    assert len(completo.distribuicao_publico_alvo) == 4
    assert consolidado.quantidade_orgaos_participantes == 1
    assert consolidado.quantidade_setores_ativos == 1
    assert consolidado.orgaos_maior_quantidade_fluxos == [
        {
            "patriarca": None,
            "orgao": "Órgão comum",
            "quantidade_fluxos": 4,
            "percentual": "100.00",
        }
    ]
    assert [
        item["publico_alvo"]
        for item in consolidado.distribuicao_publico_alvo
    ] == ["Cidadão", "Órgão"]
    assert all(
        item["percentual"] == "50.00"
        for item in consolidado.distribuicao_publico_alvo
    )


def test_rotas_eflow_expoem_coletas_linhas_e_auditoria():
    assert resolve("/api/pub-institucional/coletas-eflow/").func.cls is VisaoColetaEflow
    assert (
        resolve("/api/pub-institucional/definicoes-eflow/").func.cls
        is VisaoDefinicaoFluxoEflow
    )
    assert (
        resolve("/api/pub-institucional/auditoria-eflow/").func.cls
        is VisaoEventoAuditoriaEflow
    )
    assert (
        resolve("/api/pub-institucional/resultados-eflow/").func.cls
        is VisaoResultadoCalculoEflow
    )
    assert (
        resolve("/api/pub-institucional/preferencias-eflow/minha/").func.cls
        is VisaoPreferenciaExibicaoEflow
    )
    assert (
        resolve("/api/pub-institucional/auditoria-preferencias-eflow/").func.cls
        is VisaoEventoAuditoriaPreferenciaEflow
    )


def test_api_importa_csv_e_retorna_resultado_ao_front(
    patriarca,
    gestor_publicacoes_eflow,
):
    arquivo = SimpleUploadedFile(
        "definicoes.csv",
        _csv(
            "00000000-0000-0000-0000-000000000001;Fluxo;1;Cidadão;"
            "PMAB - MUNICÍPIO DE ÁGUIA BRANCA;Órgão;Setor"
        ),
        content_type="text/csv",
    )
    requisicao = APIRequestFactory().post(
        "/api/pub-institucional/coletas-eflow/",
        {
            "arquivo": arquivo,
            "ano_vigencia_inicio": 2024,
            "mes_vigencia_inicio": 1,
            "vigencia_retroativa": True,
        },
        format="multipart",
        HTTP_X_APP_CODE="PUB_INSTITUCIONAL",
    )
    force_authenticate(requisicao, user=gestor_publicacoes_eflow)

    resposta = VisaoColetaEflow.as_view({"post": "create"})(requisicao)

    assert resposta.status_code == 201
    assert resposta.data["situacao"] == "CONCLUIDA"
    assert resposta.data["ano_vigencia_inicio"] == 2024
    assert resposta.data["mes_vigencia_inicio"] == 1
    assert resposta.data["vigencia_retroativa"] is True
    assert resposta.data["quantidade_fluxos"] == 1
    assert {
        resultado["perfil"] for resultado in resposta.data["resultados_calculo"]
    } == {"COMPLETO_TECNICO", "CONSOLIDADO_PUBLICACAO"}
    assert "arquivo_conteudo" not in resposta.data
    assert ColetaEflow.objects.filter(pk=resposta.data["id"]).exists()


def test_usuario_inicializa_e_altera_preferencia_sem_justificativa(
    gestor_publicacoes_eflow,
):
    fabrica = APIRequestFactory()
    consultar = VisaoPreferenciaExibicaoEflow.as_view({"get": "minha"})
    requisicao = fabrica.get(
        "/api/pub-institucional/preferencias-eflow/minha/",
        HTTP_X_APP_CODE="PUB_INSTITUCIONAL",
    )
    force_authenticate(requisicao, user=gestor_publicacoes_eflow)

    resposta = consultar(requisicao)

    assert resposta.status_code == 200
    assert resposta.data["perfil_preferido"] == "CONSOLIDADO_PUBLICACAO"
    assert resposta.data["acoes_disponiveis"] == [
        "alterar_preferencia_exibicao"
    ]
    preferencia = PreferenciaExibicaoEflow.objects.get(
        usuario=gestor_publicacoes_eflow
    )
    assert preferencia.eventos_auditoria.get().tipo_evento == (
        "PREFERENCIA_INICIALIZADA"
    )

    alterar = VisaoPreferenciaExibicaoEflow.as_view({"patch": "minha"})
    requisicao = fabrica.patch(
        "/api/pub-institucional/preferencias-eflow/minha/",
        {"perfil_preferido": "COMPLETO_TECNICO"},
        format="json",
        HTTP_X_APP_CODE="PUB_INSTITUCIONAL",
    )
    force_authenticate(requisicao, user=gestor_publicacoes_eflow)

    resposta = alterar(requisicao)

    assert resposta.status_code == 200
    assert resposta.data["perfil_preferido"] == "COMPLETO_TECNICO"
    evento = EventoAuditoriaPreferenciaEflow.objects.get(
        tipo_evento="PREFERENCIA_ALTERADA"
    )
    assert evento.perfil_anterior == "CONSOLIDADO_PUBLICACAO"
    assert evento.perfil_atual == "COMPLETO_TECNICO"

    requisicao = fabrica.patch(
        "/api/pub-institucional/preferencias-eflow/minha/",
        {"perfil_preferido": "COMPLETO_TECNICO"},
        format="json",
        HTTP_X_APP_CODE="PUB_INSTITUCIONAL",
    )
    force_authenticate(requisicao, user=gestor_publicacoes_eflow)
    alterar(requisicao)
    assert preferencia.eventos_auditoria.count() == 2
