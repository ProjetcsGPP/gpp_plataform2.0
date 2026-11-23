"""Contrato de revogação de uma atividade Celery de Carga."""

import json
import multiprocessing
from contextlib import contextmanager
from datetime import timedelta
from unittest.mock import Mock, patch

import pytest
from django.db import connections
from django.test import RequestFactory, override_settings
from django.utils import timezone

from apps.accounts.views_internas import DecisaoAtividadeIAMInternaView
from apps.accounts.models import UserRole
from apps.accounts.services.decisao_interna import decidir_atividade_carga
from apps.carga_org_lot.models import (
    EnvioOrganogramaProdest,
    EventoIntegracaoProdest,
    FaseIntegracaoProdest,
    StatusEnvioOrganograma,
    StatusEventoOperacional,
)
from apps.carga_org_lot.services.integration_events import record_operational_event
from apps.carga_org_lot.services.cargarh import CargaRHRequestError
from apps.carga_org_lot.services.workflow import AuditActor
from apps.carga_org_lot.services.cliente_iam import (
    IAMIndisponivel,
    PermissaoIAMNegada,
    decidir_atividade_remota,
)
from apps.carga_org_lot.tests.view_helpers import (
    ENVIOS_ORGANOGRAMA_URL,
    IMPORTACOES_URL,
    arquivo_planilha,
    conteudo_organograma,
)

TOKEN = "t" * 40
URL = "https://iam.exemplo.org/interno/iam/v1/decisoes/"


@override_settings(
    IAM_DECISOES_INTERNAS_ATIVAS=True,
    IAM_TOKEN_SERVICO_CARGA=TOKEN,
)
def test_endpoint_atividade_exige_m2m_e_nao_recebe_cookie(monkeypatch):
    consulta = Mock(return_value={"resultado": "NEGADO", "usuario_id": 7})
    monkeypatch.setattr(
        "apps.accounts.views_internas.decidir_atividade_carga", consulta
    )
    requisicao = RequestFactory().post(
        "/interno/iam/v1/decisoes-atividade/",
        data='{"usuario_id":7,"acao":"change_importacaoplanilha"}',
        content_type="application/json",
    )
    view = DecisaoAtividadeIAMInternaView.as_view()
    assert view(requisicao).status_code == 401
    assert not consulta.called
    requisicao = RequestFactory().post(
        "/interno/iam/v1/decisoes-atividade/",
        data='{"usuario_id":7,"acao":"change_importacaoplanilha"}',
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {TOKEN}",
    )
    resposta = view(requisicao)
    assert resposta.status_code == 200
    assert json.loads(resposta.content)["resultado"] == "NEGADO"
    assert resposta["Cache-Control"] == "no-store"
    consulta.assert_called_once_with(
        usuario_id=7, permissao="change_importacaoplanilha"
    )


@override_settings(IAM_URL_CARGA=URL, IAM_TOKEN_SERVICO_CARGA=TOKEN)
def test_cliente_atividade_nao_envia_cookie_e_nega_revogacao(monkeypatch):
    resposta = Mock(status_code=200)
    resposta.json.return_value = {
        "versao": 1,
        "decisao_id": "decisao-1",
        "resultado": "NEGADO",
        "usuario_id": 7,
    }
    postagem = Mock(return_value=resposta)
    monkeypatch.setattr(
        "apps.carga_org_lot.services.cliente_iam.requests.post", postagem
    )
    with pytest.raises(PermissaoIAMNegada):
        decidir_atividade_remota(
            usuario_id=7, permissao="change_importacaoplanilha"
        )
    args, kwargs = postagem.call_args
    assert args[0].endswith("/interno/iam/v1/decisoes-atividade/")
    assert kwargs["json"] == {
        "usuario_id": 7, "acao": "change_importacaoplanilha"
    }
    assert "Cookie" not in kwargs["headers"]


@override_settings(IAM_URL_CARGA=URL, IAM_TOKEN_SERVICO_CARGA=TOKEN)
def test_cliente_atividade_rejeita_identidade_divergente(monkeypatch):
    resposta = Mock(status_code=200)
    resposta.json.return_value = {
        "versao": 1,
        "decisao_id": "decisao-1",
        "resultado": "AUTORIZADO",
        "usuario_id": 8,
        "versao_autorizacao": 2,
    }
    monkeypatch.setattr(
        "apps.carga_org_lot.services.cliente_iam.requests.post",
        Mock(return_value=resposta),
    )
    with pytest.raises(IAMIndisponivel):
        decidir_atividade_remota(
            usuario_id=7, permissao="change_importacaoplanilha"
        )


