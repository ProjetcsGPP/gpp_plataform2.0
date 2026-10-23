"""Testes de views: prodest."""

import pytest
from django.conf import settings

from apps.carga_org_lot.models import (EnvioOrganogramaProdest,
                                       EventoIntegracaoProdest,
                                       FaseProcessoCargaInicial,
                                       ItemOrganograma, ProcessoCargaInicial,
                                       StatusEnvioOrganograma,
                                       StatusLotacaoProcesso,
                                       StatusOrganogramaProcesso)
from apps.carga_org_lot.services.cargarh import CargaRHRequestError
from apps.carga_org_lot.tests.view_helpers import (ENVIOS_ORGANOGRAMA_URL,
                                                   EVENTOS_INTEGRACAO_URL,
                                                   IMPORTACOES_URL,
                                                   ITENS_ORGANOGRAMA_URL,
                                                   arquivo_planilha,
                                                   conteudo_organograma)


@pytest.mark.django_db(transaction=True)
class TestEnvioOrganogramaProdest:
    class FakeCargaRHClient:
        submitted_payload: dict = {}
        submitted_dry_run = None

        def __init__(self, **kwargs):
            self.context = kwargs

        def submit_organogram(self, patriarch_id, payload, *, dry_run):
            self.__class__.submitted_payload = payload
            self.__class__.submitted_dry_run = dry_run
            return "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"

        def get_status(self, carga_id):
            return {
                "guid": str(carga_id),
                "dryRun": self.__class__.submitted_dry_run,
                "finalizada": True,
                "mensagemErro": None,
                "etapas": [
                    {
                        "etapa": 3,
                        "status": 3,
                        "tentativas": 1,
                        "mensagemErro": None,
                    }
                ],
            }

        def get_report(self, carga_id):
            return {
                "cargaId": str(carga_id),
                "tipo": "organograma",
                "modo": "Simulacao",
                "parcial": False,
                "totais": {"incluidos": 2},
            }

        def list_initial_imports(self, patriarch_id, *, limit):
            return [
                {
                    "guid": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
                    "patriarcaId": str(patriarch_id),
                    "finalizada": True,
                    "dryRun": True,
                }
            ][:limit]

    def _valid_import(self, client, patriarca, tipo_organograma):
        response = client.post(
            f"{IMPORTACOES_URL}upload/",
            {
                "idpatriarca_id": patriarca.pk,
                "idtipocarga_id": tipo_organograma.pk,
                "arquivo": arquivo_planilha(
                    conteudo=conteudo_organograma(
                        linhas=[
                            (1, "Prefeitura", "PMVV"),
                            ("1.1", "Secretaria de Administração", "SEMAD"),
                            ("1.1.1", "Secretaria de Administração", "SEMAD"),
                            ("1.1.1.1", "Gerência de Pessoas", "GEP"),
                        ]
                    )
                ),
            },
            format="multipart",
        )
        assert response.status_code == 201
        return response.data["idimportacaoplanilha"]

    def test_simula_acompanha_e_obtem_relatorio(
        self,
        client_gestor_carga_lot,
        patriarca,
        tipo_organograma,
        monkeypatch,
    ):
        monkeypatch.setattr(
            "apps.carga_org_lot.services.organogram_submission.CargaRHClient",
            self.FakeCargaRHClient,
        )
        importacao_id = self._valid_import(
            client_gestor_carga_lot,
            patriarca,
            tipo_organograma,
        )

        response = client_gestor_carga_lot.post(
            ENVIOS_ORGANOGRAMA_URL,
            {
                "idimportacaoplanilha_id": importacao_id,
                "dry_run": True,
            },
            format="json",
        )

        assert response.status_code == 202
        envio_id = response.data["idenvioorganograma"]
        assert response.data["modo"] == "SIMULACAO"
        assert response.data["strstatus"] == StatusEnvioOrganograma.SOLICITANDO
        assert "strtoken" not in response.data
        payload = self.FakeCargaRHClient.submitted_payload
        assert isinstance(payload, dict)
        assert payload["patriarcaId"] == str(patriarca.idexternopatriarca)
        assert payload["orgaos"] == [
            {
                "nome": "SECRETARIA DE ADMINISTRAÇÃO",
                "sigla": "SEMAD",
                "unidades": [
                    {
                        "nome": "SECRETARIA DE ADMINISTRAÇÃO",
                        "sigla": "SEMAD",
                        "unidadePai": None,
                    },
                    {
                        "nome": "GERÊNCIA DE PESSOAS",
                        "sigla": "GEP",
                        "unidadePai": "SEMAD",
                    },
                ],
            }
        ]
        process = ProcessoCargaInicial.objects.get(idpatriarca=patriarca)
        assert process.strfaseatual == FaseProcessoCargaInicial.SIMULANDO
        assert (
            process.strstatusorganograma
            == StatusOrganogramaProcesso.PROCESSANDO_NA_PRODEST
        )

        status_response = client_gestor_carga_lot.post(
            f"{ENVIOS_ORGANOGRAMA_URL}{envio_id}/consultar-status/"
        )
        assert status_response.status_code == 200
        assert status_response.data["strstatus"] == StatusEnvioOrganograma.CONCLUIDO
        assert status_response.data["finalizada_prodest"] is True
        assert status_response.data["relatorio_disponivel"] is True
        assert status_response.data["etapas_prodest"][0]["etapa_nome"] == (
            "Organograma"
        )
        assert status_response.data["etapas_prodest"][0]["status_nome"] == (
            "Finalizada"
        )
        process.refresh_from_db()
        assert process.strfaseatual == FaseProcessoCargaInicial.PRONTO_PARA_ENVIO
        assert process.strstatusorganograma == StatusOrganogramaProcesso.PRONTO

        report_response = client_gestor_carga_lot.post(
            f"{ENVIOS_ORGANOGRAMA_URL}{envio_id}/consultar-relatorio/"
        )
        assert report_response.status_code == 200
        assert report_response.data["jsonrelatorioprodest"]["parcial"] is False

    def test_envio_definitivo_concluido_libera_preparacao_das_lotacoes(
        self,
        client_gestor_carga_lot,
        patriarca,
        tipo_organograma,
        monkeypatch,
    ):
        monkeypatch.setattr(
            "apps.carga_org_lot.services.organogram_submission.CargaRHClient",
            self.FakeCargaRHClient,
        )
        importacao_id = self._valid_import(
            client_gestor_carga_lot,
            patriarca,
            tipo_organograma,
        )
        created = client_gestor_carga_lot.post(
            ENVIOS_ORGANOGRAMA_URL,
            {
                "idimportacaoplanilha_id": importacao_id,
                "dry_run": False,
            },
            format="json",
        )
        assert created.status_code == 202

        completed = client_gestor_carga_lot.post(
            f"{ENVIOS_ORGANOGRAMA_URL}"
            f"{created.data['idenvioorganograma']}/consultar-status/"
        )

        assert completed.status_code == 200
        process = ProcessoCargaInicial.objects.get(idpatriarca=patriarca)
        assert process.strfaseatual == FaseProcessoCargaInicial.PREPARANDO_LOTACOES
        assert process.strstatusorganograma == StatusOrganogramaProcesso.CONCLUIDO
        assert process.strstatuslotacao == StatusLotacaoProcesso.NAO_INICIADA

    def test_rejeita_segunda_carga_inicial_ativa_do_mesmo_patriarca(
        self,
        client_gestor_carga_lot,
        patriarca,
        tipo_organograma,
        monkeypatch,
    ):
        monkeypatch.setattr(
            "apps.carga_org_lot.services.organogram_submission.CargaRHClient",
            self.FakeCargaRHClient,
        )
        importacao_id = self._valid_import(
            client_gestor_carga_lot,
            patriarca,
            tipo_organograma,
        )
        payload = {
            "idimportacaoplanilha_id": importacao_id,
            "dry_run": True,
        }
        first = client_gestor_carga_lot.post(
            ENVIOS_ORGANOGRAMA_URL,
            payload,
            format="json",
        )
        payload["dry_run"] = False
        second = client_gestor_carga_lot.post(
            ENVIOS_ORGANOGRAMA_URL,
            payload,
            format="json",
        )

        assert first.status_code == 202
        assert second.status_code == 400
        assert EnvioOrganogramaProdest.objects.count() == 1

    def test_consulta_ultimas_cargas_iniciais_na_prodest_e_concilia_local(
        self,
        client_gestor_carga_lot,
        patriarca,
        tipo_organograma,
        monkeypatch,
    ):
        monkeypatch.setattr(
            "apps.carga_org_lot.services.organogram_submission.CargaRHClient",
            self.FakeCargaRHClient,
        )
        importacao_id = self._valid_import(
            client_gestor_carga_lot,
            patriarca,
            tipo_organograma,
        )
        created = client_gestor_carga_lot.post(
            ENVIOS_ORGANOGRAMA_URL,
            {"idimportacaoplanilha_id": importacao_id, "dry_run": True},
            format="json",
        )
        monkeypatch.setattr(
            "apps.carga_org_lot.views.organograma.CargaRHClient",
            self.FakeCargaRHClient,
        )

        response = client_gestor_carga_lot.get(
            f"{ENVIOS_ORGANOGRAMA_URL}ultimas-prodest/",
            {"patriarca": patriarca.pk, "limit": 10},
        )

        assert response.status_code == 200
        assert response.data["patriarca_id"] == patriarca.pk
        assert len(response.data["cargas"]) == 1
        assert response.data["cargas"][0]["idenvioorganograma_local"] == (
            created.data["idenvioorganograma"]
        )

    def test_consulta_ultimas_cargas_rejeita_limite_acima_de_dez(
        self,
        client_gestor_carga_lot,
        patriarca,
    ):
        response = client_gestor_carga_lot.get(
            f"{ENVIOS_ORGANOGRAMA_URL}ultimas-prodest/",
            {"patriarca": patriarca.pk, "limit": 11},
        )

        assert response.status_code == 400

    def test_falha_de_comunicacao_fica_registrada_sem_token(
        self,
        client_gestor_carga_lot,
        patriarca,
        tipo_organograma,
        monkeypatch,
    ):
        class FailingClient:
            def __init__(self, **kwargs):
                self.context = kwargs

            def submit_organogram(self, patriarch_id, payload, *, dry_run):
                raise CargaRHRequestError(
                    "Não foi possível estabelecer comunicação com a PRODEST."
                )

        monkeypatch.setattr(
            "apps.carga_org_lot.services.organogram_submission.CargaRHClient",
            FailingClient,
        )
        importacao_id = self._valid_import(
            client_gestor_carga_lot,
            patriarca,
            tipo_organograma,
        )

        response = client_gestor_carga_lot.post(
            ENVIOS_ORGANOGRAMA_URL,
            {
                "idimportacaoplanilha_id": importacao_id,
                "dry_run": True,
            },
            format="json",
        )

        assert response.status_code == 202
        envio = EnvioOrganogramaProdest.objects.get()
        assert response.data["idenvioorganograma"] == envio.pk
        assert envio.strstatus == StatusEnvioOrganograma.ERRO
        assert envio.idexternocarga is None
        assert envio.jsonstatusprodest == {
            "falha_solicitacao": {
                "http_status": None,
                "problem": {},
            }
        }
        assert "token" not in str(response.data).lower()
        process = ProcessoCargaInicial.objects.get(idpatriarca=patriarca)
        assert process.strstatusorganograma == StatusOrganogramaProcesso.ERRO

    def test_status_de_erro_da_prodest_atualiza_processo(
        self,
        client_gestor_carga_lot,
        patriarca,
        tipo_organograma,
        monkeypatch,
    ):
        class ErrorStatusClient(self.FakeCargaRHClient):
            def get_status(self, carga_id):
                return {
                    "guid": str(carga_id),
                    "dryRun": True,
                    "finalizada": True,
                    "mensagemErro": None,
                    "etapas": [
                        {
                            "etapa": 3,
                            "status": 4,
                            "tentativas": 1,
                            "mensagemErro": "Sigla rejeitada pela PRODEST.",
                        }
                    ],
                }

        monkeypatch.setattr(
            "apps.carga_org_lot.services.organogram_submission.CargaRHClient",
            ErrorStatusClient,
        )
        importacao_id = self._valid_import(
            client_gestor_carga_lot,
            patriarca,
            tipo_organograma,
        )
        created = client_gestor_carga_lot.post(
            ENVIOS_ORGANOGRAMA_URL,
            {
                "idimportacaoplanilha_id": importacao_id,
                "dry_run": True,
            },
            format="json",
        )

        response = client_gestor_carga_lot.post(
            f"{ENVIOS_ORGANOGRAMA_URL}"
            f"{created.data['idenvioorganograma']}/consultar-status/"
        )

        assert response.status_code == 200
        assert response.data["strstatus"] == StatusEnvioOrganograma.ERRO
        assert "Sigla rejeitada" in response.data["strmensagemerro"]
        process = ProcessoCargaInicial.objects.get(idpatriarca=patriarca)
        assert process.strstatusorganograma == StatusOrganogramaProcesso.ERRO

    def test_conclusao_nao_valida_organograma_alterado_durante_processamento(
        self,
        client_gestor_carga_lot,
        patriarca,
        tipo_organograma,
        monkeypatch,
    ):
        monkeypatch.setattr(
            "apps.carga_org_lot.services.organogram_submission.CargaRHClient",
            self.FakeCargaRHClient,
        )
        importacao_id = self._valid_import(
            client_gestor_carga_lot,
            patriarca,
            tipo_organograma,
        )
        created = client_gestor_carga_lot.post(
            ENVIOS_ORGANOGRAMA_URL,
            {
                "idimportacaoplanilha_id": importacao_id,
                "dry_run": True,
            },
            format="json",
        )
        unit = ItemOrganograma.objects.get(
            idimportacaoplanilha_id=importacao_id,
            strsigla="GEP",
        )
        changed = client_gestor_carga_lot.patch(
            f"{ITENS_ORGANOGRAMA_URL}{unit.pk}/",
            {"strnome": "Gerência de Pessoas Atualizada"},
            format="json",
        )
        assert changed.status_code == 200

        response = client_gestor_carga_lot.post(
            f"{ENVIOS_ORGANOGRAMA_URL}"
            f"{created.data['idenvioorganograma']}/consultar-status/"
        )

        assert response.status_code == 200
        assert (
            response.data["strstatus"] == StatusEnvioOrganograma.CONCLUIDO_DESATUALIZADO
        )
        process = ProcessoCargaInicial.objects.get(idpatriarca=patriarca)
        assert process.strfaseatual == FaseProcessoCargaInicial.PREPARANDO_ORGANOGRAMA
        assert process.strstatusorganograma == StatusOrganogramaProcesso.EM_PREPARACAO

    def test_configuracao_nao_expoe_credenciais(self, client_gestor_carga_lot):
        response = client_gestor_carga_lot.get(f"{ENVIOS_ORGANOGRAMA_URL}configuracao/")

        assert response.status_code == 200
        assert set(response.data) == {
            "configurado",
            "ambiente",
            "ausentes",
            "invalidas",
        }
        serialized = str(response.data).lower()
        assert "client_secret" not in serialized
        assert "access_token" not in serialized

    def test_conexao_autenticada_nao_expoe_token(
        self,
        client_gestor_carga_lot,
        monkeypatch,
    ):
        class AuthenticatedClient:
            def __init__(self, **kwargs):
                self.context = kwargs

            def test_connection(self):
                return True

        monkeypatch.setattr(
            "apps.carga_org_lot.views.organograma.CargaRHClient",
            AuthenticatedClient,
        )

        response = client_gestor_carga_lot.post(
            f"{ENVIOS_ORGANOGRAMA_URL}testar-conexao/"
        )

        assert response.status_code == 200
        assert response.data == {
            "conectado": True,
            "ambiente": settings.CARGARH_ENVIRONMENT,
            "token_armazenado": "cache",
            "token_exposto": False,
        }


