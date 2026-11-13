"""Modelos do catálogo E-Docs de PUBLICAÇÕES."""

import uuid

from django.db import models
from django.db.models import Q

from common.models import ModeloAuditavel


class AmbienteEdocs(models.TextChoices):
    HML = "HML", "Homologação"
    PRD = "PRD", "Produção"


class SituacaoColetaPatriarcas(models.TextChoices):
    EM_EXECUCAO = "EM_EXECUCAO", "Em execução"
    CONCLUIDA = "CONCLUIDA", "Concluída"
    CONCLUIDA_COM_DIVERGENCIAS = (
        "CONCLUIDA_COM_DIVERGENCIAS",
        "Concluída com divergências",
    )
    FALHOU = "FALHOU", "Falhou"


class TipoComparacaoPatriarca(models.TextChoices):
    COINCIDENTE = "COINCIDENTE", "Sem divergência"
    NOVO = "NOVO", "Novo no E-Docs"
    ALTERADO = "ALTERADO", "Dados divergentes"
    AUSENTE = "AUSENTE", "Ausente no E-Docs"


class SituacaoDivergenciaPatriarca(models.TextChoices):
    PENDENTE = "PENDENTE", "Pendente"
    APLICADA = "APLICADA", "Aplicada"
    MANTIDA = "MANTIDA", "Cadastro mantido"
    SUBSTITUIDA = "SUBSTITUIDA", "Substituída por decisão posterior"


class DecisaoDivergenciaPatriarca(models.TextChoices):
    ADICIONAR = "ADICIONAR", "Adicionar"
    ATUALIZAR = "ATUALIZAR", "Atualizar"
    DESATIVAR = "DESATIVAR", "Desativar"
    MANTER = "MANTER", "Manter cadastro"


class TipoEventoAuditoriaPatriarca(models.TextChoices):
    COLETA_INICIADA = "COLETA_INICIADA", "Consulta iniciada"
    COLETA_CONCLUIDA = "COLETA_CONCLUIDA", "Consulta concluída"
    COLETA_FALHOU = "COLETA_FALHOU", "Consulta falhou"
    DIVERGENCIA_DETECTADA = "DIVERGENCIA_DETECTADA", "Divergência detectada"
    CATALOGO_INCLUIDO = "CATALOGO_INCLUIDO", "Patriarca incluído"
    CATALOGO_ATUALIZADO = "CATALOGO_ATUALIZADO", "Patriarca atualizado"
    CATALOGO_DESATIVADO = "CATALOGO_DESATIVADO", "Patriarca desativado"
    CATALOGO_MANTIDO = "CATALOGO_MANTIDO", "Cadastro mantido"
    SELECAO_COLETA_ALTERADA = (
        "SELECAO_COLETA_ALTERADA",
        "Seleção para coleta alterada",
    )
    INDICADOR_SEM_EDOCS_ALTERADO = (
        "INDICADOR_SEM_EDOCS_ALTERADO",
        "Indicador de município sem uso do E-Docs alterado",
    )
    INDICADORES_MUNICIPAIS_ALTERADOS = (
        "INDICADORES_MUNICIPAIS_ALTERADOS",
        "Indicadores municipais alterados",
    )


class TipoAgenteEdocs(models.IntegerChoices):
    CIDADAO = 1, "Cidadao"
    PAPEL = 2, "Papel"
    GRUPO = 3, "Grupo"
    UNIDADE = 4, "Unidade"
    ORGANIZACAO = 5, "Organizacao"
    SISTEMA = 6, "Sistema"
    NAO_IDENTIFICADO = 99, "NaoIdentificado"


class DescricaoTipoAgenteEdocs(models.TextChoices):
    CIDADAO = "Cidadao", "Cidadão"
    PAPEL = "Papel", "Papel"
    GRUPO = "Grupo", "Grupo"
    UNIDADE = "Unidade", "Unidade"
    ORGANIZACAO = "Organizacao", "Organização"
    SISTEMA = "Sistema", "Sistema"
    NAO_IDENTIFICADO = "NaoIdentificado", "Não identificado"