@pytest.mark.django_db(transaction=True)
def test_iam_revalida_permissao_atual_apos_remover_role(gestor_carga_lot):
    assert decidir_atividade_carga(
        usuario_id=gestor_carga_lot.pk,
        permissao="change_importacaoplanilha",
    )["resultado"] == "AUTORIZADO"
    UserRole.objects.filter(user=gestor_carga_lot).delete()
    assert decidir_atividade_carga(
        usuario_id=gestor_carga_lot.pk,
        permissao="change_importacaoplanilha",
    )["resultado"] == "NEGADO"


def _criar_envio(client, patriarca, tipo_organograma):
    resposta = client.post(
        f"{IMPORTACOES_URL}upload/",
        {
            "idpatriarca_id": patriarca.pk,
            "idtipocarga_id": tipo_organograma.pk,
            "arquivo": arquivo_planilha(conteudo=conteudo_organograma(
                linhas=[
                    (1, "Prefeitura", "PMVV"),
                    ("1.1", "Secretaria", "SEC"),
                ]
            )),
        },
        format="multipart",
    )
    assert resposta.status_code == 201
    resposta = client.post(
        ENVIOS_ORGANOGRAMA_URL,
        {"idimportacaoplanilha_id": resposta.data["idimportacaoplanilha"],
         "dry_run": True},
        format="json",
    )
    assert resposta.status_code == 202
    return resposta.data["idenvioorganograma"]


def _worker_envio_bloqueado(canal, liberacao, envio_id, ponto, resultado):
    """Executa a tarefa em outro processo, com PRODEST simulada e DB próprio."""
    from apps.carga_org_lot import tasks

    connections.close_all()

    class ClienteProdest:
        def __init__(self, **_kwargs):
            pass

        def submit_organogram(self, *_args, **_kwargs):
            if ponto == "prodest":
                canal.send(("CHAMADA_PRODEST", None))
                if not liberacao.wait(timeout=10):
                    raise TimeoutError("Ensaio não liberou a resposta da PRODEST")
            if resultado == "erro":
                raise CargaRHRequestError("Resposta rejeitada", status_code=422)
            return "dddddddd-dddd-4ddd-8ddd-dddddddddddd"

    def decidir(**_kwargs):
        if ponto == "iam":
            canal.send(("IAM_EM_VOO", None))
            if not liberacao.wait(timeout=10):
                raise TimeoutError("Ensaio não liberou a decisão IAM")
        return {}

    try:
        with (
            override_settings(CARGA_IAM_ATIVIDADES_REMOTAS_ATIVAS=True),
            patch.object(tasks, "decidir_atividade_remota", side_effect=decidir),
            patch(
                "apps.carga_org_lot.services.organogram_submission.CargaRHClient",
                ClienteProdest,
            ),
        ):
            canal.send(("RESULTADO", tasks.processar_envio_organograma(envio_id)))
    except Exception as exc:  # reportar falhas do filho sem perder o diagnóstico
        canal.send(("ERRO", f"{type(exc).__name__}: {exc}"))
    finally:
        connections.close_all()
        canal.close()


@contextmanager
def _envio_em_outro_processo(envio_id, *, ponto="prodest", resultado="aceite"):
    """Isola a conexão do worker e não deixa filho bloqueado após o teste."""
    connections.close_all()
    contexto = multiprocessing.get_context("fork")
    pai, filho = contexto.Pipe()
    liberacao = contexto.Event()
    processo = contexto.Process(
        target=_worker_envio_bloqueado,
        args=(filho, liberacao, envio_id, ponto, resultado),
    )
    processo.start()
    filho.close()
    try:
        assert pai.poll(5), "Worker não alcançou o ponto de sincronização"
        esperado = "IAM_EM_VOO" if ponto == "iam" else "CHAMADA_PRODEST"
        assert pai.recv() == (esperado, None)
        yield pai, liberacao
    finally:
        liberacao.set()
        processo.join(timeout=5)
        if processo.is_alive():
            processo.terminate()
            processo.join(timeout=5)
        pai.close()
        assert processo.exitcode == 0


