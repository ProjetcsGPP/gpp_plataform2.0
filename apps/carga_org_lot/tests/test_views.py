"""Testes das APIs de Carga de Organograma e Lotação."""

import hashlib
from io import BytesIO
from uuid import uuid4

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from openpyxl import Workbook

from apps.carga_org_lot.models import (
    DetalheStatusCarga,
    ImportacaoPlanilha,
    ItemOrganograma,
    Patriarca,
    StatusCarga,
    StatusProgresso,
    TipoCarga,
    TokenEnvioCarga,
)
from apps.carga_org_lot.views import (
    CargaOrgLotViewSet,
    HistoricoCargaViewSet,
    ImportacaoPlanilhaViewSet,
    ItemOrganogramaViewSet,
    PatriarcaViewSet,
    StatusCargaViewSet,
    StatusProgressoViewSet,
    TipoCargaViewSet,
)

BASE_URL = "/api/carga-org-lot"
PATRIARCAS_URL = f"{BASE_URL}/patriarcas/"
IMPORTACOES_URL = f"{BASE_URL}/importacoes/"
ITENS_ORGANOGRAMA_URL = f"{BASE_URL}/itens-organograma/"
CARGAS_URL = f"{BASE_URL}/cargas/"
HISTORICO_URL = f"{BASE_URL}/historico-cargas/"


@pytest.fixture
def status_novo(db):
    return StatusProgresso.objects.create(
        idstatusprogresso=1,
        strdescricao="Novo",
    )


@pytest.fixture
def status_processando(db):
    return StatusProgresso.objects.create(
        idstatusprogresso=2,
        strdescricao="Em progresso",
    )


@pytest.fixture
def tipo_organograma(db):
    return TipoCarga.objects.create(
        idtipocarga=3,
        strdescricao="Organograma",
    )


@pytest.fixture
def tipo_lotacao(db):
    return TipoCarga.objects.create(
        idtipocarga=4,
        strdescricao="Lotações",
    )


@pytest.fixture
def status_carga_recebida(db):
    return StatusCarga.objects.create(
        idstatuscarga=1,
        strdescricao="Recebida",
        flgsucesso=0,
    )


@pytest.fixture
def patriarca(status_novo):
    return Patriarca.objects.create(
        idexternopatriarca=uuid4(),
        strsiglapatriarca="PMVV",
        strnome="Prefeitura Municipal de Vila Velha",
        datcriacao=timezone.now(),
        idstatusprogresso=status_novo,
    )


@pytest.fixture
def carga(status_processando, tipo_organograma):
    return TokenEnvioCarga.objects.create(
        strtoken="credencial-que-nao-pode-ser-exposta",
        idtipocarga=tipo_organograma,
        idstatusprogresso=status_processando,
    )


def conteudo_organograma(
    linhas=None,
    cabecalho=("Numero", "Nome", "Sigla"),
    segunda_aba=None,
):
    linhas = linhas or [
        (1, "Prefeitura Municipal de Vila Velha", "PMVV"),
        ("1.1", "Secretaria de Administração", "SEMAD"),
    ]
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "Organograma"
    worksheet.append(cabecalho)
    for linha in linhas:
        worksheet.append(linha)
    if segunda_aba is not None:
        worksheet = workbook.create_sheet("Segunda aba")
        worksheet.append(segunda_aba[0])
        for linha in segunda_aba[1]:
            worksheet.append(linha)
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


def arquivo_planilha(nome="organograma.xlsx", conteudo=None):
    conteudo = conteudo if conteudo is not None else conteudo_organograma()
    return SimpleUploadedFile(
        nome,
        conteudo,
        content_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
    )


@pytest.mark.django_db(transaction=True)
class TestAutenticacao:
    @pytest.mark.parametrize(
        "url",
        [
            PATRIARCAS_URL,
            IMPORTACOES_URL,
            CARGAS_URL,
            HISTORICO_URL,
            f"{BASE_URL}/status-carga/",
            f"{BASE_URL}/status-progresso/",
            f"{BASE_URL}/tipos-carga/",
        ],
    )
    def test_listas_exigem_autenticacao(self, client_anonimo_carga, url):
        response = client_anonimo_carga.get(url)
        assert response.status_code == 401


