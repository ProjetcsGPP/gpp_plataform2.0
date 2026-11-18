"""Testes de views: importacao validacao."""

import hashlib

import pytest

from apps.carga_org_lot.models import (ImportacaoPlanilha, ItemOrganograma,
                                       OcorrenciaValidacaoImportacao,
                                       ProcessoCargaInicial,
                                       ResultadoRelatorioValidacao,
                                       StatusImportacaoLocal,
                                       StatusOrganogramaProcesso)
from apps.carga_org_lot.tests.view_helpers import (IMPORTACOES_URL,
                                                   arquivo_planilha,
                                                   conteudo_organograma)


@pytest.mark.django_db(transaction=True)
class TestValidacaoImportacaoOrganograma:
    def test_resolve_pai_com_mesma_sigla_sem_numeracao(
        self,
        client_gestor_carga_lot,
        patriarca,
        tipo_organograma,
    ):
        content = conteudo_organograma(
            cabecalho=("Nome", "Sigla", "Pai_Sigla"),
            linhas=[
                ("Prefeitura", "PMVV", ""),
                ("Secretaria de Administração", "SEMAD", "PMVV"),
                ("Secretaria de Administração", "SEMAD", "SEMAD"),
            ],
        )

        response = client_gestor_carga_lot.post(
            f"{IMPORTACOES_URL}upload/",
            {
                "idpatriarca_id": patriarca.pk,
                "idtipocarga_id": tipo_organograma.pk,
                "arquivo": arquivo_planilha(conteudo=content),
            },
            format="multipart",
        )

        assert response.status_code == 201
        repeated = list(ItemOrganograma.objects.filter(strsigla="SEMAD"))
        assert len(repeated) == 2
        organ = next(item for item in repeated if item.idpai.strsigla == "PMVV")
        unit = next(item for item in repeated if item.idpai_id == organ.pk)
        assert unit.strnome == organ.strnome

    @pytest.mark.parametrize(
        ("linhas", "codigo"),
        [
            (
                [
                    (1, "Prefeitura", "PMVV"),
                    ("1.1", "Órgão A", "ORG"),
                    ("1.2", "Órgão B", "ORG"),
                ],
                "sigla_duplicada_entre_irmaos",
            ),
            (
                [
                    (1, "Prefeitura", "PMVV"),
                    ("1.1", "Órgão A", "ORGA"),
                    ("1.1.1", "Unidade A", "UNI"),
                    ("1.1.2", "Unidade B", "UNI"),
                ],
                "sigla_duplicada_no_orgao",
            ),
            (
                [
                    (1, "Prefeitura", "PMVV"),
                    ("1.1", "Órgão com sigla inválida", "PMVV"),
                ],
                "sigla_igual_ao_pai_no_nivel_2",
            ),
        ],
    )
    def test_rejeita_siglas_invalidas_no_escopo_hierarquico(
        self,
        client_gestor_carga_lot,
        patriarca,
        tipo_organograma,
        linhas,
        codigo,
    ):
        response = client_gestor_carga_lot.post(
            f"{IMPORTACOES_URL}upload/",
            {
                "idpatriarca_id": patriarca.pk,
                "idtipocarga_id": tipo_organograma.pk,
                "arquivo": arquivo_planilha(
                    conteudo=conteudo_organograma(linhas=linhas)
                ),
            },
            format="multipart",
        )

        assert response.status_code == 400
        errors = response.data["errors"]["arquivo"]["erros"]
        assert codigo in {error["codigo"] for error in errors}

    def test_rejeita_sigla_repetida_em_ramos_do_mesmo_orgao(
        self,
        client_gestor_carga_lot,
        patriarca,
        tipo_organograma,
    ):
        content = conteudo_organograma(
            linhas=[
                (1, "Prefeitura", "PMVV"),
                ("1.1", "Órgão A", "ORGA"),
                ("1.1.1", "Diretoria A", "DIRA"),
                ("1.1.1.1", "Unidade Comum A", "COMUM"),
                ("1.1.2", "Diretoria B", "DIRB"),
                ("1.1.2.1", "Unidade Comum B", "COMUM"),
            ]
        )

        response = client_gestor_carga_lot.post(
            f"{IMPORTACOES_URL}upload/",
            {
                "idpatriarca_id": patriarca.pk,
                "idtipocarga_id": tipo_organograma.pk,
                "arquivo": arquivo_planilha(conteudo=content),
            },
            format="multipart",
        )

        assert response.status_code == 400
        errors = response.data["errors"]["arquivo"]["erros"]
        matching = [
            error for error in errors if error["codigo"] == "sigla_duplicada_no_orgao"
        ]
        assert len(matching) == 2

    @pytest.mark.parametrize(
        ("name", "acronym", "number", "code"),
        [
            ("N" * 101, "ORGA", "1.1", "nome_orgao_muito_longo"),
            ("Órgão A", "A" * 21, "1.1", "sigla_orgao_muito_longa"),
            ("N" * 101, "UNIA", "1.1.1", "nome_unidade_muito_longo"),
            ("Unidade A", "A" * 26, "1.1.1", "sigla_unidade_muito_longa"),
        ],
    )
    def test_rejeita_tamanhos_superiores_aos_limites_da_prodest(
        self,
        client_gestor_carga_lot,
        patriarca,
        tipo_organograma,
        name,
        acronym,
        number,
        code,
    ):
        rows = [(1, "Prefeitura", "PMVV"), ("1.1", "Órgão A", "ORGA")]
        if number == "1.1":
            rows[1] = (number, name, acronym)
        else:
            rows.append((number, name, acronym))

        response = client_gestor_carga_lot.post(
            f"{IMPORTACOES_URL}upload/",
            {
                "idpatriarca_id": patriarca.pk,
                "idtipocarga_id": tipo_organograma.pk,
                "arquivo": arquivo_planilha(conteudo=conteudo_organograma(linhas=rows)),
            },
            format="multipart",
        )

        assert response.status_code == 400
        errors = response.data["errors"]["arquivo"]["erros"]
        assert code in {error["codigo"] for error in errors}

    def test_aceita_tamanhos_exatamente_nos_limites_da_prodest(
        self,
        client_gestor_carga_lot,
        patriarca,
        tipo_organograma,
    ):
        response = client_gestor_carga_lot.post(
            f"{IMPORTACOES_URL}upload/",
            {
                "idpatriarca_id": patriarca.pk,
                "idtipocarga_id": tipo_organograma.pk,
                "arquivo": arquivo_planilha(
                    conteudo=conteudo_organograma(
                        linhas=[
                            (1, "Prefeitura", "PMVV"),
                            ("1.1", "O" * 100, "A" * 20),
                            ("1.1.1", "U" * 100, "B" * 25),
                        ]
                    )
                ),
            },
            format="multipart",
        )

        assert response.status_code == 201

    def test_importa_responsavel_e_cargo_quando_informados(
        self,
        client_gestor_carga_lot,
        patriarca,
        tipo_organograma,
    ):
        content = conteudo_organograma(
            cabecalho=("Numero", "Nome", "Sigla", "Responsável", "Cargo/Função"),
            linhas=[
                (1, "Prefeitura", "PMVV", "Maria da Silva", "Prefeita"),
                (
                    "1.1",
                    "Secretaria de Administração",
                    "SEMAD",
                    "João Souza",
                    "Secretário Municipal",
                ),
            ],
        )

        response = client_gestor_carga_lot.post(
            f"{IMPORTACOES_URL}upload/",
            {
                "idpatriarca_id": patriarca.pk,
                "idtipocarga_id": tipo_organograma.pk,
                "arquivo": arquivo_planilha(conteudo=content),
            },
            format="multipart",
        )

        assert response.status_code == 201
        root = ItemOrganograma.objects.get(strsigla="PMVV")
        child = ItemOrganograma.objects.get(strsigla="SEMAD")
        assert root.strresponsavel == "MARIA DA SILVA"
        assert root.strcargo == "PREFEITA"
        assert child.strresponsavel == "JOÃO SOUZA"
        assert child.strcargo == "SECRETÁRIO MUNICIPAL"

    def test_rejeita_importacao_e_retorna_todos_os_erros(
        self,
        client_gestor_carga_lot,
        patriarca,
        tipo_organograma,
    ):
        conteudo = conteudo_organograma(
            linhas=[
                (1, "Prefeitura", "PMVV"),
                ("1.1", "Secretaria", "SEC REPETIDA"),
                ("1.2", "Secretaria", "SEC REPETIDA"),
                ("1.3.1", "", "SEM NOME"),
            ]
        )
        response = client_gestor_carga_lot.post(
            f"{IMPORTACOES_URL}upload/",
            {
                "idpatriarca_id": patriarca.pk,
                "idtipocarga_id": tipo_organograma.pk,
                "arquivo": arquivo_planilha(conteudo=conteudo),
            },
            format="multipart",
        )

        assert response.status_code == 400
        report = response.data["errors"]["arquivo"]
        assert report["leitura_completa"] is True
        assert report["total_erros"] >= 6
        assert {error["codigo"] for error in report["erros"]} >= {
            "nome_obrigatorio",
            "nome_duplicado_entre_irmaos",
            "sigla_duplicada_entre_irmaos",
            "sigla_com_espaco",
            "numero_pai_inexistente",
        }
        importacao = ImportacaoPlanilha.objects.get(pk=report["idimportacaoplanilha"])
        assert importacao.strstatusimportacao == StatusImportacaoLocal.REJEITADA
        assert not importacao.itens_organograma.exists()
        persisted_report = importacao.relatorio_validacao
        assert persisted_report.strresultado == ResultadoRelatorioValidacao.INVALIDO
        assert persisted_report.inttotalerros == report["total_erros"]
        assert (
            OcorrenciaValidacaoImportacao.objects.filter(
                idrelatoriovalidacao=persisted_report
            ).count()
            == report["total_erros"]
        )
        process = ProcessoCargaInicial.objects.get(idpatriarca=patriarca)
        assert process.strstatusorganograma == StatusOrganogramaProcesso.COM_PENDENCIAS

    def test_exige_selecao_quando_organograma_tem_varias_abas(
        self,
        client_gestor_carga_lot,
        patriarca,
        tipo_organograma,
    ):
        conteudo = conteudo_organograma(
            segunda_aba=(
                ("Numero", "Nome", "Sigla"),
                [(1, "Outro patriarca", "OUTRO")],
            )
        )
        response = client_gestor_carga_lot.post(
            f"{IMPORTACOES_URL}upload/",
            {
                "idpatriarca_id": patriarca.pk,
                "idtipocarga_id": tipo_organograma.pk,
                "arquivo": arquivo_planilha(conteudo=conteudo),
            },
            format="multipart",
        )

        assert response.status_code == 409
        report = response.data["errors"]["arquivo"]
        assert report["codigo"] == "selecao_aba_obrigatoria"
        assert [aba["nome"] for aba in report["abas"]] == [
            "Organograma",
            "Segunda aba",
        ]
        assert not ImportacaoPlanilha.objects.exists()

    def test_importacao_rejeitada_nao_e_base_para_lotacao(
        self,
        client_gestor_carga_lot,
        patriarca,
        tipo_organograma,
        tipo_lotacao,
    ):
        rejected = ImportacaoPlanilha.objects.create(
            idpatriarca=patriarca,
            idtipocarga=tipo_organograma,
            idstatusprogresso=patriarca.idstatusprogresso,
            strnomearquivo="organograma-rejeitado.xlsx",
            strtipomime="application/octet-stream",
            inttamanhoarquivo=3,
            strhasharquivo=hashlib.sha256(b"abc").hexdigest(),
            strstatusimportacao=StatusImportacaoLocal.REJEITADA,
            binconteudo=b"abc",
        )

        response = client_gestor_carga_lot.post(
            f"{IMPORTACOES_URL}upload/",
            {
                "idpatriarca_id": patriarca.pk,
                "idtipocarga_id": tipo_lotacao.pk,
                "idimportacaoorganograma_id": rejected.pk,
                "arquivo": arquivo_planilha(nome="lotacao.xlsx"),
            },
            format="multipart",
        )

        assert response.status_code == 400
        assert "idimportacaoorganograma_id" in response.data["errors"]

    def test_importa_somente_aba_selecionada_e_persiste_hierarquia(
        self,
        client_gestor_carga_lot,
        patriarca,
        tipo_organograma,
    ):
        conteudo = conteudo_organograma(
            segunda_aba=(
                ("Numero", "Nome", "Sigla"),
                [(1, "Outro patriarca", "OUTRO")],
            )
        )
        response = client_gestor_carga_lot.post(
            f"{IMPORTACOES_URL}upload/",
            {
                "idpatriarca_id": patriarca.pk,
                "idtipocarga_id": tipo_organograma.pk,
                "aba": "Organograma",
                "arquivo": arquivo_planilha(conteudo=conteudo),
            },
            format="multipart",
        )

        assert response.status_code == 201
        assert response.data["strabaimportada"] == "Organograma"
        assert response.data["total_itens_organograma"] == 2
        items = ItemOrganograma.objects.order_by("intlinhaorigem")
        assert [item.strsigla for item in items] == ["PMVV", "SEMAD"]
        assert items[0].idpai_id is None
        assert items[1].idpai_id == items[0].pk