def _resultado_worker(canal):
    assert canal.poll(5), "Worker não devolveu o resultado"
    tipo, valor = canal.recv()
    assert tipo == "RESULTADO", valor
    return valor


@pytest.mark.django_db(transaction=True)
@override_settings(CARGA_IAM_ATIVIDADES_REMOTAS_ATIVAS=True)
def test_revogacao_antes_do_envio_encerra_com_evento(
    client_gestor_carga_lot, patriarca, tipo_organograma, monkeypatch
):
    from apps.carga_org_lot import tasks

    monkeypatch.setattr(tasks.processar_envio_organograma, "delay", Mock())
    envio_id = _criar_envio(client_gestor_carga_lot, patriarca, tipo_organograma)
    monkeypatch.setattr(
        tasks, "decidir_atividade_remota",
        Mock(side_effect=PermissaoIAMNegada("revogado")),
    )
    enviar = Mock()
    monkeypatch.setattr(tasks, "execute_organogram_submission", enviar)
    assert tasks.processar_envio_organograma(envio_id)["motivo"] == "REVOGADO"
    envio = EnvioOrganogramaProdest.objects.get(pk=envio_id)
    assert envio.strstatus == StatusEnvioOrganograma.ERRO
    assert envio.datfinalizacao is not None
    assert envio.idexternocarga is None
    assert "revogada" in envio.strmensagematual
    assert EventoIntegracaoProdest.objects.filter(
        idenvioorganograma_id=envio_id,
        strcodigo="ATIVIDADE_ENCERRADA_REVOGACAO",
    ).exists()
    resposta_api = client_gestor_carga_lot.get(
        f"{ENVIOS_ORGANOGRAMA_URL}{envio_id}/"
    )
    assert resposta_api.status_code == 200
    assert "revogada" in resposta_api.data["strmensagematual"]
    enviar.assert_not_called()


@pytest.mark.django_db(transaction=True)
@override_settings(CARGA_IAM_ATIVIDADES_REMOTAS_ATIVAS=True)
def test_encerramento_enquanto_iam_responde_nao_inicia_envio(
    client_gestor_carga_lot, patriarca, tipo_organograma, monkeypatch
):
    from apps.carga_org_lot import tasks
    from apps.carga_org_lot.services.organogram_submission import (
        encerrar_atividade_por_revogacao,
    )

    monkeypatch.setattr(tasks.processar_envio_organograma, "delay", Mock())
    envio_id = _criar_envio(client_gestor_carga_lot, patriarca, tipo_organograma)

    def decisao_em_voo(**_kwargs):
        assert encerrar_atividade_por_revogacao(envio_id) is True
        return {"resultado": "AUTORIZADO"}

    monkeypatch.setattr(tasks, "decidir_atividade_remota", decisao_em_voo)
    enviar = Mock()
    monkeypatch.setattr(tasks, "execute_organogram_submission", enviar)

    assert tasks.processar_envio_organograma(envio_id) == {
        "ignorado": True,
        "motivo": "estado_alterado_apos_iam",
    }
    envio = EnvioOrganogramaProdest.objects.get(pk=envio_id)
    assert envio.strstatus == StatusEnvioOrganograma.ERRO
    assert EventoIntegracaoProdest.objects.filter(
        idenvioorganograma_id=envio_id,
        strcodigo="ATIVIDADE_ENCERRADA_REVOGACAO",
    ).exists()
    enviar.assert_not_called()