@pytest.mark.django_db(transaction=True)
class TestPermissoesDeclaradas:
    @pytest.mark.parametrize(
        ("viewset", "model_name"),
        [
            (PatriarcaViewSet, "patriarca"),
            (StatusCargaViewSet, "statuscarga"),
            (StatusProgressoViewSet, "statusprogresso"),
            (TipoCargaViewSet, "tipocarga"),
            (CargaOrgLotViewSet, "tokenenviocarga"),
            (HistoricoCargaViewSet, "detalhestatuscarga"),
            (ItemOrganogramaViewSet, "itemorganograma"),
        ],
    )
    def test_crud_possui_mapa_completo(self, viewset, model_name):
        expected = {
            "list": f"view_{model_name}",
            "retrieve": f"view_{model_name}",
            "create": f"add_{model_name}",
            "update": f"change_{model_name}",
            "partial_update": f"change_{model_name}",
            "destroy": f"delete_{model_name}",
        }
        if viewset is PatriarcaViewSet:
            expected["download_organograma"] = "view_importacaoplanilha"
        assert viewset.permission_map == expected

    def test_importacao_inclui_upload_e_download(self):
        assert ImportacaoPlanilhaViewSet.permission_map["upload"] == (
            "add_importacaoplanilha"
        )
        assert ImportacaoPlanilhaViewSet.permission_map["download"] == (
            "view_importacaoplanilha"
        )


@pytest.mark.django_db(transaction=True)
class TestPatriarca:
    def test_crud_completo(
        self,
        client_gestor_carga_lot,
        gestor_carga_lot,
        status_novo,
        status_processando,
    ):
        external_id = uuid4()
        create_response = client_gestor_carga_lot.post(
            PATRIARCAS_URL,
            {
                "idexternopatriarca": str(external_id),
                "strsiglapatriarca": "  pmc  ",
                "strnome": "  Prefeitura Municipal de Cariacica  ",
            },
            format="json",
        )

        assert create_response.status_code == 201
        pk = create_response.data["idpatriarca"]
        assert create_response.data["strsiglapatriarca"] == "PMC"
        assert create_response.data["idstatusprogresso_id"] == status_novo.pk
        assert create_response.data["created_by_id"] == gestor_carga_lot.pk

        list_response = client_gestor_carga_lot.get(PATRIARCAS_URL)
        assert list_response.status_code == 200
        assert list_response.data["count"] == 1

        retrieve_response = client_gestor_carga_lot.get(f"{PATRIARCAS_URL}{pk}/")
        assert retrieve_response.status_code == 200

        patch_response = client_gestor_carga_lot.patch(
            f"{PATRIARCAS_URL}{pk}/",
            {"idstatusprogresso_id": status_processando.pk},
            format="json",
        )
        assert patch_response.status_code == 200
        assert patch_response.data["status"]["strdescricao"] == "Em progresso"
        assert patch_response.data["datalteracao"] is not None

        delete_response = client_gestor_carga_lot.delete(f"{PATRIARCAS_URL}{pk}/")
        assert delete_response.status_code == 204
        assert not Patriarca.objects.filter(pk=pk).exists()

    def test_rejeita_sigla_duplicada_sem_diferenciar_caixa(
        self, client_gestor_carga_lot, status_novo, patriarca
    ):
        response = client_gestor_carga_lot.post(
            PATRIARCAS_URL,
            {
                "idexternopatriarca": str(uuid4()),
                "strsiglapatriarca": "pmvv",
                "strnome": "Outra instituição",
            },
            format="json",
        )
        assert response.status_code == 400
        assert "strsiglapatriarca" in response.data["errors"]