def condicao_tipo_agente_valido():
    """Relaciona o código numérico à descrição oficial do contrato E-Docs."""

    return (
        Q(tipo_agente=TipoAgenteEdocs.CIDADAO, descricao_tipo_agente="Cidadao")
        | Q(tipo_agente=TipoAgenteEdocs.PAPEL, descricao_tipo_agente="Papel")
        | Q(tipo_agente=TipoAgenteEdocs.GRUPO, descricao_tipo_agente="Grupo")
        | Q(tipo_agente=TipoAgenteEdocs.UNIDADE, descricao_tipo_agente="Unidade")
        | Q(
            tipo_agente=TipoAgenteEdocs.ORGANIZACAO,
            descricao_tipo_agente="Organizacao",
        )
        | Q(tipo_agente=TipoAgenteEdocs.SISTEMA, descricao_tipo_agente="Sistema")
        | Q(
            tipo_agente=TipoAgenteEdocs.NAO_IDENTIFICADO,
            descricao_tipo_agente="NaoIdentificado",
        )
    )


class PatriarcaEdocs(ModeloAuditavel):
    """Catálogo definitivo, alterado somente após decisão humana explícita."""

    id_externo = models.UUIDField(unique=True, verbose_name="ID no E-Docs")
    sigla = models.CharField(max_length=80, blank=True, verbose_name="Sigla")
    nome = models.CharField(max_length=300, verbose_name="Nome")
    tipo_agente = models.IntegerField(
        choices=TipoAgenteEdocs.choices,
        verbose_name="Tipo do agente",
    )
    descricao_tipo_agente = models.CharField(
        max_length=20,
        choices=DescricaoTipoAgenteEdocs.choices,
        verbose_name="Descrição do tipo",
    )
    coletar_detalhes = models.BooleanField(
        default=False,
        verbose_name="Coletar informações detalhadas",
    )
    codigo_municipio = models.PositiveIntegerField(
        null=True,
        blank=True,
        unique=True,
        verbose_name="Código IBGE do município",
    )
    municipio_implantado = models.BooleanField(
        default=False,
        verbose_name="Município implantado",
    )
    municipio_em_implantacao = models.BooleanField(
        default=False,
        verbose_name="Município em implantação",
    )
    municipio_manifestou_interesse = models.BooleanField(
        default=False,
        verbose_name="Município que manifestou interesse",
    )
    municipio_implantado_sem_uso_edocs = models.BooleanField(
        default=False,
        verbose_name="Município implantado sem uso do E-Docs",
    )
    ano_inicio_implantacao_sem_uso_edocs = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        verbose_name="Ano inicial da implantação sem uso do E-Docs",
    )
    mes_inicio_implantacao_sem_uso_edocs = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        verbose_name="Mês inicial da implantação sem uso do E-Docs",
    )
    ativo = models.BooleanField(default=True, verbose_name="Ativo")
    versao = models.PositiveIntegerField(default=1, editable=False)

    class Meta:
        db_table = '"publicacoes"."patriarca_edocs"'
        ordering = ("nome", "id_externo")
        indexes = [
            models.Index(fields=("ativo", "coletar_detalhes")),
            models.Index(fields=("sigla",)),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(ativo=True) | Q(coletar_detalhes=False),
                name="edocs_inativo_sem_coleta_detalhada",
            ),
            models.CheckConstraint(
                condition=condicao_tipo_agente_valido(),
                name="edocs_patriarca_tipo_agente_valido",
            ),
            models.CheckConstraint(
                condition=(
                    Q(codigo_municipio__isnull=True)
                    | Q(
                        codigo_municipio__gte=1_000_000,
                        codigo_municipio__lte=9_999_999,
                    )
                ),
                name="edocs_codigo_municipio_valido",
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        municipio_implantado_sem_uso_edocs=False,
                        ano_inicio_implantacao_sem_uso_edocs__isnull=True,
                        mes_inicio_implantacao_sem_uso_edocs__isnull=True,
                    )
                    | Q(
                        municipio_implantado_sem_uso_edocs=True,
                        ano_inicio_implantacao_sem_uso_edocs__isnull=True,
                        mes_inicio_implantacao_sem_uso_edocs__isnull=True,
                    )
                    | Q(
                        municipio_implantado_sem_uso_edocs=True,
                        ano_inicio_implantacao_sem_uso_edocs__gte=2024,
                        mes_inicio_implantacao_sem_uso_edocs__gte=1,
                        mes_inicio_implantacao_sem_uso_edocs__lte=12,
                    )
                ),
                name="edocs_sem_uso_vigencia_coerente",
            ),
        ]
        permissions = [
            ("consultar_patriarcas_edocs", "Pode consultar patriarcas no E-Docs"),
            ("revisar_patriarcas_edocs", "Pode decidir divergências de patriarcas"),
            (
                "selecionar_patriarcas_coleta",
                "Pode selecionar patriarcas para coleta detalhada",
            ),
            (
                "alterar_indicador_municipio_sem_edocs",
                "Pode alterar o indicador de município sem uso do E-Docs",
            ),
            (
                "alterar_indicadores_municipais_edocs",
                "Pode alterar os indicadores municipais do E-Docs",
            ),
        ]

    def __str__(self):
        return f"{self.sigla} - {self.nome}" if self.sigla else self.nome