@pytest.mark.skipif(
    "fork" not in multiprocessing.get_all_start_methods(),
    reason="Ensaio entre processos requer fork e PostgreSQL local",
)
@pytest.mark.django_db(transaction=True)
@override_settings(CARGA_IAM_ATIVIDADES_REMOTAS_ATIVAS=True)
def test_dois_workers_nao_enviam_mesma_tentativa_concorrente(
    client_gestor_carga_lot, patriarca, tipo_organograma, monkeypatch
):
    from apps.carga_org_lot import tasks

    monkeypatch.setattr(tasks.processar_envio_organograma, "delay", Mock())
    envio_id = _criar_envio(client_gestor_carga_lot, patriarca, tipo_organograma)
    with _envio_em_outro_processo(envio_id) as (canal, liberacao):
        # O primeiro worker está parado dentro da chamada externa. A segunda
        # execução usa outra conexão PostgreSQL e deve respeitar o prazo salvo.
        resposta_concorrente = tasks.processar_envio_organograma(envio_id)
        assert resposta_concorrente == {
            "ignorado": True,
            "motivo": "ainda_nao_vencido",
        }
        liberacao.set()
        assert _resultado_worker(canal) == {"processado": True}
    envio = EnvioOrganogramaProdest.objects.get(pk=envio_id)
    assert envio.strstatus == StatusEnvioOrganograma.PROCESSANDO
    assert str(envio.idexternocarga) == "dddddddd-dddd-4ddd-8ddd-dddddddddddd"
    assert EventoIntegracaoProdest.objects.filter(
        idenvioorganograma_id=envio_id,
        strcodigo="ENVIO_EXTERNO_INICIADO",
    ).count() == 1


@pytest.mark.skipif(
    "fork" not in multiprocessing.get_all_start_methods(),
    reason="Ensaio entre processos requer fork e PostgreSQL local",
)
@pytest.mark.django_db(transaction=True)
@override_settings(CARGA_IAM_ATIVIDADES_REMOTAS_ATIVAS=True)
def test_reserva_vencida_nao_reenvia_tentativa_externa_em_voo(
    client_gestor_carga_lot, patriarca, tipo_organograma, monkeypatch
):
    from apps.carga_org_lot import tasks

    monkeypatch.setattr(tasks.processar_envio_organograma, "delay", Mock())
    envio_id = _criar_envio(client_gestor_carga_lot, patriarca, tipo_organograma)

    class ClienteProdestDuplicado:
        def __init__(self, **_kwargs):
            pass

        def submit_organogram(self, *_args, **_kwargs):
            raise AssertionError("O segundo worker tentou reenviar à PRODEST")

    with _envio_em_outro_processo(envio_id) as (canal, liberacao):
        EnvioOrganogramaProdest.objects.filter(pk=envio_id).update(
            datproximaconsulta=timezone.now() - timedelta(seconds=1)
        )
        with (
            patch.object(tasks, "decidir_atividade_remota", return_value={}),
            patch(
                "apps.carga_org_lot.services.organogram_submission.CargaRHClient",
                ClienteProdestDuplicado,
            ),
        ):
            resposta_concorrente = tasks.processar_envio_organograma(envio_id)
        assert resposta_concorrente == {
            "ignorado": True,
            "motivo": "tentativa_externa_ja_iniciada",
        }
        liberacao.set()
        assert _resultado_worker(canal) == {"processado": True}

    envio = EnvioOrganogramaProdest.objects.get(pk=envio_id)
    assert envio.strstatus == StatusEnvioOrganograma.PROCESSANDO
    assert EventoIntegracaoProdest.objects.filter(
        idenvioorganograma_id=envio_id,
        strcodigo="ENVIO_EXTERNO_INICIADO",
    ).count() == 1


@pytest.mark.django_db(transaction=True)
@override_settings(CARGA_IAM_ATIVIDADES_REMOTAS_ATIVAS=True)
def test_tentativa_sem_resposta_local_nao_e_reenviada(
    client_gestor_carga_lot, patriarca, tipo_organograma, monkeypatch
):
    from apps.carga_org_lot import tasks

    monkeypatch.setattr(tasks.processar_envio_organograma, "delay", Mock())
    envio_id = _criar_envio(client_gestor_carga_lot, patriarca, tipo_organograma)
    envio = EnvioOrganogramaProdest.objects.get(pk=envio_id)
    record_operational_event(
        envio,
        code="ENVIO_EXTERNO_INICIADO",
        phase=FaseIntegracaoProdest.ENVIO,
        status=StatusEventoOperacional.EM_ANDAMENTO,
        title="Tentativa externa iniciada",
        message="Aceite remoto ainda não confirmado.",
        actor=AuditActor(user_name="Worker anterior"),
    )
    EnvioOrganogramaProdest.objects.filter(pk=envio_id).update(
        datproximaconsulta=timezone.now() - timedelta(seconds=1)
    )

    class ClienteProdestProibido:
        def __init__(self, **_kwargs):
            raise AssertionError("A tentativa anterior não pode ser reenviada")

    with (
        patch.object(tasks, "decidir_atividade_remota", return_value={}),
        patch(
            "apps.carga_org_lot.services.organogram_submission.CargaRHClient",
            ClienteProdestProibido,
        ),
    ):
        assert tasks.processar_envio_organograma(envio_id) == {
            "ignorado": True,
            "motivo": "tentativa_externa_ja_iniciada",
        }

    envio.refresh_from_db()
    assert envio.strstatus == StatusEnvioOrganograma.SOLICITANDO
    assert envio.idexternocarga is None
    assert EventoIntegracaoProdest.objects.filter(
        idenvioorganograma_id=envio_id,
        strcodigo="ENVIO_EXTERNO_INICIADO",
    ).count() == 1
    assert EventoIntegracaoProdest.objects.filter(
        idenvioorganograma_id=envio_id,
        strcodigo="REENVIO_AUTOMATICO_BLOQUEADO",
    ).exists()