@pytest.mark.django_db(transaction=True)
class TestCatalogos:
    @pytest.mark.parametrize(
        ("url", "id_field", "description_field", "payload"),
        [
            (
                f"{BASE_URL}/status-progresso/",
                "idstatusprogresso",
                "strdescricao",
                {"idstatusprogresso": 9, "strdescricao": "Recebido"},
            ),
            (
                f"{BASE_URL}/tipos-carga/",
                "idtipocarga",
                "strdescricao",
                {"idtipocarga": 9, "strdescricao": "Teste"},
            ),
            (
                f"{BASE_URL}/status-carga/",
                "idstatuscarga",
                "strdescricao",
                {
                    "idstatuscarga": 20,
                    "strdescricao": "Recebida",
                    "flgsucesso": 0,
                },
            ),
        ],
    )
    def test_crud_completo(
        self,
        client_gestor_carga_lot,
        url,
        id_field,
        description_field,
        payload,
    ):
        create_response = client_gestor_carga_lot.post(url, payload, format="json")
        assert create_response.status_code == 201
        pk = create_response.data[id_field]

        assert client_gestor_carga_lot.get(url).status_code == 200
        assert client_gestor_carga_lot.get(f"{url}{pk}/").status_code == 200

        patch_response = client_gestor_carga_lot.patch(
            f"{url}{pk}/",
            {description_field: "Atualizado"},
            format="json",
        )
        assert patch_response.status_code == 200
        assert patch_response.data[description_field] == "Atualizado"

        delete_response = client_gestor_carga_lot.delete(f"{url}{pk}/")
        assert delete_response.status_code == 204


