"""Testes de views: access."""

from uuid import uuid4

import pytest
from django.urls import Resolver404, resolve

from apps.carga_org_lot.models import (FaseProcessoCargaInicial, Patriarca,
                                       ProcessoCargaInicial,
                                       StatusLotacaoProcesso,
                                       StatusOrganogramaProcesso)
from apps.carga_org_lot.tests.view_helpers import (BASE_URL, CARGAS_URL,
                                                   EVENTOS_INTEGRACAO_URL,
                                                   HISTORICO_URL,
                                                   IMPORTACOES_URL,
                                                   ITENS_LOTACAO_URL,
                                                   PATRIARCAS_URL,
                                                   PROCESSOS_URL)
from apps.carga_org_lot.views import (CargaOrgLotViewSet,
                                      CasoValidacaoImportacaoViewSet,
                                      ConjuntoLotacaoViewSet,
                                      EnvioOrganogramaProdestViewSet,
                                      EventoIntegracaoProdestViewSet,
                                      HistoricoCargaViewSet,
                                      ImportacaoPlanilhaViewSet,
                                      ItemLotacaoImportadoViewSet,
                                      ItemLotacaoViewSet,
                                      ItemOrganogramaViewSet, PatriarcaViewSet,
                                      ProcessoCargaInicialViewSet,
                                      StatusCargaViewSet,
                                      StatusProgressoViewSet, TipoCargaViewSet)


@pytest.mark.parametrize(
    "path",
    [
        "/api/public/carga-org-lot/dashboard/",
        f"{BASE_URL}/dashboard-publico/",
    ],
)
def test_dashboard_publico_descontinuado(path):
    with pytest.raises(Resolver404):
        resolve(path)


@pytest.mark.django_db(transaction=True)
class TestAutenticacao:
    @pytest.mark.parametrize(
        "url",
        [
            PATRIARCAS_URL,
            IMPORTACOES_URL,
            ITENS_LOTACAO_URL,
            PROCESSOS_URL,
            CARGAS_URL,
            HISTORICO_URL,
            EVENTOS_INTEGRACAO_URL,
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
        if viewset is ItemOrganogramaViewSet:
            expected["impacto_exclusao"] = "view_itemorganograma"
        assert viewset.permission_map == expected

    def test_importacao_inclui_upload_e_download(self):
        assert ImportacaoPlanilhaViewSet.permission_map["upload"] == (
            "add_importacaoplanilha"
        )
        assert (
            ImportacaoPlanilhaViewSet.permission_map["criar_organograma_inicial"]
            == "add_importacaoplanilha"
        )
        assert ImportacaoPlanilhaViewSet.permission_map["download"] == (
            "view_importacaoplanilha"
        )
        assert (
            ImportacaoPlanilhaViewSet.permission_map["download_organograma_atualizado"]
            == "view_importacaoplanilha"
        )
        assert ImportacaoPlanilhaViewSet.permission_map["relatorio"] == (
            "view_importacaoplanilha"
        )

    def test_processo_e_somente_leitura(self):
        assert ProcessoCargaInicialViewSet.permission_map == {
            "list": "view_patriarca",
            "retrieve": "view_patriarca",
        }

    def test_itens_lotacao_sao_somente_leitura(self):
        assert ItemLotacaoViewSet.permission_map == {
            "list": "view_importacaoplanilha",
            "retrieve": "view_importacaoplanilha",
        }

    def test_conjunto_lotacao_possui_permissoes_explicitas(self):
        assert ConjuntoLotacaoViewSet.permission_map == {
            "list": "view_importacaoplanilha",
            "retrieve": "view_importacaoplanilha",
            "create": "add_importacaoplanilha",
            "adicionar_importacao": "add_importacaoplanilha",
            "homologar": "change_importacaoplanilha",
            "ativar": "change_importacaoplanilha",
            "cancelar": "change_importacaoplanilha",
            "download_consolidado": "view_importacaoplanilha",
            "historico": "view_importacaoplanilha",
            "resumo": "view_importacaoplanilha",
            "resumo_organograma": "view_importacaoplanilha",
        }

    def test_consultas_operacionais_possuem_permissoes_explicitas(self):
        assert ItemLotacaoImportadoViewSet.permission_map == {
            "list": "view_importacaoplanilha",
            "retrieve": "view_importacaoplanilha",
            "descartados": "view_importacaoplanilha",
        }
        assert CasoValidacaoImportacaoViewSet.permission_map == {
            "list": "view_importacaoplanilha",
            "retrieve": "view_importacaoplanilha",
            "resumo": "view_importacaoplanilha",
            "resolver": "change_importacaoplanilha",
        }

    def test_envio_organograma_possui_permissoes_explicitas(self):
        assert EnvioOrganogramaProdestViewSet.permission_map == {
            "list": "view_importacaoplanilha",
            "retrieve": "view_importacaoplanilha",
            "create": "change_importacaoplanilha",
            "configuracao": "view_importacaoplanilha",
            "ultimas_prodest": "view_importacaoplanilha",
            "testar_conexao": "change_importacaoplanilha",
            "consultar_status": "change_importacaoplanilha",
            "consultar_relatorio": "change_importacaoplanilha",
            "acompanhamento": "view_importacaoplanilha",
            "eventos": "view_importacaoplanilha",
        }

    def test_eventos_integracao_sao_somente_leitura(self):
        assert EventoIntegracaoProdestViewSet.permission_map == {
            "list": "view_importacaoplanilha",
            "retrieve": "view_importacaoplanilha",
        }


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
        process = create_response.data["processo_ativo"]
        assert process["strfaseatual"] == FaseProcessoCargaInicial.NOVO
        assert process["strstatusorganograma"] == StatusOrganogramaProcesso.NAO_INICIADO
        assert process["strstatuslotacao"] == StatusLotacaoProcesso.BLOQUEADA
        assert process["historico"][0]["stracao"] == "PROCESSO_CRIADO"

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
class TestProcessoCargaInicial:
    def test_lista_filtra_e_detalha_processo_ativo(
        self,
        client_gestor_carga_lot,
        patriarca,
    ):
        process = ProcessoCargaInicial.objects.create(idpatriarca=patriarca)

        list_response = client_gestor_carga_lot.get(
            PROCESSOS_URL,
            {"patriarca": patriarca.pk, "ativo": "true"},
        )

        assert list_response.status_code == 200
        assert list_response.data["count"] == 1
        assert list_response.data["results"][0]["idprocessocargainicial"] == process.pk
        detail_response = client_gestor_carga_lot.get(f"{PROCESSOS_URL}{process.pk}/")
        assert detail_response.status_code == 200
        assert detail_response.data["strfaseatual"] == "NOVO"

    def test_rejeita_filtros_invalidos(
        self,
        client_gestor_carga_lot,
    ):
        invalid_patriarch = client_gestor_carga_lot.get(
            PROCESSOS_URL,
            {"patriarca": "abc"},
        )
        invalid_active = client_gestor_carga_lot.get(
            PROCESSOS_URL,
            {"ativo": "sim"},
        )

        assert invalid_patriarch.status_code == 400
        assert "patriarca" in invalid_patriarch.data["errors"]
        assert invalid_active.status_code == 400
        assert "ativo" in invalid_active.data["errors"]


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