@pytest.mark.skipif(
    "fork" not in multiprocessing.get_all_start_methods(),
    reason="Ensaio entre processos requer fork e PostgreSQL local",
)
@pytest.mark.django_db(transaction=True)
@override_settings(CARGA_IAM_ATIVIDADES_REMOTAS_ATIVAS=True)
def test_revogacao_em_outro_processo_preserva_aceite_em_voo(
    client_gestor_carga_lot, patriarca, tipo_organograma, monkeypatch
):
    from apps.carga_org_lot import tasks
    from apps.carga_org_lot.services.organogram_submission import (
        encerrar_atividade_por_revogacao,
    )

    monkeypatch.setattr(tasks.processar_envio_organograma, "delay", Mock())
    envio_id = _criar_envio(client_gestor_carga_lot, patriarca, tipo_organograma)
    with _envio_em_outro_processo(envio_id) as (canal, liberacao):
        assert encerrar_atividade_por_revogacao(envio_id) is True
        fechado = EnvioOrganogramaProdest.objects.get(pk=envio_id)
        assert fechado.strstatus == (
            StatusEnvioOrganograma.SITUACAO_REMOTA_INDETERMINADA
        )
        assert fechado.idexternocarga is None
        liberacao.set()
        assert _resultado_worker(canal) == {
            "processado": False,
            "motivo": "ATIVIDADE_ENCERRADA",
        }
    envio = EnvioOrganogramaProdest.objects.get(pk=envio_id)
    assert envio.strstatus == StatusEnvioOrganograma.SITUACAO_REMOTA_INDETERMINADA
    assert str(envio.idexternocarga) == "dddddddd-dddd-4ddd-8ddd-dddddddddddd"
    assert envio.datproximaconsulta is None
    assert EventoIntegracaoProdest.objects.filter(
        idenvioorganograma_id=envio_id,
        strcodigo="CARGA_REMOTA_CRIADA",
        jsondetalhes__atividade_local_encerrada=True,
    ).exists()
    assert tasks.processar_envio_organograma(envio_id) == {"ignorado": True}


@pytest.mark.skipif(
    "fork" not in multiprocessing.get_all_start_methods(),
    reason="Ensaio entre processos requer fork e PostgreSQL local",
)
@pytest.mark.django_db(transaction=True)
@override_settings(CARGA_IAM_ATIVIDADES_REMOTAS_ATIVAS=True)
def test_revogacao_em_outro_processo_preserva_erro_prodest_em_voo(
    client_gestor_carga_lot, patriarca, tipo_organograma, monkeypatch
):
    from apps.carga_org_lot import tasks
    from apps.carga_org_lot.services.organogram_submission import (
        encerrar_atividade_por_revogacao,
    )

    monkeypatch.setattr(tasks.processar_envio_organograma, "delay", Mock())
    envio_id = _criar_envio(client_gestor_carga_lot, patriarca, tipo_organograma)
    with _envio_em_outro_processo(envio_id, resultado="erro") as (canal, liberacao):
        assert encerrar_atividade_por_revogacao(envio_id) is True
        liberacao.set()
        resposta = _resultado_worker(canal)
        assert "Resposta rejeitada" in resposta["erro"]

    envio = EnvioOrganogramaProdest.objects.get(pk=envio_id)
    assert envio.strstatus == StatusEnvioOrganograma.SITUACAO_REMOTA_INDETERMINADA
    assert envio.idexternocarga is None
    assert envio.jsonstatusprodest["falha_solicitacao"]["http_status"] == 422
    assert envio.datproximaconsulta is None
    assert EventoIntegracaoProdest.objects.filter(
        idenvioorganograma_id=envio_id,
        strcodigo="ENVIO_REJEITADO",
    ).exists()