@pytest.mark.django_db(transaction=True)
class TestImportacaoPlanilha:
    def test_upload_lista_detalha_e_download(
        self,
        client_gestor_carga_lot,
        gestor_carga_lot,
        patriarca,
        tipo_organograma,
    ):
        conteudo = conteudo_organograma()
        upload_response = client_gestor_carga_lot.post(
            f"{IMPORTACOES_URL}upload/",
            {
                "idpatriarca_id": patriarca.pk,
                "idtipocarga_id": tipo_organograma.pk,
                "arquivo": arquivo_planilha(conteudo=conteudo),
            },
            format="multipart",
        )

        assert upload_response.status_code == 201
        pk = upload_response.data["idimportacaoplanilha"]
        assert upload_response.data["strnomearquivo"] == "organograma.xlsx"
        assert upload_response.data["inttamanhoarquivo"] == len(conteudo)
        assert upload_response.data["strhasharquivo"] == hashlib.sha256(
            conteudo
        ).hexdigest()
        assert upload_response.data["status"]["strdescricao"] == "Novo"
        assert upload_response.data["created_by_id"] == gestor_carga_lot.pk
        assert "binconteudo" not in upload_response.data

        importacao = ImportacaoPlanilha.objects.get(pk=pk)
        assert bytes(importacao.binconteudo) == conteudo

        list_response = client_gestor_carga_lot.get(IMPORTACOES_URL)
        assert list_response.status_code == 200
        assert list_response.data["count"] == 1
        assert "binconteudo" not in list_response.data["results"][0]

        filtered_response = client_gestor_carga_lot.get(
            IMPORTACOES_URL,
            {"patriarca": patriarca.pk, "tipo_carga": tipo_organograma.pk},
        )
        assert filtered_response.status_code == 200
        assert filtered_response.data["count"] == 1

        empty_response = client_gestor_carga_lot.get(
            IMPORTACOES_URL,
            {"patriarca": patriarca.pk + 1},
        )
        assert empty_response.status_code == 200
        assert empty_response.data["count"] == 0

        detail_response = client_gestor_carga_lot.get(f"{IMPORTACOES_URL}{pk}/")
        assert detail_response.status_code == 200
        assert detail_response.data["patriarca"]["idpatriarca"] == patriarca.pk

        download_response = client_gestor_carga_lot.get(
            f"{IMPORTACOES_URL}{pk}/download/"
        )
        assert download_response.status_code == 200
        assert download_response.content == conteudo
        assert download_response["Content-Length"] == str(len(conteudo))
        assert "organograma.xlsx" in download_response["Content-Disposition"]
        assert download_response["X-Content-Type-Options"] == "nosniff"

    def test_rejeita_filtro_nao_numerico(self, client_gestor_carga_lot):
        response = client_gestor_carga_lot.get(
            IMPORTACOES_URL,
            {"patriarca": "qualquer"},
        )
        assert response.status_code == 400
        assert "patriarca" in response.data["errors"]

    def test_post_padrao_tambem_realiza_upload(
        self,
        client_gestor_carga_lot,
        patriarca,
        tipo_organograma,
    ):
        response = client_gestor_carga_lot.post(
            IMPORTACOES_URL,
            {
                "idpatriarca_id": patriarca.pk,
                "idtipocarga_id": tipo_organograma.pk,
                "arquivo": arquivo_planilha(),
            },
            format="multipart",
        )
        assert response.status_code == 201

    def test_rejeita_extensao_invalida(
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
                "arquivo": arquivo_planilha(nome="dados.exe"),
            },
            format="multipart",
        )
        assert response.status_code == 400
        assert "arquivo" in response.data["errors"]

    def test_rejeita_arquivo_acima_do_limite(
        self,
        client_gestor_carga_lot,
        patriarca,
        tipo_organograma,
        settings,
    ):
        settings.CARGA_ORG_LOT_MAX_UPLOAD_BYTES = 4
        response = client_gestor_carga_lot.post(
            f"{IMPORTACOES_URL}upload/",
            {
                "idpatriarca_id": patriarca.pk,
                "idtipocarga_id": tipo_organograma.pk,
                "arquivo": arquivo_planilha(conteudo=b"12345"),
            },
            format="multipart",
        )
        assert response.status_code == 400
        assert "arquivo" in response.data["errors"]

    @pytest.mark.parametrize(
        ("cabecalho", "linhas"),
        [
            (
                ("Numero", "Nome", "Sigla", "Pai_Sigla"),
                [
                    (1, "Prefeitura", "PMVV", ""),
                    (2, "Secretaria", "SEC", "PMVV"),
                    (3, "Gerência", "GER", "SEC"),
                ],
            ),
            (
                ("Nome", "Sigla", "Pai_Sigla"),
                [
                    ("Prefeitura", "PMVV", ""),
                    ("Secretaria", "SEC", "PMVV"),
                    ("Gerência", "GER", "SEC"),
                ],
            ),
            (
                (
                    "pode ser isso",
                    "ESTRUTURA ORGANIZACIONAL DO MUNICÍPIO",
                    "SIGLAS ATUAIS",
                ),
                [
                    ("", "Prefeitura", "PMVV"),
                    (1, "Secretaria", "SEC"),
                    ("1.1", "Gerência", "GER"),
                ],
            ),
        ],
    )
    def test_aceita_formatos_flexiveis_de_hierarquia(
        self,
        client_gestor_carga_lot,
        patriarca,
        tipo_organograma,
        cabecalho,
        linhas,
    ):
        response = client_gestor_carga_lot.post(
            f"{IMPORTACOES_URL}upload/",
            {
                "idpatriarca_id": patriarca.pk,
                "idtipocarga_id": tipo_organograma.pk,
                "arquivo": arquivo_planilha(
                    conteudo=conteudo_organograma(linhas, cabecalho)
                ),
            },
            format="multipart",
        )

        assert response.status_code == 201
        assert ImportacaoPlanilha.objects.count() == 1

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
            "nome_duplicado",
            "sigla_duplicada",
            "sigla_com_espaco",
            "numero_pai_inexistente",
        }
        assert not ImportacaoPlanilha.objects.exists()

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

    def test_lotacao_exige_organograma_do_mesmo_patriarca(
        self,
        client_gestor_carga_lot,
        patriarca,
        tipo_organograma,
        tipo_lotacao,
    ):
        organograma = ImportacaoPlanilha.objects.create(
            idpatriarca=patriarca,
            idtipocarga=tipo_organograma,
            idstatusprogresso=patriarca.idstatusprogresso,
            strnomearquivo="organograma.xlsx",
            strtipomime="application/octet-stream",
            inttamanhoarquivo=3,
            strhasharquivo=hashlib.sha256(b"abc").hexdigest(),
            binconteudo=b"abc",
        )
        sem_referencia = client_gestor_carga_lot.post(
            f"{IMPORTACOES_URL}upload/",
            {
                "idpatriarca_id": patriarca.pk,
                "idtipocarga_id": tipo_lotacao.pk,
                "arquivo": arquivo_planilha(nome="lotacao.xlsx"),
            },
            format="multipart",
        )
        assert sem_referencia.status_code == 400

        response = client_gestor_carga_lot.post(
            f"{IMPORTACOES_URL}upload/",
            {
                "idpatriarca_id": patriarca.pk,
                "idtipocarga_id": tipo_lotacao.pk,
                "idimportacaoorganograma_id": organograma.pk,
                "arquivo": arquivo_planilha(nome="lotacao.xlsx"),
            },
            format="multipart",
        )
        assert response.status_code == 201
        assert response.data["idimportacaoorganograma_id"] == organograma.pk

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
        assert not ImportacaoPlanilha.objects.exists()

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
                "strreferenciapai": root.strsigla,
                "strabaorigem": "Organograma",
                "intlinhaorigem": 4,
            },
            format="json",
        )
        assert create_response.status_code == 201
        pk = create_response.data["iditemorganograma"]
        assert create_response.data["strsigla"] == "GEP"

        list_response = client_gestor_carga_lot.get(
            ITENS_ORGANOGRAMA_URL,
            {"importacao": importacao_id},
        )
        assert list_response.status_code == 200
        assert list_response.data["count"] == 3
        assert client_gestor_carga_lot.get(
            f"{ITENS_ORGANOGRAMA_URL}{pk}/"
        ).status_code == 200

        patch_response = client_gestor_carga_lot.patch(
            f"{ITENS_ORGANOGRAMA_URL}{pk}/",
            {"strnome": "Gerência de Gestão de Pessoas"},
            format="json",
        )
        assert patch_response.status_code == 200
        assert patch_response.data["strnome"] == "Gerência de Gestão de Pessoas"

        delete_response = client_gestor_carga_lot.delete(
            f"{ITENS_ORGANOGRAMA_URL}{pk}/"
        )
        assert delete_response.status_code == 204
        assert ImportacaoPlanilha.objects.filter(pk=importacao_id).exists()

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
        response = client_gestor_carga_lot.delete(
            f"{PATRIARCAS_URL}{patriarca.pk}/"
        )
        assert response.status_code == 400
        assert Patriarca.objects.filter(pk=patriarca.pk).exists()


