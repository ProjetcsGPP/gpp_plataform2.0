"""Modelos da coleta por arquivo do E-Flow."""

import uuid

from django.conf import settings
from django.db import models

from common.models import ModeloAuditavel

from .edocs import PatriarcaEdocs


class SituacaoColetaEflow(models.TextChoices):
    EM_PROCESSAMENTO = "EM_PROCESSAMENTO", "Em processamento"
    CONCLUIDA = "CONCLUIDA", "Concluída"
    FALHOU = "FALHOU", "Falhou"


class PublicoAlvoEflow(models.TextChoices):
    CIDADAO = "Cidadão", "Cidadão"
    ORGAO = "Órgão", "Órgão"
    PATRIARCA = "Patriarca", "Patriarca"
    SETOR = "Setor", "Setor"
    LISTA_PERMISSAO = "Lista de Permissão", "Lista de Permissão"


class PerfilCalculoEflow(models.TextChoices):
    COMPLETO_TECNICO = "COMPLETO_TECNICO", "Completo técnico"
    CONSOLIDADO_PUBLICACAO = (
        "CONSOLIDADO_PUBLICACAO",
        "Consolidado para publicação",
    )


class TipoEventoAuditoriaEflow(models.TextChoices):
    COLETA_INICIADA = "COLETA_INICIADA", "Coleta iniciada"
    COLETA_CONCLUIDA = "COLETA_CONCLUIDA", "Coleta concluída"
    COLETA_FALHOU = "COLETA_FALHOU", "Coleta falhou"
    RESULTADOS_CALCULADOS = "RESULTADOS_CALCULADOS", "Resultados calculados"


class TipoEventoAuditoriaPreferenciaEflow(models.TextChoices):
    PREFERENCIA_INICIALIZADA = (
        "PREFERENCIA_INICIALIZADA",
        "Preferência inicializada",
    )
    PREFERENCIA_ALTERADA = "PREFERENCIA_ALTERADA", "Preferência alterada"