@pytest.mark.skipif(
    "fork" not in multiprocessing.get_all_start_methods(),
    reason="Ensaio entre processos requer fork e PostgreSQL local",
)
@pytest.mark.django_db(transaction=True)
@override_settings(CARGA_IAM_ATIVIDADES_REMOTAS_ATIVAS=True)
def test_revogacao_em_outro_processo_enquanto_iam_responde_nao_envia(
    client_gestor_carga_lot, patriarca, tipo_organograma, monkeypatch
):
    from apps.carga_org_lot import tasks
    from apps.carga_org_lot.services.organogram_submission import (
        encerrar_atividade_por_revogacao,
    )

    monkeypatch.setattr(tasks.processar_envio_organograma, "delay", Mock())
    envio_id = _criar_envio(client_gestor_carga_lot, patriarca, tipo_organograma)
    with _envio_em_outro_processo(envio_id, ponto="iam") as (canal, liberacao):
        assert encerrar_atividade_por_revogacao(envio_id) is True
        liberacao.set()
        assert _resultado_worker(canal) == {
            "ignorado": True,
            "motivo": "estado_alterado_apos_iam",
        }

    envio = EnvioOrganogramaProdest.objects.get(pk=envio_id)
    assert envio.strstatus == StatusEnvioOrganograma.ERRO
    assert not EventoIntegracaoProdest.objects.filter(
        idenvioorganograma_id=envio_id,
        strcodigo="ENVIO_EXTERNO_INICIADO",
    ).exists()


@pytest.mark.django_db(transaction=True)
@override_settings(CARGA_IAM_ATIVIDADES_REMOTAS_ATIVAS=True)
def test_iam_indisponivel_nao_envia_nem_rotula_revogacao(
    client_gestor_carga_lot, patriarca, tipo_organograma, monkeypatch
):
    from apps.carga_org_lot import tasks

    monkeypatch.setattr(tasks.processar_envio_organograma, "delay", Mock())
    envio_id = _criar_envio(client_gestor_carga_lot, patriarca, tipo_organograma)
    monkeypatch.setattr(
        tasks, "decidir_atividade_remota",
        Mock(side_effect=IAMIndisponivel("indisponivel")),
    )
    enviar = Mock()
    monkeypatch.setattr(tasks, "execute_organogram_submission", enviar)
    assert tasks.processar_envio_organograma(envio_id)["motivo"] == "IAM_INDISPONIVEL"
    envio = EnvioOrganogramaProdest.objects.get(pk=envio_id)
    assert envio.strstatus == StatusEnvioOrganograma.SOLICITANDO
    assert envio.datproximaconsulta is not None
    assert EventoIntegracaoProdest.objects.filter(
        idenvioorganograma_id=envio_id,
        strcodigo="IAM_INDISPONIVEL_ATIVIDADE",
    ).exists()
    enviar.assert_not_called()