class ColetaPatriarcasEdocs(ModeloAuditavel):
    """Execução persistida de uma consulta ao catálogo remoto."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    ambiente = models.CharField(max_length=3, choices=AmbienteEdocs.choices)
    situacao = models.CharField(
        max_length=32,
        choices=SituacaoColetaPatriarcas.choices,
        default=SituacaoColetaPatriarcas.EM_EXECUCAO,
    )
    iniciada_em = models.DateTimeField()
    concluida_em = models.DateTimeField(null=True, blank=True)
    hash_fonte = models.CharField(max_length=64, blank=True, editable=False)
    quantidade_observados = models.PositiveIntegerField(default=0)
    quantidade_coincidentes = models.PositiveIntegerField(default=0)
    quantidade_novos = models.PositiveIntegerField(default=0)
    quantidade_alterados = models.PositiveIntegerField(default=0)
    quantidade_ausentes = models.PositiveIntegerField(default=0)
    quantidade_pendentes = models.PositiveIntegerField(default=0)
    codigo_erro = models.CharField(max_length=80, blank=True)
    mensagem_erro = models.CharField(max_length=500, blank=True)

    class Meta:
        db_table = '"publicacoes"."coleta_patriarcas_edocs"'
        ordering = ("-iniciada_em",)
        indexes = [models.Index(fields=("situacao", "iniciada_em"))]
        permissions = [
            (
                "visualizar_coletas_patriarcas",
                "Pode visualizar coletas de patriarcas do E-Docs",
            ),
            (
                "solicitar_coleta_patriarcas_edocs",
                "Pode solicitar uma nova coleta de patriarcas do E-Docs",
            ),
        ]


class ObservacaoPatriarcaEdocs(ModeloAuditavel):
    """Retrato normalizado e imutável de um patriarca retornado pelo E-Docs."""

    coleta = models.ForeignKey(
        ColetaPatriarcasEdocs,
        on_delete=models.PROTECT,
        related_name="observacoes",
    )
    patriarca = models.ForeignKey(
        PatriarcaEdocs,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="observacoes",
    )
    id_externo = models.UUIDField()
    sigla = models.CharField(max_length=80, blank=True)
    nome = models.CharField(max_length=300)
    tipo_agente = models.IntegerField(choices=TipoAgenteEdocs.choices)
    descricao_tipo_agente = models.CharField(
        max_length=20,
        choices=DescricaoTipoAgenteEdocs.choices,
    )
    comparacao = models.CharField(max_length=16, choices=TipoComparacaoPatriarca.choices)
    hash_conteudo = models.CharField(max_length=64, editable=False)

    class Meta:
        db_table = '"publicacoes"."observacao_patriarca_edocs"'
        ordering = ("nome", "id_externo")
        constraints = [
            models.UniqueConstraint(
                fields=("coleta", "id_externo"),
                name="edocs_observacao_unica_por_coleta",
            ),
            models.CheckConstraint(
                condition=condicao_tipo_agente_valido(),
                name="edocs_observacao_tipo_agente_valido",
            ),
        ]
        indexes = [models.Index(fields=("coleta", "comparacao"))]


class DivergenciaPatriarcaEdocs(ModeloAuditavel):
    """Mudança proposta que aguarda decisão e justificativa de um usuário."""

    coleta = models.ForeignKey(
        ColetaPatriarcasEdocs,
        on_delete=models.PROTECT,
        related_name="divergencias",
    )
    observacao = models.OneToOneField(
        ObservacaoPatriarcaEdocs,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="divergencia",
    )
    patriarca = models.ForeignKey(
        PatriarcaEdocs,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="divergencias",
    )
    id_externo = models.UUIDField()
    comparacao = models.CharField(max_length=16, choices=TipoComparacaoPatriarca.choices)
    situacao = models.CharField(
        max_length=20,
        choices=SituacaoDivergenciaPatriarca.choices,
        default=SituacaoDivergenciaPatriarca.PENDENTE,
    )
    dados_esperados = models.JSONField(default=dict)
    dados_observados = models.JSONField(null=True, blank=True)
    campos_alterados = models.JSONField(default=list)
    decisao = models.CharField(
        max_length=20,
        choices=DecisaoDivergenciaPatriarca.choices,
        blank=True,
    )
    justificativa = models.TextField(blank=True)
    revisado_por_id = models.IntegerField(null=True, blank=True, editable=False)
    revisado_por_nome = models.CharField(max_length=200, blank=True, editable=False)
    revisado_em = models.DateTimeField(null=True, blank=True, editable=False)

    class Meta:
        db_table = '"publicacoes"."divergencia_patriarca_edocs"'
        ordering = ("-criado_em",)
        constraints = [
            models.UniqueConstraint(
                fields=("coleta", "id_externo", "comparacao"),
                name="edocs_divergencia_unica_por_coleta",
            ),
            models.CheckConstraint(
                condition=~Q(comparacao=TipoComparacaoPatriarca.COINCIDENTE),
                name="edocs_divergencia_nao_coincidente",
            ),
        ]
        indexes = [
            models.Index(fields=("situacao", "comparacao")),
            models.Index(fields=("id_externo", "situacao")),
        ]


class EventoAuditoriaPatriarcaEdocs(ModeloAuditavel):
    """Trilha append-only dos fatos e decisões do catálogo de patriarcas."""

    coleta = models.ForeignKey(
        ColetaPatriarcasEdocs,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="eventos_auditoria",
    )
    patriarca = models.ForeignKey(
        PatriarcaEdocs,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="eventos_auditoria",
    )
    divergencia = models.ForeignKey(
        DivergenciaPatriarcaEdocs,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="eventos_auditoria",
    )
    tipo_evento = models.CharField(max_length=40, choices=TipoEventoAuditoriaPatriarca.choices)
    mensagem = models.CharField(max_length=500)
    dados_anteriores = models.JSONField(null=True, blank=True)
    dados_atuais = models.JSONField(null=True, blank=True)
    metadados = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = '"publicacoes"."evento_auditoria_patriarca_edocs"'
        ordering = ("-criado_em", "-id")
        indexes = [models.Index(fields=("tipo_evento", "criado_em"))]