class ColetaEflow(ModeloAuditavel):
    """Snapshot imutável de uma exportação do E-Flow Admin."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    situacao = models.CharField(
        max_length=20,
        choices=SituacaoColetaEflow.choices,
        default=SituacaoColetaEflow.EM_PROCESSAMENTO,
    )
    arquivo_nome = models.CharField(max_length=255)
    arquivo_hash_sha256 = models.CharField(max_length=64, db_index=True)
    arquivo_tamanho_bytes = models.PositiveBigIntegerField()
    arquivo_conteudo = models.BinaryField(editable=False)
    iniciada_em = models.DateTimeField()
    concluida_em = models.DateTimeField(null=True, blank=True)
    quantidade_fluxos = models.PositiveIntegerField(default=0)
    quantidade_orgaos_participantes = models.PositiveIntegerField(default=0)
    quantidade_setores_ativos = models.PositiveIntegerField(default=0)
    orgaos_maior_quantidade_fluxos = models.JSONField(default=list, blank=True)
    distribuicao_publico_alvo = models.JSONField(default=list, blank=True)
    codigo_erro = models.CharField(max_length=100, blank=True, default="")
    mensagem_erro = models.CharField(max_length=500, blank=True, default="")

    class Meta:
        db_table = '"publicacoes"."coleta_eflow"'
        ordering = ("-iniciada_em",)
        permissions = [
            ("importar_coleta_eflow", "Pode importar coleta do E-Flow"),
        ]
        indexes = [models.Index(fields=("situacao", "iniciada_em"))]


class DefinicaoFluxoEflow(ModeloAuditavel):
    """Linha normalizada pertencente a um snapshot do E-Flow."""

    coleta = models.ForeignKey(
        ColetaEflow,
        on_delete=models.PROTECT,
        related_name="definicoes",
    )
    id_externo = models.UUIDField()
    nome = models.CharField(max_length=500)
    versao_origem = models.PositiveIntegerField()
    publico_alvo = models.CharField(
        max_length=30,
        choices=PublicoAlvoEflow.choices,
    )
    patriarca = models.ForeignKey(
        PatriarcaEdocs,
        on_delete=models.PROTECT,
        related_name="definicoes_fluxo_eflow",
    )
    patriarca_texto = models.CharField(max_length=300)
    orgao = models.CharField(max_length=500)
    setor = models.CharField(max_length=500)

    class Meta:
        db_table = '"publicacoes"."definicao_fluxo_eflow"'
        ordering = ("nome", "id_externo")
        constraints = [
            models.UniqueConstraint(
                fields=("coleta", "id_externo"),
                name="eflow_definicao_unica_por_coleta",
            )
        ]
        indexes = [
            models.Index(fields=("coleta", "patriarca")),
            models.Index(fields=("coleta", "publico_alvo")),
        ]


class ResultadoCalculoEflow(ModeloAuditavel):
    """Resultado imutável de um dos dois perfis aplicados ao snapshot."""

    coleta = models.ForeignKey(
        ColetaEflow,
        on_delete=models.PROTECT,
        related_name="resultados_calculo",
    )
    perfil = models.CharField(max_length=30, choices=PerfilCalculoEflow.choices)
    quantidade_fluxos = models.PositiveIntegerField()
    quantidade_orgaos_participantes = models.PositiveIntegerField()
    quantidade_setores_ativos = models.PositiveIntegerField()
    orgaos_maior_quantidade_fluxos = models.JSONField(default=list)
    distribuicao_publico_alvo = models.JSONField(default=list)
    calculado_em = models.DateTimeField()

    class Meta:
        db_table = '"publicacoes"."resultado_calculo_eflow"'
        ordering = ("perfil",)
        constraints = [
            models.UniqueConstraint(
                fields=("coleta", "perfil"),
                name="eflow_resultado_unico_por_perfil",
            )
        ]
        indexes = [models.Index(fields=("perfil", "calculado_em"))]


class PreferenciaExibicaoEflow(ModeloAuditavel):
    """Perfil E-Flow que deve ser aberto inicialmente para um usuário."""

    usuario = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="preferencia_exibicao_eflow",
    )
    perfil_preferido = models.CharField(
        max_length=30,
        choices=PerfilCalculoEflow.choices,
        default=PerfilCalculoEflow.CONSOLIDADO_PUBLICACAO,
    )

    class Meta:
        db_table = '"publicacoes"."preferencia_exibicao_eflow"'
        permissions = [
            (
                "alterar_preferencia_exibicao_eflow",
                "Pode alterar a própria preferência de exibição E-Flow",
            )
        ]


class EventoAuditoriaPreferenciaEflow(ModeloAuditavel):
    """Histórico append-only da preferência individual de exibição."""

    preferencia = models.ForeignKey(
        PreferenciaExibicaoEflow,
        on_delete=models.PROTECT,
        related_name="eventos_auditoria",
    )
    tipo_evento = models.CharField(
        max_length=30,
        choices=TipoEventoAuditoriaPreferenciaEflow.choices,
    )
    perfil_anterior = models.CharField(
        max_length=30,
        choices=PerfilCalculoEflow.choices,
        null=True,
        blank=True,
    )
    perfil_atual = models.CharField(
        max_length=30,
        choices=PerfilCalculoEflow.choices,
    )

    class Meta:
        db_table = '"publicacoes"."evento_auditoria_preferencia_eflow"'
        ordering = ("-criado_em", "-id")
        indexes = [models.Index(fields=("preferencia", "criado_em"))]


class EventoAuditoriaEflow(ModeloAuditavel):
    """Trilha append-only das coletas E-Flow."""

    coleta = models.ForeignKey(
        ColetaEflow,
        on_delete=models.PROTECT,
        related_name="eventos_auditoria",
    )
    tipo_evento = models.CharField(
        max_length=30,
        choices=TipoEventoAuditoriaEflow.choices,
    )
    mensagem = models.CharField(max_length=500)
    metadados = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = '"publicacoes"."evento_auditoria_eflow"'
        ordering = ("-criado_em", "-id")
        indexes = [models.Index(fields=("tipo_evento", "criado_em"))]