@pytest.mark.django_db(transaction=True)
@override_settings(CARGA_IAM_ATIVIDADES_REMOTAS_ATIVAS=True)
def test_revogacao_com_tentativa_iniciada_sem_resposta_nao_afirma_nao_envio(
    client_gestor_carga_lot, patriarca, tipo_organograma, monkeypatch
):
    from apps.carga_org_lot import tasks

    monkeypatch.setattr(tasks.processar_envio_organograma, "delay", Mock())
    envio_id = _criar_envio(client_gestor_carga_lot, patriarca, tipo_organograma)
    envio = EnvioOrganogramaProdest.objects.get(pk=envio_id)
    record_operational_event(
        envio,
        code="ENVIO_EXTERNO_INICIADO",
        phase=FaseIntegracaoProdest.ENVIO,
        status=StatusEventoOperacional.EM_ANDAMENTO,
        title="Tentativa externa iniciada",
        message="Aceite ainda não confirmado.",
        actor=AuditActor(envio.created_by_id, envio.created_by_name),
    )
    monkeypatch.setattr(
        tasks, "decidir_atividade_remota",
        Mock(side_effect=PermissaoIAMNegada("revogado")),
    )
    assert tasks.processar_envio_organograma(envio_id)["motivo"] == "REVOGADO"
    envio.refresh_from_db()
    assert envio.idexternocarga is None
    assert envio.strstatus == StatusEnvioOrganograma.SITUACAO_REMOTA_INDETERMINADA
    assert "não há confirmação local de aceite" in envio.strmensagematual
    assert "não iniciado" not in envio.strmensagematual
    evento = EventoIntegracaoProdest.objects.get(
        idenvioorganograma_id=envio_id,
        strcodigo="ATIVIDADE_ENCERRADA_REVOGACAO",
    )
    assert evento.jsondetalhes["tentativa_externa_iniciada"] is True
    assert evento.jsondetalhes["resposta_prodest_registrada"] is False


@pytest.mark.django_db(transaction=True)
@override_settings(CARGA_IAM_ATIVIDADES_REMOTAS_ATIVAS=True)
def test_revogacao_durante_chamada_preserva_resposta_e_para_monitor(
    client_gestor_carga_lot, patriarca, tipo_organograma, monkeypatch
):
    from apps.carga_org_lot import tasks

    monkeypatch.setattr(tasks.processar_envio_organograma, "delay", Mock())
    envio_id = _criar_envio(client_gestor_carga_lot, patriarca, tipo_organograma)
    chamada = Mock(side_effect=[{}, PermissaoIAMNegada("revogado")])
    monkeypatch.setattr(tasks, "decidir_atividade_remota", chamada)

    class ClienteProdest:
        def __init__(self, **kwargs):
            _ = kwargs

        def submit_organogram(self, *args, **kwargs):
            _ = (args, kwargs)
            return "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"

    monkeypatch.setattr(
        "apps.carga_org_lot.services.organogram_submission.CargaRHClient",
        ClienteProdest,
    )
    assert tasks.processar_envio_organograma(envio_id)["motivo"] == "REVOGADO"
    envio = EnvioOrganogramaProdest.objects.get(pk=envio_id)
    assert str(envio.idexternocarga) == "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    assert envio.strstatus == StatusEnvioOrganograma.SITUACAO_REMOTA_INDETERMINADA
    assert envio.datfinalizacao is not None
    assert envio.datfimmonitoramento is not None
    assert envio.datproximaconsulta is None
    assert EventoIntegracaoProdest.objects.filter(
        idenvioorganograma_id=envio_id, strcodigo="CARGA_REMOTA_CRIADA"
    ).exists()
    assert EventoIntegracaoProdest.objects.filter(
        idenvioorganograma_id=envio_id,
        strcodigo="ATIVIDADE_ENCERRADA_REVOGACAO",
        jsondetalhes__resposta_prodest_registrada=True,
    ).exists()
    assert tasks.processar_envio_organograma(envio_id)["ignorado"] is True


@pytest.mark.django_db(transaction=True)
@override_settings(CARGA_IAM_ATIVIDADES_REMOTAS_ATIVAS=True)
def test_resposta_prodest_apos_encerramento_nao_reabre_atividade(
    client_gestor_carga_lot, patriarca, tipo_organograma, monkeypatch
):
    from apps.carga_org_lot import tasks
    from apps.carga_org_lot.services.organogram_submission import (
        encerrar_atividade_por_revogacao,
    )

    monkeypatch.setattr(tasks.processar_envio_organograma, "delay", Mock())
    envio_id = _criar_envio(client_gestor_carga_lot, patriarca, tipo_organograma)
    monkeypatch.setattr(tasks, "decidir_atividade_remota", Mock(return_value={}))

    class ClienteProdest:
        def __init__(self, **kwargs):
            _ = kwargs

        def submit_organogram(self, *args, **kwargs):
            _ = (args, kwargs)
            assert encerrar_atividade_por_revogacao(envio_id) is True
            return "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"

    monkeypatch.setattr(
        "apps.carga_org_lot.services.organogram_submission.CargaRHClient",
        ClienteProdest,
    )
    assert tasks.processar_envio_organograma(envio_id)["motivo"] == "ATIVIDADE_ENCERRADA"
    envio = EnvioOrganogramaProdest.objects.get(pk=envio_id)
    assert envio.strstatus == StatusEnvioOrganograma.SITUACAO_REMOTA_INDETERMINADA
    assert str(envio.idexternocarga) == "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
    assert envio.datproximaconsulta is None
    assert "revogação" in envio.strmensagematual
    aceite = EventoIntegracaoProdest.objects.get(
        idenvioorganograma_id=envio_id, strcodigo="CARGA_REMOTA_CRIADA"
    )
    assert aceite.jsondetalhes["atividade_local_encerrada"] is True


