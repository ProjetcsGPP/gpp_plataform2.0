"""Testes de views: prodest."""

import pytest
from django.conf import settings
from django.test import override_settings

from apps.carga_org_lot.models import (EnvioOrganogramaProdest,
                                       EventoIntegracaoProdest,
                                       FaseIntegracaoProdest,
                                       FaseProcessoCargaInicial,
                                       ItemOrganograma,
                                       OperacaoIntegracaoProdest,
                                       ProcessoCargaInicial,
                                       StatusEnvioOrganograma,
                                       StatusLotacaoProcesso,
                                       StatusOrganogramaProcesso)
from apps.carga_org_lot.services.cargarh import CargaRHRequestError
from apps.carga_org_lot.services.submission_workflow import (
    build_submission_workflow, canonical_event_phase)
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
        workflow = status_response.data["fluxo_operacional"]
        assert workflow["fase_atual"] == FaseIntegracaoProdest.CONCLUSAO
        assert workflow["status_atual"] == "SUCESSO"
        assert [stage["codigo"] for stage in workflow["etapas"]] == [
            "PREPARACAO",
            "AUTENTICACAO",
            "ENVIO",
            "PROCESSAMENTO",
            "RELATORIO",
            "CONCLUSAO",
        ]
        assert all(stage["status"] == "SUCESSO" for stage in workflow["etapas"])
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

    def test_403_ao_enviar_organograma_e_classificado_na_fase_de_envio(
        self,
        client_gestor_carga_lot,
        patriarca,
        tipo_organograma,
        monkeypatch,
    ):
        realtime_payloads = []

        class ForbiddenSubmissionClient:
            def __init__(self, **kwargs):
                self.context = kwargs

            def submit_organogram(self, patriarch_id, payload, *, dry_run):
                raise CargaRHRequestError(
                    "A PRODEST recusou a solicitação ao enviar o organograma.",
                    status_code=403,
                    details={
                        "title": "Client sem permissão nesse contexto de carga",
                        "detail": (
                            "O client autenticado não tem permissão para enviar "
                            "cargas no contexto informado."
                        ),
                        "status": 403,
                        "traceId": "trace-safe-403",
                    },
                    operation=(
                        OperacaoIntegracaoProdest.ENVIAR_ORGANOGRAMA_INICIAL
                    ),
                    method="POST",
                    endpoint=(
                        "https://api.cargarh.hom.es.gov.br/v3/"
                        "importacoes-iniciais/patriarcas/patriarch/organograma"
                    ),
                )

        monkeypatch.setattr(
            "apps.carga_org_lot.services.organogram_submission.CargaRHClient",
            ForbiddenSubmissionClient,
        )
        monkeypatch.setattr(
            "apps.carga_org_lot.services.integration_events."
            "publish_submission_update",
            lambda payload, **kwargs: realtime_payloads.append(payload),
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
        assert envio.strfaseatual == FaseIntegracaoProdest.ENVIO
        failure = EventoIntegracaoProdest.objects.get(
            idenvioorganograma=envio,
            strcodigo="ENVIO_REJEITADO",
        )
        assert failure.strfase == FaseIntegracaoProdest.ENVIO
        assert failure.strtitulo == "Não foi possível enviar o organograma"
        assert failure.strmetodo == "POST"
        assert failure.inthttpstatus == 403
        assert failure.jsondetalhes == {
            "ambiente": settings.CARGARH_ENVIRONMENT,
            "etapa": FaseIntegracaoProdest.ENVIO,
            "servico": "API CargaRH",
            "modo": "SIMULACAO",
            "operacao": OperacaoIntegracaoProdest.ENVIAR_ORGANOGRAMA_INICIAL,
            "metodo": "POST",
            "endpoint": (
                "https://api.cargarh.hom.es.gov.br/v3/importacoes-iniciais/"
                "patriarcas/patriarch/organograma"
            ),
            "http_status": 403,
            "titulo_provedor": "Client sem permissão nesse contexto de carga",
            "detalhe_provedor": (
                "O client autenticado não tem permissão para enviar cargas no "
                "contexto informado."
            ),
            "status_provedor": 403,
            "trace_id": "trace-safe-403",
        }
        assert realtime_payloads[-1]["evento"]["detalhes"] == (
            failure.jsondetalhes
        )
        assert realtime_payloads[-1]["evento"]["detalhes_exibicao"] == (
            failure.jsondetalhes
        )
        serialized = str(failure.jsondetalhes).lower()
        assert "authorization" not in serialized
        assert "client-secret" not in serialized
        assert "temporary-token" not in serialized

        # Tentativas antigas podem ter persistido este 403 como autenticação.
        # O contrato novo deriva a exibição da operação realmente recusada.
        failure.strfase = FaseIntegracaoProdest.AUTENTICACAO
        failure.save(update_fields=["strfase"])
        assert canonical_event_phase(failure) == FaseIntegracaoProdest.ENVIO
        workflow = build_submission_workflow(envio)
        assert workflow["fase_atual"] == FaseIntegracaoProdest.ENVIO
        assert workflow["status_atual"] == "ERRO"
        envio_stage = next(
            stage
            for stage in workflow["etapas"]
            if stage["codigo"] == FaseIntegracaoProdest.ENVIO
        )
        assert envio_stage["status"] == "ERRO"

    def test_invalid_scope_e_classificado_na_fase_de_autenticacao(
        self,
        client_gestor_carga_lot,
        patriarca,
        tipo_organograma,
        monkeypatch,
    ):
        class InvalidScopeClient:
            def __init__(self, **kwargs):
                self.context = kwargs

            def submit_organogram(self, patriarch_id, payload, *, dry_run):
                raise CargaRHRequestError(
                    "A PRODEST recusou a solicitação ao autenticar na PRODEST.",
                    status_code=400,
                    details={"error": "invalid_scope"},
                    operation=OperacaoIntegracaoProdest.OBTER_TOKEN,
                    method="POST",
                    endpoint="https://acessocidadao.example/connect/token",
                )

        monkeypatch.setattr(
            "apps.carga_org_lot.services.organogram_submission.CargaRHClient",
            InvalidScopeClient,
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
                "dry_run": False,
            },
            format="json",
        )

        assert response.status_code == 202
        envio = EnvioOrganogramaProdest.objects.get()
        assert envio.strfaseatual == FaseIntegracaoProdest.AUTENTICACAO
        failure = EventoIntegracaoProdest.objects.get(
            idenvioorganograma=envio,
            strcodigo="AUTENTICACAO_REJEITADA",
        )
        assert failure.strtitulo == "Não foi possível autenticar na PRODEST"
        assert failure.inthttpstatus == 400
        assert failure.jsondetalhes["codigo_erro"] == "invalid_scope"
        assert failure.jsondetalhes["escopos_solicitados"] == (
            settings.CARGARH_CLIENT_SCOPE.split()
        )
        assert failure.jsondetalhes["modo"] == "DEFINITIVO"
        workflow = build_submission_workflow(envio)
        assert workflow["fase_atual"] == FaseIntegracaoProdest.AUTENTICACAO
        assert workflow["status_atual"] == "ERRO"

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

    @override_settings(CARGA_ORG_LOT_REMOTE_STALE_WARNING_SECONDS=1)
    def test_avisa_quando_prodest_responde_sem_atualizar_processamento(
        self,
        client_gestor_carga_lot,
        patriarca,
        tipo_organograma,
        monkeypatch,
    ):
        class StaleStatusClient(self.FakeCargaRHClient):
            def get_status(self, carga_id):
                return {
                    "guid": str(carga_id),
                    "finalizada": False,
                    "dataUltimaAtualizacaoUtc": "2020-01-01T00:00:00Z",
                    "etapas": [
                        {
                            "etapa": 3,
                            "status": 1,
                            "dataInicioUtc": None,
                            "dataFimUtc": None,
                            "tentativas": 0,
                            "mensagemErro": None,
                        }
                    ],
                }

        monkeypatch.setattr(
            "apps.carga_org_lot.services.organogram_submission.CargaRHClient",
            StaleStatusClient,
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
        envio_id = created.data["idenvioorganograma"]

        first = client_gestor_carga_lot.post(
            f"{ENVIOS_ORGANOGRAMA_URL}{envio_id}/consultar-status/"
        )
        second = client_gestor_carga_lot.post(
            f"{ENVIOS_ORGANOGRAMA_URL}{envio_id}/consultar-status/"
        )

        assert first.status_code == 200
        assert second.status_code == 200
        assert second.data["strstatus"] == StatusEnvioOrganograma.PROCESSANDO
        workflow = second.data["fluxo_operacional"]
        assert workflow["fase_atual"] == FaseIntegracaoProdest.PROCESSAMENTO
        assert workflow["status_atual"] == "AVISO"
        assert "continua respondendo" in workflow["mensagem_atual"]
        assert EventoIntegracaoProdest.objects.filter(
            idenvioorganograma_id=envio_id,
            strcodigo="PROCESSAMENTO_SEM_ATUALIZACAO",
        ).count() == 1

    @override_settings(
        CARGA_ORG_LOT_REMOTE_STALE_WARNING_SECONDS=1,
        CARGA_ORG_LOT_REMOTE_INDETERMINATE_AFTER_SECONDS=7200,
    )
    def test_encerra_monitoramento_indeterminado_e_libera_nova_tentativa(
        self,
        client_gestor_carga_lot,
        patriarca,
        tipo_organograma,
        monkeypatch,
    ):
        class StaleStatusClient(self.FakeCargaRHClient):
            def get_status(self, carga_id):
                return {
                    "guid": str(carga_id),
                    "finalizada": False,
                    "dataUltimaAtualizacaoUtc": "2020-01-01T00:00:00Z",
                    "etapas": [{"etapa": 3, "status": 1, "tentativas": 0}],
                }

        monkeypatch.setattr(
            "apps.carga_org_lot.services.organogram_submission.CargaRHClient",
            StaleStatusClient,
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
        envio_id = created.data["idenvioorganograma"]
        client_gestor_carga_lot.post(
            f"{ENVIOS_ORGANOGRAMA_URL}{envio_id}/consultar-status/"
        )

        before = client_gestor_carga_lot.get(
            f"{ENVIOS_ORGANOGRAMA_URL}{envio_id}/"
        )
        assert before.data["acoes_disponiveis"]["encerrar_monitoramento"] is True
        assert before.data["encerramento_monitoramento"]["permitido"] is True
        assert before.data["encerramento_monitoramento"][
            "opcoes_disponiveis"
        ] == ["CONTINUAR_AGUARDANDO", "LIBERAR_NOVO_ENVIO"]

        closed = client_gestor_carga_lot.post(
            f"{ENVIOS_ORGANOGRAMA_URL}{envio_id}/encerrar-monitoramento/",
            {
                "justificativa": (
                    "Carga sem atualização; situação alinhada com a PRODEST."
                ),
                "confirmar_risco_processamento_remoto": True,
                "analista_prodest_avisado": True,
                "analista_prodest_respondeu": True,
                "retorno_analista_prodest": (
                    "Orientou encerrar o acompanhamento local e reenviar."
                ),
            },
            format="json",
        )

        assert closed.status_code == 200
        assert closed.data["strstatus"] == (
            StatusEnvioOrganograma.SITUACAO_REMOTA_INDETERMINADA
        )
        assert closed.data["finalizada_prodest"] is False
        assert closed.data["datencerramentomanual"] is not None
        assert closed.data["flganalistaprodestavisado"] is True
        assert closed.data["flganalistaprodestrespondeu"] is True
        assert closed.data["acoes_disponiveis"]["encerrar_monitoramento"] is False
        assert EventoIntegracaoProdest.objects.filter(
            idenvioorganograma_id=envio_id,
            strcodigo="MONITORAMENTO_ENCERRADO_SITUACAO_INDETERMINADA",
        ).exists()
        process = ProcessoCargaInicial.objects.get(idpatriarca=patriarca)
        assert process.strfaseatual == FaseProcessoCargaInicial.PRONTO_PARA_ENVIO
        assert process.strstatusorganograma == StatusOrganogramaProcesso.PRONTO

        next_attempt = client_gestor_carga_lot.post(
            ENVIOS_ORGANOGRAMA_URL,
            {
                "idimportacaoplanilha_id": importacao_id,
                "dry_run": True,
            },
            format="json",
        )
        assert next_attempt.status_code == 202
        assert next_attempt.data["idtentativaanterior_id"] == envio_id

    @override_settings(
        CARGA_ORG_LOT_REMOTE_INDETERMINATE_AFTER_SECONDS=7200,
    )
    def test_nao_libera_encerramento_antes_da_carencia(
        self,
        client_gestor_carga_lot,
        patriarca,
        tipo_organograma,
        monkeypatch,
    ):
        class CurrentStatusClient(self.FakeCargaRHClient):
            def get_status(self, carga_id):
                return {
                    "guid": str(carga_id),
                    "finalizada": False,
                    "etapas": [{"etapa": 3, "status": 2, "tentativas": 1}],
                }

        monkeypatch.setattr(
            "apps.carga_org_lot.services.organogram_submission.CargaRHClient",
            CurrentStatusClient,
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
        envio_id = created.data["idenvioorganograma"]

        response = client_gestor_carga_lot.post(
            f"{ENVIOS_ORGANOGRAMA_URL}{envio_id}/encerrar-monitoramento/",
            {
                "justificativa": "Tentativa de encerramento antes da carência.",
                "confirmar_risco_processamento_remoto": True,
                "analista_prodest_avisado": False,
                "analista_prodest_respondeu": False,
                "retorno_analista_prodest": "",
            },
            format="json",
        )

        assert response.status_code == 409
        assert response.data["errors"]["details"]["permitido"] is False
        assert response.data["errors"]["details"]["opcoes_disponiveis"] == [
            "CONTINUAR_AGUARDANDO"
        ]
        assert response.data["errors"]["details"]["segundos_restantes"] > 0
        envio = EnvioOrganogramaProdest.objects.get(pk=envio_id)
        assert envio.strstatus == StatusEnvioOrganograma.PROCESSANDO

    @override_settings(
        CARGA_ORG_LOT_REMOTE_INDETERMINATE_AFTER_SECONDS=7200,
    )
    def test_ultima_consulta_conclui_carga_em_vez_de_encerrar_monitoramento(
        self,
        client_gestor_carga_lot,
        patriarca,
        tipo_organograma,
        monkeypatch,
    ):
        class FinishesOnLastConsultClient(self.FakeCargaRHClient):
            status_calls = 0

            def get_status(self, carga_id):
                self.__class__.status_calls += 1
                if self.__class__.status_calls == 1:
                    return {
                        "guid": str(carga_id),
                        "finalizada": False,
                        "dataUltimaAtualizacaoUtc": "2020-01-01T00:00:00Z",
                        "etapas": [{"etapa": 3, "status": 1}],
                    }
                return {
                    "guid": str(carga_id),
                    "finalizada": True,
                    "dataUltimaAtualizacaoUtc": "2026-11-03T12:00:00Z",
                    "mensagemErro": None,
                    "etapas": [{"etapa": 3, "status": 3}],
                }

        monkeypatch.setattr(
            "apps.carga_org_lot.services.organogram_submission.CargaRHClient",
            FinishesOnLastConsultClient,
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
        envio_id = created.data["idenvioorganograma"]
        client_gestor_carga_lot.post(
            f"{ENVIOS_ORGANOGRAMA_URL}{envio_id}/consultar-status/"
        )

        response = client_gestor_carga_lot.post(
            f"{ENVIOS_ORGANOGRAMA_URL}{envio_id}/encerrar-monitoramento/",
            {
                "justificativa": "Carga sem atualização antes da consulta final.",
                "confirmar_risco_processamento_remoto": True,
                "analista_prodest_avisado": True,
                "analista_prodest_respondeu": False,
                "retorno_analista_prodest": "",
            },
            format="json",
        )

        assert response.status_code == 200
        assert response.data["strstatus"] == StatusEnvioOrganograma.CONCLUIDO
        assert response.data["finalizada_prodest"] is True
        assert response.data["datencerramentomanual"] is None
        assert not EventoIntegracaoProdest.objects.filter(
            idenvioorganograma_id=envio_id,
            strcodigo="MONITORAMENTO_ENCERRADO_SITUACAO_INDETERMINADA",
        ).exists()

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
    @override_settings(TIME_ZONE="America/Sao_Paulo")
    def test_exibe_data_da_prodest_no_fuso_local_sem_alterar_valor_tecnico(
        self,
        client_gestor_carga_lot,
        gestor_carga_lot,
        patriarca,
    ):
        EventoIntegracaoProdest.objects.create(
            idpatriarca=patriarca,
            stroperacao="CONSULTAR_STATUS",
            strmetodo="GET",
            strendpoint="https://api.example/status",
            strresultado="SUCESSO",
            strmensagem="Processamento remoto sem atualização.",
            jsondetalhes={
                "limite_segundos": 1800,
                "ultima_atualizacao_prodest": (
                    "2026-10-29T13:44:03.0413547"
                ),
            },
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
        item = response.data["results"][0]
        assert item["jsondetalhes"]["ultima_atualizacao_prodest"] == (
            "2026-10-29T13:44:03.0413547"
        )
        assert item["jsondetalhes_exibicao"] == {
            "limite_segundos": 1800,
            "ultima_atualizacao_prodest": "29/10/2026 10:44:03",
        }

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