@pytest.mark.django_db(transaction=True)
class TestEventoIntegracaoProdest:
    def test_lista_eventos_seguros_e_filtra_por_patriarca(
        self,
        client_gestor_carga_lot,
        gestor_carga_lot,
        patriarca,
    ):
        event = EventoIntegracaoProdest.objects.create(
            idpatriarca=patriarca,
            stroperacao="OBTER_TOKEN",
            strmetodo="POST",
            strendpoint="https://auth.example/connect/token",
            inttentativa=1,
            strresultado="ERRO_HTTP",
            inthttpstatus=401,
            intduracaoms=125,
            strmensagem="O Acesso Cidadão recusou a autenticação.",
            jsondetalhes={"title": "Unauthorized", "status": 401},
            created_by_id=gestor_carga_lot.pk,
            created_by_name=gestor_carga_lot.username,
            updated_by_id=gestor_carga_lot.pk,
            updated_by_name=gestor_carga_lot.username,
        )

        response = client_gestor_carga_lot.get(
            EVENTOS_INTEGRACAO_URL,
            {"patriarca": patriarca.pk},
        )

        assert response.status_code == 200
        assert response.data["count"] == 1
        item = response.data["results"][0]
        assert item["ideventointegracao"] == event.pk
        assert item["operacao_nome"] == "Autenticação no Acesso Cidadão"
        assert item["resultado_nome"] == "Recusada pelo serviço externo"
        assert item["sucesso"] is False
        assert "token" not in str(item["jsondetalhes"]).lower()

    def test_rejeita_filtro_numerico_invalido(
        self,
        client_gestor_carga_lot,
    ):
        response = client_gestor_carga_lot.get(
            EVENTOS_INTEGRACAO_URL,
            {"patriarca": "invalido"},
        )

        assert response.status_code == 400