@pytest.mark.django_db(transaction=True)
@override_settings(CARGA_IAM_ATIVIDADES_REMOTAS_ATIVAS=True)
def test_erro_prodest_apos_revogacao_preserva_resposta_e_encerramento(
    client_gestor_carga_lot, patriarca, tipo_organograma, monkeypatch
):
    from apps.carga_org_lot import tasks
    from apps.carga_org_lot.services.organogram_submission import (
        encerrar_atividade_por_revogacao,
    )

    monkeypatch.setattr(tasks.processar_envio_organograma, "delay", Mock())
    envio_id = _criar_envio(client_gestor_carga_lot, patriarca, tipo_organograma)
    monkeypatch.setattr(tasks, "decidir_atividade_remota", Mock(return_value={}))

    class ClienteProdest:
        def __init__(self, **kwargs):
            _ = kwargs

        def submit_organogram(self, *args, **kwargs):
            _ = (args, kwargs)
            assert encerrar_atividade_por_revogacao(envio_id) is True
            raise CargaRHRequestError("Resposta rejeitada", status_code=422)

    monkeypatch.setattr(
        "apps.carga_org_lot.services.organogram_submission.CargaRHClient",
        ClienteProdest,
    )
    assert "Resposta rejeitada" in tasks.processar_envio_organograma(envio_id)["erro"]
    envio = EnvioOrganogramaProdest.objects.get(pk=envio_id)
    assert envio.strstatus == StatusEnvioOrganograma.SITUACAO_REMOTA_INDETERMINADA
    assert envio.jsonstatusprodest["falha_solicitacao"]["http_status"] == 422
    assert envio.datproximaconsulta is None
    assert "revogação" in envio.strmensagematual
    assert EventoIntegracaoProdest.objects.filter(
        idenvioorganograma_id=envio_id, strcodigo="ENVIO_REJEITADO"
    ).exists()


@pytest.mark.django_db(transaction=True)
def test_consulta_em_voo_guarda_resposta_sem_reabrir_monitoramento(
    client_gestor_carga_lot, patriarca, tipo_organograma, monkeypatch
):
    from apps.carga_org_lot.services.organogram_submission import (
        encerrar_atividade_por_revogacao,
        refresh_submission_status,
    )

    from apps.carga_org_lot import tasks
    monkeypatch.setattr(tasks.processar_envio_organograma, "delay", Mock())
    envio_id = _criar_envio(client_gestor_carga_lot, patriarca, tipo_organograma)
    envio = EnvioOrganogramaProdest.objects.get(pk=envio_id)
    envio.idexternocarga = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
    envio.strstatus = StatusEnvioOrganograma.PROCESSANDO
    envio.save(update_fields=["idexternocarga", "strstatus"])

    class ClienteProdest:
        def get_status(self, carga_id):
            assert str(carga_id) == "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
            assert encerrar_atividade_por_revogacao(envio_id) is True
            return {"finalizada": False, "etapas": [{"status": "EM_ANDAMENTO"}]}

    refresh_submission_status(
        envio,
        actor=AuditActor(envio.created_by_id, envio.created_by_name),
        client=ClienteProdest(),
    )
    envio.refresh_from_db()
    assert envio.strstatus == StatusEnvioOrganograma.SITUACAO_REMOTA_INDETERMINADA
    assert envio.datproximaconsulta is None
    assert envio.jsonstatusprodest["finalizada"] is False
    assert "revogação" in envio.strmensagematual
    assert EventoIntegracaoProdest.objects.filter(
        idenvioorganograma_id=envio_id,
        strcodigo="RESPOSTA_PRODEST_APOS_ENCERRAMENTO",
    ).exists()
