"""Testes de views: importacao lotacao validacao."""

import hashlib

import pytest

from apps.carga_org_lot.models import (CasoValidacaoImportacao,
                                       FaseProcessoCargaInicial,
                                       ImportacaoPlanilha, ItemLotacao,
                                       ItemOrganograma, ProcessoCargaInicial,
                                       StatusImportacaoLocal,
                                       StatusLotacaoProcesso)
from apps.carga_org_lot.tests.view_helpers import (CASOS_VALIDACAO_URL,
                                                   IMPORTACOES_URL,
                                                   PATRIARCAS_URL,
                                                   arquivo_planilha,
                                                   conteudo_lotacao,
                                                   conteudo_organograma)


@pytest.mark.django_db(transaction=True)
class TestValidacaoImportacaoLotacao:
    def test_lotacao_aceita_cpf_repetido_em_orgao_ou_unidade_diferente(
        self,
        client_gestor_carga_lot,
        patriarca,
        tipo_organograma,
        tipo_lotacao,
    ):
        organograma = client_gestor_carga_lot.post(
            f"{IMPORTACOES_URL}upload/",
            {
                "idpatriarca_id": patriarca.pk,
                "idtipocarga_id": tipo_organograma.pk,
                "arquivo": arquivo_planilha(
                    conteudo=conteudo_organograma(
                        linhas=[
                            (1, "Prefeitura Municipal de Vila Velha", "PMVV"),
                            ("1.1", "Secretaria de Administração", "SEMAD"),
                            ("1.1.1", "Secretaria de Administração", "SEMAD"),
                            ("1.1.2", "Recursos Humanos", "RH"),
                            ("1.2", "Secretaria de Saúde", "SESA"),
                            ("1.2.1", "Secretaria de Saúde", "SESA"),
                        ]
                    )
                ),
            },
            format="multipart",
        )
        cpf = "90396100457"
        linhas = [
            (
                "SEMAD",
                "Administração",
                "Maria da Silva",
                cpf,
                "Auxiliar Administrativo",
                "SEMAD",
                "Administração",
            ),
            (
                "SEMAD",
                "Administração",
                "Maria da Silva",
                cpf,
                "Auxiliar Administrativo",
                "RH",
                "RH",
            ),
            (
                "SESA",
                "Saúde",
                "Maria da Silva",
                cpf,
                "Auxiliar Administrativo",
                "SESA",
                "Saúde",
            ),
        ]

        response = client_gestor_carga_lot.post(
            f"{IMPORTACOES_URL}upload/",
            {
                "idpatriarca_id": patriarca.pk,
                "idtipocarga_id": tipo_lotacao.pk,
                "idimportacaoorganograma_id": organograma.data["idimportacaoplanilha"],
                "arquivo": arquivo_planilha(
                    nome="lotacao-cpf-em-lotacoes-distintas.xlsx",
                    conteudo=conteudo_lotacao(linhas=linhas),
                ),
            },
            format="multipart",
        )

        assert response.status_code == 201
        assert response.data["strstatusimportacao"] == "INCORPORADA"
        assert response.data["total_itens_lotacao"] == 3
        report = response.data["relatorio_validacao"]
        assert report["inttotalavisos"] == 0
        assert not any(
            occurrence["strcodigo"] == "cpf_duplicado_planilha"
            for occurrence in report["ocorrencias"]
        )

    def test_lotacao_rejeita_apenas_nome_servidor_ausente_quando_siglas_validas(
        self,
        client_gestor_carga_lot,
        patriarca,
        tipo_organograma,
        tipo_lotacao,
    ):
        organograma = client_gestor_carga_lot.post(
            f"{IMPORTACOES_URL}upload/",
            {
                "idpatriarca_id": patriarca.pk,
                "idtipocarga_id": tipo_organograma.pk,
                "arquivo": arquivo_planilha(),
            },
            format="multipart",
        )
        linha = (
            "SEMAD",
            "Nome divergente do órgão",
            "",
            "90396100457",
            "Auxiliar Administrativo",
            "SEMAD",
            "Nome divergente da unidade",
        )

        response = client_gestor_carga_lot.post(
            f"{IMPORTACOES_URL}upload/",
            {
                "idpatriarca_id": patriarca.pk,
                "idtipocarga_id": tipo_lotacao.pk,
                "idimportacaoorganograma_id": organograma.data["idimportacaoplanilha"],
                "arquivo": arquivo_planilha(
                    nome="lotacao-nomes-invalidos.xlsx",
                    conteudo=conteudo_lotacao(linhas=[linha]),
                ),
            },
            format="multipart",
        )

        assert response.status_code == 201
        codes = {
            error["codigo"]
            for error in response.data["relatorio_validacao"]["jsonresumo"]["erros"]
        }
        assert codes == {"nome_servidor_ausente"}
        assert response.data["strstatusimportacao"] == "AGUARDANDO_REVISAO"
        assert response.data["total_casos_pendentes"] == 1

    def test_lotacao_permite_corrigir_nome_servidor_e_incorporar(
        self,
        client_gestor_carga_lot,
        patriarca,
        tipo_organograma,
        tipo_lotacao,
    ):
        organograma = client_gestor_carga_lot.post(
            f"{IMPORTACOES_URL}upload/",
            {
                "idpatriarca_id": patriarca.pk,
                "idtipocarga_id": tipo_organograma.pk,
                "arquivo": arquivo_planilha(),
            },
            format="multipart",
        )
        linha = (
            "SEMAD",
            "Nome divergente do órgão",
            "",
            "90396100457",
            "Auxiliar Administrativo",
            "SEMAD",
            "Nome divergente da unidade",
        )
        uploaded = client_gestor_carga_lot.post(
            f"{IMPORTACOES_URL}upload/",
            {
                "idpatriarca_id": patriarca.pk,
                "idtipocarga_id": tipo_lotacao.pk,
                "idimportacaoorganograma_id": organograma.data["idimportacaoplanilha"],
                "arquivo": arquivo_planilha(
                    nome="lotacao-para-revisao.xlsx",
                    conteudo=conteudo_lotacao(linhas=[linha]),
                ),
            },
            format="multipart",
        )
        assert uploaded.status_code == 201
        cases = {
            case["strcodigo"]: case
            for case in uploaded.data["relatorio_validacao"]["casos"]
        }
        item_id = cases["nome_servidor_ausente"]["item_ids"][0]

        refused = client_gestor_carga_lot.post(
            (
                f"{CASOS_VALIDACAO_URL}"
                f"{cases['nome_servidor_ausente']['idcasovalidacao']}/resolver/"
            ),
            {
                "acao": "ACEITAR_COMO_INFORMADO",
                "justificativa": "Não corrigir.",
            },
            format="json",
        )
        assert refused.status_code == 400

        corrected = client_gestor_carga_lot.post(
            (
                f"{CASOS_VALIDACAO_URL}"
                f"{cases['nome_servidor_ausente']['idcasovalidacao']}/resolver/"
            ),
            {
                "acao": "CORRIGIR_MANUALMENTE",
                "alteracoes": [
                    {
                        "iditemlotacaoimportado": item_id,
                        "campos": {"strnomeservidor": "Maria da Silva"},
                    }
                ],
            },
            format="json",
        )
        assert corrected.status_code == 200
        assert corrected.data["strstatus"] == "CORRIGIDO"

        importacao_id = uploaded.data["idimportacaoplanilha"]
        importacao = ImportacaoPlanilha.objects.get(pk=importacao_id)
        assert (
            importacao.strstatusimportacao
            == StatusImportacaoLocal.PRONTA_PARA_INCORPORAR
        )
        incorporated = client_gestor_carga_lot.post(
            f"{IMPORTACOES_URL}{importacao_id}/incorporar-lotacao/",
            {},
            format="json",
        )
        assert incorporated.status_code == 200
        item = ItemLotacao.objects.get(idimportacaoplanilha_id=importacao_id)
        assert item.strnomeservidor == "Maria da Silva"
        assert item.strnomeorgao == "Nome divergente do órgão"
        assert item.strnomeunidade == "Nome divergente da unidade"

    def test_descartar_linha_resolve_suas_criticas_sem_registros_validos(
        self,
        client_gestor_carga_lot,
        patriarca,
        tipo_organograma,
        tipo_lotacao,
    ):
        organograma = client_gestor_carga_lot.post(
            f"{IMPORTACOES_URL}upload/",
            {
                "idpatriarca_id": patriarca.pk,
                "idtipocarga_id": tipo_organograma.pk,
                "arquivo": arquivo_planilha(),
            },
            format="multipart",
        )
        linha = (
            "SEMAD",
            "Nome divergente",
            "",
            "123",
            "",
            "INEXISTENTE",
            "Unidade inexistente",
        )
        uploaded = client_gestor_carga_lot.post(
            f"{IMPORTACOES_URL}upload/",
            {
                "idpatriarca_id": patriarca.pk,
                "idtipocarga_id": tipo_lotacao.pk,
                "idimportacaoorganograma_id": organograma.data["idimportacaoplanilha"],
                "arquivo": arquivo_planilha(
                    nome="lotacao-descartada.xlsx",
                    conteudo=conteudo_lotacao(linhas=[linha]),
                ),
            },
            format="multipart",
        )
        cases = uploaded.data["relatorio_validacao"]["casos"]
        discarded = client_gestor_carga_lot.post(
            f"{CASOS_VALIDACAO_URL}{cases[0]['idcasovalidacao']}/resolver/",
            {
                "acao": "DESCARTAR_LINHAS",
                "justificativa": "Registro será corrigido na planilha de origem.",
            },
            format="json",
        )
        assert discarded.status_code == 200

        importacao = ImportacaoPlanilha.objects.get(
            pk=uploaded.data["idimportacaoplanilha"]
        )
        assert (
            importacao.strstatusimportacao
            == StatusImportacaoLocal.SEM_REGISTROS_VALIDOS
        )
        assert not importacao.relatorio_validacao.casos.filter(
            strstatus="PENDENTE"
        ).exists()
        assert set(
            importacao.relatorio_validacao.casos.values_list("strstatus", flat=True)
        ) == {"LINHAS_DESCARTADAS"}
        assert importacao.itens_lotacao_importados.get().strsituacao == "DESCARTADO"

        incorporated = client_gestor_carga_lot.post(
            f"{IMPORTACOES_URL}{importacao.pk}/incorporar-lotacao/",
            {},
            format="json",
        )
        assert incorporated.status_code == 400
        assert not importacao.itens_lotacao.exists()

    def test_lotacao_invalida_le_tudo_rejeita_e_nao_persiste_itens(
        self,
        client_gestor_carga_lot,
        patriarca,
        tipo_organograma,
        tipo_lotacao,
    ):
        organograma = client_gestor_carga_lot.post(
            f"{IMPORTACOES_URL}upload/",
            {
                "idpatriarca_id": patriarca.pk,
                "idtipocarga_id": tipo_organograma.pk,
                "arquivo": arquivo_planilha(),
            },
            format="multipart",
        )
        invalid_rows = [
            (
                "SEMAD",
                "Secretaria de Administração",
                "Pessoa Um",
                "123",
                "",
                "INEXISTENTE",
                "Unidade inexistente",
            ),
            (
                "OUTRO",
                "Outro órgão",
                "Pessoa Dois",
                "987.654.321-00",
                "Analista",
                "SEMAD",
                "Secretaria de Administração",
            ),
        ]

        response = client_gestor_carga_lot.post(
            f"{IMPORTACOES_URL}upload/",
            {
                "idpatriarca_id": patriarca.pk,
                "idtipocarga_id": tipo_lotacao.pk,
                "idimportacaoorganograma_id": organograma.data["idimportacaoplanilha"],
                "arquivo": arquivo_planilha(
                    nome="lotacao-invalida.xlsx",
                    conteudo=conteudo_lotacao(linhas=invalid_rows),
                ),
            },
            format="multipart",
        )

        assert response.status_code == 201
        report = response.data["relatorio_validacao"]["jsonresumo"]
        assert report["leitura_completa"] is True
        assert report["total_linhas_lidas"] == 2
        assert {error["codigo"] for error in report["erros"]} >= {
            "cpf_invalido",
            "cargo_ausente",
            "unidade_invalida",
            "orgao_invalido",
        }
        importacao = ImportacaoPlanilha.objects.get(
            pk=response.data["idimportacaoplanilha"]
        )
        assert (
            importacao.strstatusimportacao == StatusImportacaoLocal.AGUARDANDO_REVISAO
        )
        assert not importacao.itens_lotacao.exists()
        assert importacao.itens_lotacao_importados.count() == 2
        assert CasoValidacaoImportacao.objects.filter(
            idrelatoriovalidacao=importacao.relatorio_validacao,
            strstatus="PENDENTE",
        ).exists()
        process = ProcessoCargaInicial.objects.get(idpatriarca=patriarca)
        assert process.strstatuslotacao == StatusLotacaoProcesso.COM_PENDENCIAS

    def test_novo_organograma_desatualiza_lotacoes_existentes(
        self,
        client_gestor_carga_lot,
        patriarca,
        tipo_organograma,
        tipo_lotacao,
    ):
        first_organogram = client_gestor_carga_lot.post(
            f"{IMPORTACOES_URL}upload/",
            {
                "idpatriarca_id": patriarca.pk,
                "idtipocarga_id": tipo_organograma.pk,
                "arquivo": arquivo_planilha(nome="organograma-1.xlsx"),
            },
            format="multipart",
        )
        assert first_organogram.status_code == 201

        lotation = client_gestor_carga_lot.post(
            f"{IMPORTACOES_URL}upload/",
            {
                "idpatriarca_id": patriarca.pk,
                "idtipocarga_id": tipo_lotacao.pk,
                "idimportacaoorganograma_id": first_organogram.data[
                    "idimportacaoplanilha"
                ],
                "arquivo": arquivo_planilha(
                    nome="lotacao.xlsx",
                    conteudo=conteudo_lotacao(),
                ),
            },
            format="multipart",
        )
        assert lotation.status_code == 201

        second_organogram = client_gestor_carga_lot.post(
            f"{IMPORTACOES_URL}upload/",
            {
                "idpatriarca_id": patriarca.pk,
                "idtipocarga_id": tipo_organograma.pk,
                "arquivo": arquivo_planilha(nome="organograma-2.xlsx"),
            },
            format="multipart",
        )

        assert second_organogram.status_code == 201
        process = ProcessoCargaInicial.objects.get(idpatriarca=patriarca)
        assert process.strfaseatual == FaseProcessoCargaInicial.PREPARANDO_ORGANOGRAMA
        assert process.strstatuslotacao == StatusLotacaoProcesso.DESATUALIZADA
        assert list(process.historico.values_list("stracao", flat=True)) == [
            "PROCESSO_CRIADO",
            "ORGANOGRAMA_IMPORTADO",
            "LOTACAO_IMPORTADA",
            "ORGANOGRAMA_IMPORTADO",
        ]

    def test_interrompe_quando_arquivo_nao_pode_ser_lido(
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
                "arquivo": arquivo_planilha(conteudo=b"arquivo corrompido"),
            },
            format="multipart",
        )

        assert response.status_code == 400
        report = response.data["errors"]["arquivo"]
        assert report["leitura_completa"] is False
        assert report["erros"][0]["codigo"] == "arquivo_ilegivel"
        importacao = ImportacaoPlanilha.objects.get(pk=report["idimportacaoplanilha"])
        assert importacao.strstatusimportacao == StatusImportacaoLocal.REJEITADA
        assert importacao.relatorio_validacao.flgleituracompleta is False

    def test_download_do_ultimo_organograma_pelo_patriarca(
        self,
        client_gestor_carga_lot,
        patriarca,
        tipo_organograma,
    ):
        antigo = b"organograma antigo"
        recente = b"organograma mais recente"
        for nome, conteudo in [
            ("antigo.xlsx", antigo),
            ("recente.xlsx", recente),
        ]:
            ImportacaoPlanilha.objects.create(
                idpatriarca=patriarca,
                idtipocarga=tipo_organograma,
                idstatusprogresso=patriarca.idstatusprogresso,
                strnomearquivo=nome,
                strtipomime=(
                    "application/vnd.openxmlformats-officedocument."
                    "spreadsheetml.sheet"
                ),
                inttamanhoarquivo=len(conteudo),
                strhasharquivo=hashlib.sha256(conteudo).hexdigest(),
                binconteudo=conteudo,
            )

        detail_response = client_gestor_carga_lot.get(
            f"{PATRIARCAS_URL}{patriarca.pk}/"
        )
        assert detail_response.status_code == 200
        assert detail_response.data["organograma_download_url"].endswith(
            f"{PATRIARCAS_URL}{patriarca.pk}/organograma/download/"
        )

        response = client_gestor_carga_lot.get(
            f"{PATRIARCAS_URL}{patriarca.pk}/organograma/download/"
        )
        assert response.status_code == 200
        assert response.content == recente
        assert "recente.xlsx" in response["Content-Disposition"]

    def test_download_de_organograma_inexistente_retorna_404(
        self,
        client_gestor_carga_lot,
        patriarca,
    ):
        response = client_gestor_carga_lot.get(
            f"{PATRIARCAS_URL}{patriarca.pk}/organograma/download/"
        )

        assert response.status_code == 404
        assert response.data["success"] is False

    def test_atualiza_status_e_exclui_importacao(
        self,
        client_gestor_carga_lot,
        patriarca,
        tipo_organograma,
        status_processando,
    ):
        importacao = ImportacaoPlanilha.objects.create(
            idpatriarca=patriarca,
            idtipocarga=tipo_organograma,
            idstatusprogresso=patriarca.idstatusprogresso,
            strnomearquivo="organograma.xlsx",
            strtipomime="application/octet-stream",
            inttamanhoarquivo=3,
            strhasharquivo=hashlib.sha256(b"abc").hexdigest(),
            binconteudo=b"abc",
        )

        patch_response = client_gestor_carga_lot.patch(
            f"{IMPORTACOES_URL}{importacao.pk}/",
            {"idstatusprogresso_id": status_processando.pk},
            format="json",
        )
        assert patch_response.status_code == 200
        assert patch_response.data["status"]["strdescricao"] == "Em progresso"

        delete_response = client_gestor_carga_lot.delete(
            f"{IMPORTACOES_URL}{importacao.pk}/"
        )
        assert delete_response.status_code == 204

    def test_referencia_e_opcional_e_pode_ser_atualizada(
        self,
        client_gestor_carga_lot,
        patriarca,
        tipo_organograma,
    ):
        upload_response = client_gestor_carga_lot.post(
            f"{IMPORTACOES_URL}upload/",
            {
                "idpatriarca_id": patriarca.pk,
                "idtipocarga_id": tipo_organograma.pk,
                "arquivo": arquivo_planilha(),
            },
            format="multipart",
        )
        assert upload_response.status_code == 201
        assert upload_response.data["strreferencia"] == ""

        importacao_id = upload_response.data["idimportacaoplanilha"]
        patch_response = client_gestor_carga_lot.patch(
            f"{IMPORTACOES_URL}{importacao_id}/",
            {"strreferencia": "Planilha revisada conforme reunião de 15/10."},
            format="json",
        )

        assert patch_response.status_code == 200
        assert patch_response.data["strreferencia"] == (
            "Planilha revisada conforme reunião de 15/10."
        )

    def test_exclusao_da_importacao_remove_fisicamente_os_itens(
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
                "arquivo": arquivo_planilha(),
            },
            format="multipart",
        )
        importacao_id = response.data["idimportacaoplanilha"]
        item_ids = list(
            ItemOrganograma.objects.filter(
                idimportacaoplanilha_id=importacao_id
            ).values_list("pk", flat=True)
        )

        delete_response = client_gestor_carga_lot.delete(
            f"{IMPORTACOES_URL}{importacao_id}/"
        )

        assert delete_response.status_code == 204
        assert not ImportacaoPlanilha.objects.filter(pk=importacao_id).exists()
        assert not ItemOrganograma.objects.filter(pk__in=item_ids).exists()
