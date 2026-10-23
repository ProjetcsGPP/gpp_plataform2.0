"""Testes de views: organograma."""

import hashlib
from io import BytesIO

import pytest
from openpyxl import load_workbook

from apps.carga_org_lot.models import (FaseProcessoCargaInicial,
                                       ImportacaoPlanilha, ItemOrganograma,
                                       Patriarca, ProcessoCargaInicial,
                                       StatusImportacaoLocal,
                                       StatusLotacaoProcesso,
                                       StatusOrganogramaProcesso)
from apps.carga_org_lot.tests.view_helpers import (IMPORTACOES_URL,
                                                   ITENS_ORGANOGRAMA_URL,
                                                   PATRIARCAS_URL,
                                                   arquivo_planilha,
                                                   conteudo_lotacao)


@pytest.mark.django_db(transaction=True)
class TestItemOrganograma:
    def test_crud_completo(
        self,
        client_gestor_carga_lot,
        patriarca,
        tipo_organograma,
    ):
        upload = client_gestor_carga_lot.post(
            f"{IMPORTACOES_URL}upload/",
            {
                "idpatriarca_id": patriarca.pk,
                "idtipocarga_id": tipo_organograma.pk,
                "arquivo": arquivo_planilha(),
            },
            format="multipart",
        )
        importacao_id = upload.data["idimportacaoplanilha"]
        root = ItemOrganograma.objects.get(
            idimportacaoplanilha_id=importacao_id,
            idpai__isnull=True,
        )

        create_response = client_gestor_carga_lot.post(
            ITENS_ORGANOGRAMA_URL,
            {
                "idimportacaoplanilha_id": importacao_id,
                "idpai_id": root.pk,
                "strnome": "Gerência de Pessoas",
                "strsigla": "gep",
                "strnumero": "1.2",
                "strresponsavel": "Maria de Souza",
                "strcargo": "Gerente",
            },
            format="json",
        )
        assert create_response.status_code == 201
        pk = create_response.data["iditemorganograma"]
        assert create_response.data["strsigla"] == "GEP"
        assert create_response.data["strresponsavel"] == "Maria de Souza"
        assert create_response.data["strcargo"] == "Gerente"
        assert create_response.data["strreferenciapai"] == root.strsigla
        assert create_response.data["strabaorigem"] == "Edição manual"
        assert create_response.data["intlinhaorigem"] == 0
        importacao = ImportacaoPlanilha.objects.get(pk=importacao_id)
        assert importacao.strstatusimportacao == StatusImportacaoLocal.ALTERADA
        assert importacao.flgpossuialteracoes is True
        assert importacao.datprimeiraalteracao is not None
        assert importacao.datultimaalteracao is not None
        process = importacao.idprocessocargainicial
        process.refresh_from_db()
        assert process.strfaseatual == FaseProcessoCargaInicial.PREPARANDO_ORGANOGRAMA
        assert process.strstatusorganograma == StatusOrganogramaProcesso.EM_PREPARACAO

        list_response = client_gestor_carga_lot.get(
            ITENS_ORGANOGRAMA_URL,
            {"importacao": importacao_id},
        )
        assert list_response.status_code == 200
        assert list_response.data["count"] == 3
        assert (
            client_gestor_carga_lot.get(f"{ITENS_ORGANOGRAMA_URL}{pk}/").status_code
            == 200
        )

        patch_response = client_gestor_carga_lot.patch(
            f"{ITENS_ORGANOGRAMA_URL}{pk}/",
            {
                "strnome": "Gerência de Gestão de Pessoas",
                "strresponsavel": "Joana de Souza",
                "strcargo": "Gerente de Gestão",
            },
            format="json",
        )
        assert patch_response.status_code == 200
        assert patch_response.data["strnome"] == "Gerência de Gestão de Pessoas"
        assert patch_response.data["strresponsavel"] == "Joana de Souza"
        assert patch_response.data["strcargo"] == "Gerente de Gestão"

        delete_response = client_gestor_carga_lot.delete(
            f"{ITENS_ORGANOGRAMA_URL}{pk}/"
        )
        assert delete_response.status_code == 204
        assert ImportacaoPlanilha.objects.filter(pk=importacao_id).exists()
        assert list(process.historico.values_list("stracao", flat=True))[-3:] == [
            "ITEM_ORGANOGRAMA_INCLUIDO",
            "ITEM_ORGANOGRAMA_ALTERADO",
            "ITEM_ORGANOGRAMA_EXCLUIDO",
        ]

        import_response = client_gestor_carga_lot.get(
            f"{IMPORTACOES_URL}{importacao_id}/"
        )
        updated_url = import_response.data["organograma_atualizado_download_url"]
        assert updated_url.endswith(
            f"{IMPORTACOES_URL}{importacao_id}/organograma-atualizado/download/"
        )
        export_response = client_gestor_carga_lot.get(updated_url)
        assert export_response.status_code == 200
        workbook = load_workbook(BytesIO(export_response.content), data_only=True)
        worksheet = workbook["Organograma"]
        assert list(worksheet.values) == [
            ("Numero", "Nome", "Sigla", "Pai_Sigla", "Responsavel", "Cargo"),
            (
                "1",
                "PREFEITURA MUNICIPAL DE VILA VELHA",
                "PMVV",
                None,
                None,
                None,
            ),
            (
                "1.1",
                "SECRETARIA DE ADMINISTRAÇÃO",
                "SEMAD",
                "PMVV",
                None,
                None,
            ),
        ]

    @pytest.mark.parametrize(
        ("parent_type", "field", "value"),
        [
            ("organ", "strnome", "N" * 101),
            ("organ", "strsigla", "A" * 21),
            ("unit", "strnome", "N" * 101),
            ("unit", "strsigla", "A" * 26),
        ],
    )
    def test_crud_aplica_tamanhos_maximos_da_prodest(
        self,
        client_gestor_carga_lot,
        patriarca,
        tipo_organograma,
        parent_type,
        field,
        value,
    ):
        upload = client_gestor_carga_lot.post(
            f"{IMPORTACOES_URL}upload/",
            {
                "idpatriarca_id": patriarca.pk,
                "idtipocarga_id": tipo_organograma.pk,
                "arquivo": arquivo_planilha(),
            },
            format="multipart",
        )
        importacao_id = upload.data["idimportacaoplanilha"]
        root = ItemOrganograma.objects.get(
            idimportacaoplanilha_id=importacao_id,
            idpai__isnull=True,
        )
        organ = ItemOrganograma.objects.get(
            idimportacaoplanilha_id=importacao_id,
            idpai=root,
        )
        parent = root if parent_type == "organ" else organ
        payload = {
            "idimportacaoplanilha_id": importacao_id,
            "idpai_id": parent.pk,
            "strnome": "Nova estrutura",
            "strsigla": "NOVA",
        }
        payload[field] = value

        response = client_gestor_carga_lot.post(
            ITENS_ORGANOGRAMA_URL,
            payload,
            format="json",
        )

        assert response.status_code == 400
        assert field in response.data["errors"]

    def test_crud_rejeita_sigla_repetida_em_ramos_do_mesmo_orgao(
        self,
        client_gestor_carga_lot,
        patriarca,
        tipo_organograma,
    ):
        upload = client_gestor_carga_lot.post(
            f"{IMPORTACOES_URL}upload/",
            {
                "idpatriarca_id": patriarca.pk,
                "idtipocarga_id": tipo_organograma.pk,
                "arquivo": arquivo_planilha(),
            },
            format="multipart",
        )
        importacao_id = upload.data["idimportacaoplanilha"]
        root = ItemOrganograma.objects.get(
            idimportacaoplanilha_id=importacao_id,
            idpai__isnull=True,
        )
        organ = ItemOrganograma.objects.get(
            idimportacaoplanilha_id=importacao_id,
            idpai=root,
        )

        branches = []
        for suffix in ("A", "B"):
            response = client_gestor_carga_lot.post(
                ITENS_ORGANOGRAMA_URL,
                {
                    "idimportacaoplanilha_id": importacao_id,
                    "idpai_id": organ.pk,
                    "strnome": f"Diretoria {suffix}",
                    "strsigla": f"DIR{suffix}",
                },
                format="json",
            )
            assert response.status_code == 201
            branches.append(response.data["iditemorganograma"])

        first = client_gestor_carga_lot.post(
            ITENS_ORGANOGRAMA_URL,
            {
                "idimportacaoplanilha_id": importacao_id,
                "idpai_id": branches[0],
                "strnome": "Unidade Comum A",
                "strsigla": "COMUM",
            },
            format="json",
        )
        duplicate = client_gestor_carga_lot.post(
            ITENS_ORGANOGRAMA_URL,
            {
                "idimportacaoplanilha_id": importacao_id,
                "idpai_id": branches[1],
                "strnome": "Unidade Comum B",
                "strsigla": "COMUM",
            },
            format="json",
        )

        assert first.status_code == 201
        assert duplicate.status_code == 400
        assert "strsigla" in duplicate.data["errors"]

    def test_exclusao_de_subarvore_exige_confirmacao_e_informa_impacto(
        self,
        client_gestor_carga_lot,
        patriarca,
        tipo_organograma,
    ):
        upload = client_gestor_carga_lot.post(
            f"{IMPORTACOES_URL}upload/",
            {
                "idpatriarca_id": patriarca.pk,
                "idtipocarga_id": tipo_organograma.pk,
                "arquivo": arquivo_planilha(),
            },
            format="multipart",
        )
        importacao_id = upload.data["idimportacaoplanilha"]
        root = ItemOrganograma.objects.get(
            idimportacaoplanilha_id=importacao_id,
            idpai__isnull=True,
        )

        impact_response = client_gestor_carga_lot.get(
            f"{ITENS_ORGANOGRAMA_URL}{root.pk}/impacto-exclusao/"
        )
        assert impact_response.status_code == 200
        assert impact_response.data["total_descendentes"] == 1
        assert impact_response.data["total_excluidos"] == 2

        unconfirmed = client_gestor_carga_lot.delete(
            f"{ITENS_ORGANOGRAMA_URL}{root.pk}/"
        )
        assert unconfirmed.status_code == 409
        assert (
            unconfirmed.data["errors"]["code"]
            == "confirmacao_exclusao_subarvore_obrigatoria"
        )
        assert unconfirmed.data["errors"]["impacto"]["total_excluidos"] == 2
        assert (
            ItemOrganograma.objects.filter(
                idimportacaoplanilha_id=importacao_id
            ).count()
            == 2
        )

        confirmed = client_gestor_carga_lot.delete(
            f"{ITENS_ORGANOGRAMA_URL}{root.pk}/?confirmar_subarvore=true",
        )
        assert confirmed.status_code == 204
        assert not ItemOrganograma.objects.filter(
            idimportacaoplanilha_id=importacao_id
        ).exists()
        process = ProcessoCargaInicial.objects.get(idpatriarca=patriarca)
        history = process.historico.get(stracao="SUBARVORE_ORGANOGRAMA_EXCLUIDA")
        assert history.jsondetalhes["impacto"]["total_excluidos"] == 2

    def test_edicao_de_item_desatualiza_lotacao(
        self,
        client_gestor_carga_lot,
        patriarca,
        tipo_organograma,
        tipo_lotacao,
    ):
        organogram = client_gestor_carga_lot.post(
            f"{IMPORTACOES_URL}upload/",
            {
                "idpatriarca_id": patriarca.pk,
                "idtipocarga_id": tipo_organograma.pk,
                "arquivo": arquivo_planilha(),
            },
            format="multipart",
        )
        organogram_id = organogram.data["idimportacaoplanilha"]
        lotation = client_gestor_carga_lot.post(
            f"{IMPORTACOES_URL}upload/",
            {
                "idpatriarca_id": patriarca.pk,
                "idtipocarga_id": tipo_lotacao.pk,
                "idimportacaoorganograma_id": organogram_id,
                "arquivo": arquivo_planilha(
                    nome="lotacao.xlsx",
                    conteudo=conteudo_lotacao(),
                ),
            },
            format="multipart",
        )
        assert lotation.status_code == 201
        item = (
            ItemOrganograma.objects.filter(idimportacaoplanilha_id=organogram_id)
            .exclude(idpai=None)
            .get()
        )

        response = client_gestor_carga_lot.patch(
            f"{ITENS_ORGANOGRAMA_URL}{item.pk}/",
            {"strnome": "Secretaria de Administração Atualizada"},
            format="json",
        )

        assert response.status_code == 200
        process = ProcessoCargaInicial.objects.get(idpatriarca=patriarca)
        assert process.strstatuslotacao == StatusLotacaoProcesso.DESATUALIZADA

    def test_importacao_impede_exclusao_do_patriarca(
        self,
        client_gestor_carga_lot,
        patriarca,
        tipo_organograma,
    ):
        ImportacaoPlanilha.objects.create(
            idpatriarca=patriarca,
            idtipocarga=tipo_organograma,
            idstatusprogresso=patriarca.idstatusprogresso,
            strnomearquivo="organograma.xlsx",
            strtipomime="application/octet-stream",
            inttamanhoarquivo=3,
            strhasharquivo=hashlib.sha256(b"abc").hexdigest(),
            binconteudo=b"abc",
        )
        response = client_gestor_carga_lot.delete(f"{PATRIARCAS_URL}{patriarca.pk}/")
        assert response.status_code == 400
        assert Patriarca.objects.filter(pk=patriarca.pk).exists()