@pytest.mark.django_db(transaction=True)
class TestCargaEHistorico:
    def test_crud_carga_sem_expor_token(
        self,
        client_gestor_carga_lot,
        tipo_organograma,
        status_processando,
    ):
        create_response = client_gestor_carga_lot.post(
            CARGAS_URL,
            {
                "strtoken": "segredo",
                "idtipocarga_id": tipo_organograma.pk,
                "idstatusprogresso_id": status_processando.pk,
            },
            format="json",
        )
        assert create_response.status_code == 201
        pk = create_response.data["idtokenenviocarga"]
        assert create_response.data["possui_token"] is True
        assert "strtoken" not in create_response.data

        assert client_gestor_carga_lot.get(CARGAS_URL).status_code == 200
        assert client_gestor_carga_lot.get(f"{CARGAS_URL}{pk}/").status_code == 200
        assert client_gestor_carga_lot.patch(
            f"{CARGAS_URL}{pk}/",
            {"idstatusprogresso_id": status_processando.pk},
            format="json",
        ).status_code == 200
        assert client_gestor_carga_lot.delete(f"{CARGAS_URL}{pk}/").status_code == 204

    def test_crud_historico(
        self,
        client_gestor_carga_lot,
        carga,
        status_carga_recebida,
    ):
        create_response = client_gestor_carga_lot.post(
            HISTORICO_URL,
            {
                "idtokenenviocarga_id": carga.pk,
                "idstatuscarga_id": status_carga_recebida.pk,
                "strmensagem": "Arquivo recebido.",
            },
            format="json",
        )
        assert create_response.status_code == 201
        pk = create_response.data["iddetalhestatuscarga"]

        assert client_gestor_carga_lot.get(HISTORICO_URL).status_code == 200
        assert client_gestor_carga_lot.get(f"{HISTORICO_URL}{pk}/").status_code == 200
        patch_response = client_gestor_carga_lot.patch(
            f"{HISTORICO_URL}{pk}/",
            {"strmensagem": "Atualizado."},
            format="json",
        )
        assert patch_response.status_code == 200
        assert patch_response.data["strmensagem"] == "Atualizado."
        assert client_gestor_carga_lot.delete(
            f"{HISTORICO_URL}{pk}/"
        ).status_code == 204


@pytest.mark.django_db(transaction=True)
class TestAutorizacao:
    def test_portal_admin_pode_listar(self, client_portal_admin):
        assert client_portal_admin.get(PATRIARCAS_URL).status_code == 200

    def test_sem_role_e_negado(self, client_sem_role_carga):
        response = client_sem_role_carga.get(PATRIARCAS_URL)
        assert response.status_code in (401, 403)
