"""Contratos de entrada e saída da API administrativa E-Docs."""

from django.conf import settings
from rest_framework import serializers

from apps.pub_institucional.models import (
    ColetaEflow,
    ColetaMensalEdocs,
    ColetaPatriarcasEdocs,
    DecisaoDivergenciaPatriarca,
    DefinicaoFluxoEflow,
    DivergenciaPatriarcaEdocs,
    EventoAuditoriaColetaMensalEdocs,
    EventoAuditoriaEflow,
    EventoAuditoriaPatriarcaEdocs,
    EventoAuditoriaPreferenciaEflow,
    FonteBrutaColetaMensalEdocs,
    PatriarcaEdocs,
    PerfilCalculoEflow,
    PreferenciaExibicaoEflow,
    ResultadoCalculoEflow,
    ResultadoMensalOrganizacaoEdocs,
    ResultadoMensalPatriarcaEdocs,
    SituacaoDivergenciaPatriarca,
)
from apps.pub_institucional.services.patriarcas_edocs import DECISOES_VALIDAS


class SerializadorPatriarcaEdocs(serializers.ModelSerializer):
    """Representa o cadastro definitivo sem permitir edição genérica."""

    acoes_disponiveis = serializers.SerializerMethodField()

    class Meta:
        model = PatriarcaEdocs
        fields = (
            "id",
            "id_externo",
            "sigla",
            "nome",
            "tipo_agente",
            "descricao_tipo_agente",
            "coletar_detalhes",
            "codigo_municipio",
            "municipio_implantado",
            "municipio_em_implantacao",
            "municipio_manifestou_interesse",
            "municipio_implantado_sem_uso_edocs",
            "ativo",
            "versao",
            "criado_em",
            "atualizado_em",
            "acoes_disponiveis",
        )
        read_only_fields = fields

    def get_acoes_disponiveis(self, objeto) -> list[str]:
        acoes = []
        if self.context.get("pode_selecionar") and objeto.ativo:
            acoes.append("alterar_selecao_coleta")
        if self.context.get("pode_alterar_indicador"):
            acoes.append("alterar_indicador_municipio_sem_edocs")
        if self.context.get("pode_alterar_indicadores_municipais"):
            acoes.append("alterar_indicadores_municipais")
        return acoes


class SerializadorColetaPatriarcasEdocs(serializers.ModelSerializer):
    """Resume uma execução de comparação do catálogo remoto."""

    class Meta:
        model = ColetaPatriarcasEdocs
        fields = (
            "id",
            "ambiente",
            "situacao",
            "iniciada_em",
            "concluida_em",
            "hash_fonte",
            "quantidade_observados",
            "quantidade_coincidentes",
            "quantidade_novos",
            "quantidade_alterados",
            "quantidade_ausentes",
            "quantidade_pendentes",
            "codigo_erro",
            "mensagem_erro",
            "criado_por_id",
            "criado_por_nome",
        )
        read_only_fields = fields


class SerializadorDivergenciaPatriarcaEdocs(serializers.ModelSerializer):
    """Expõe a comparação e somente as decisões atualmente permitidas."""

    coleta_id = serializers.UUIDField(read_only=True)
    patriarca_id = serializers.IntegerField(read_only=True, allow_null=True)
    decisoes_permitidas = serializers.SerializerMethodField()
    acoes_disponiveis = serializers.SerializerMethodField()

    class Meta:
        model = DivergenciaPatriarcaEdocs
        fields = (
            "id",
            "coleta_id",
            "patriarca_id",
            "id_externo",
            "comparacao",
            "situacao",
            "dados_esperados",
            "dados_observados",
            "campos_alterados",
            "decisao",
            "justificativa",
            "revisado_por_id",
            "revisado_por_nome",
            "revisado_em",
            "criado_em",
            "decisoes_permitidas",
            "acoes_disponiveis",
        )
        read_only_fields = fields

    def get_decisoes_permitidas(self, objeto) -> list[str]:
        if (
            objeto.situacao != SituacaoDivergenciaPatriarca.PENDENTE
            or not self.context.get("pode_revisar")
        ):
            return []
        return sorted(DECISOES_VALIDAS[objeto.comparacao])

    def get_acoes_disponiveis(self, objeto) -> list[str]:
        if self.get_decisoes_permitidas(objeto):
            return ["decidir"]
        return []


class SerializadorEventoAuditoriaPatriarcaEdocs(serializers.ModelSerializer):
    """Representa a trilha append-only do catálogo E-Docs."""

    coleta_id = serializers.UUIDField(read_only=True, allow_null=True)
    patriarca_id = serializers.IntegerField(read_only=True, allow_null=True)
    divergencia_id = serializers.IntegerField(read_only=True, allow_null=True)

    class Meta:
        model = EventoAuditoriaPatriarcaEdocs
        fields = (
            "id",
            "coleta_id",
            "patriarca_id",
            "divergencia_id",
            "tipo_evento",
            "mensagem",
            "dados_anteriores",
            "dados_atuais",
            "metadados",
            "criado_por_id",
            "criado_por_nome",
            "criado_em",
        )
        read_only_fields = fields


class SerializadorDecisaoDivergencia(serializers.Serializer):
    """Valida a intenção do gestor antes da regra transacional de domínio."""

    decisao = serializers.ChoiceField(choices=DecisaoDivergenciaPatriarca.choices)
    justificativa = serializers.CharField(trim_whitespace=True, allow_blank=False)
    coletar_detalhes = serializers.BooleanField(required=False, allow_null=True)


class SerializadorSelecaoColeta(serializers.Serializer):
    """Valida a seleção explícita para as demais coletas E-Docs."""

    coletar_detalhes = serializers.BooleanField()
    justificativa = serializers.CharField(trim_whitespace=True, allow_blank=False)


class SerializadorIndicadorMunicipioSemEdocs(serializers.Serializer):
    """Valida a manutenção manual do indicador municipal."""

    municipio_implantado_sem_uso_edocs = serializers.BooleanField()
    justificativa = serializers.CharField(trim_whitespace=True, allow_blank=False)


class SerializadorIndicadoresMunicipaisEdocs(serializers.Serializer):
    """Valida a manutenção parcial dos indicadores municipais manuais."""

    codigo_municipio = serializers.IntegerField(
        min_value=1_000_000,
        max_value=9_999_999,
        required=False,
        allow_null=True,
    )
    municipio_implantado = serializers.BooleanField(required=False)
    municipio_em_implantacao = serializers.BooleanField(required=False)
    municipio_manifestou_interesse = serializers.BooleanField(required=False)
    municipio_implantado_sem_uso_edocs = serializers.BooleanField(required=False)
    justificativa = serializers.CharField(trim_whitespace=True, allow_blank=False)

    def validate(self, attrs):
        if set(attrs) == {"justificativa"}:
            raise serializers.ValidationError(
                "Informe ao menos um indicador municipal."
            )
        return attrs


class SerializadorSolicitacaoColetaMensalEdocs(serializers.Serializer):
    """Valida a competência solicitada sem impor o início histórico."""

    ano = serializers.IntegerField(min_value=2000, max_value=9999)
    mes = serializers.IntegerField(min_value=1, max_value=12)


class SerializadorColetaMensalEdocs(serializers.ModelSerializer):
    """Resume uma revisão mensal e suas contagens canônicas."""

    ano = serializers.IntegerField(source="competencia.ano", read_only=True)
    mes = serializers.IntegerField(source="competencia.mes", read_only=True)

    class Meta:
        model = ColetaMensalEdocs
        fields = (
            "id",
            "ano",
            "mes",
            "revisao",
            "ambiente",
            "situacao",
            "iniciada_em",
            "concluida_em",
            "quantidade_patriarcas",
            "quantidade_organizacoes",
            "quantidade_fontes_brutas",
            "patriarcas_solicitados",
            "hash_resultado",
            "codigo_erro",
            "mensagem_erro",
            "criado_por_id",
            "criado_por_nome",
            "criado_em",
        )
        read_only_fields = fields


class SerializadorResultadoMensalPatriarcaEdocs(serializers.ModelSerializer):
    coleta_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = ResultadoMensalPatriarcaEdocs
        fields = (
            "id",
            "coleta_id",
            "patriarca_id",
            "id_patriarca_externo",
            "sigla_patriarca",
            "nome_patriarca",
            "codigo_municipio",
            "total_processos",
            "total_documentos",
            "total_paginas",
        )
        read_only_fields = fields


class SerializadorResultadoMensalOrganizacaoEdocs(serializers.ModelSerializer):
    coleta_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = ResultadoMensalOrganizacaoEdocs
        fields = (
            "id",
            "coleta_id",
            "patriarca_id",
            "id_patriarca_externo",
            "nome_patriarca",
            "id_organizacao_externo",
            "nome_organizacao",
            "total_processos",
            "total_documentos",
            "total_paginas",
        )
        read_only_fields = fields


class SerializadorFonteBrutaColetaMensalEdocs(serializers.ModelSerializer):
    """Expõe metadados da evidência sem transferir o JSON bruto pela listagem."""

    coleta_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = FonteBrutaColetaMensalEdocs
        fields = (
            "id",
            "coleta_id",
            "codigo_fonte",
            "patriarca_id",
            "id_patriarca_externo",
            "hash_sha256",
            "criado_em",
        )
        read_only_fields = fields


class SerializadorEventoAuditoriaColetaMensalEdocs(serializers.ModelSerializer):
    coleta_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = EventoAuditoriaColetaMensalEdocs
        fields = (
            "id",
            "coleta_id",
            "tipo_evento",
            "mensagem",
            "metadados",
            "criado_por_id",
            "criado_por_nome",
            "criado_em",
        )
        read_only_fields = fields


class SerializadorArquivoEflow(serializers.Serializer):
    """Valida a presença do CSV sem interpretar seu conteúdo no transporte."""

    arquivo = serializers.FileField(allow_empty_file=False)

    def validate_arquivo(self, arquivo):
        if arquivo.size > settings.GPP_EFLOW_CSV_MAX_BYTES:
            raise serializers.ValidationError(
                "O arquivo E-Flow excede o tamanho máximo permitido.",
                code="arquivo_acima_do_limite",
            )
        return arquivo


class SerializadorResultadoCalculoEflow(serializers.ModelSerializer):
    """Expõe um perfil fechado calculado sobre o snapshot."""

    coleta_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = ResultadoCalculoEflow
        fields = (
            "id",
            "coleta_id",
            "perfil",
            "quantidade_fluxos",
            "quantidade_orgaos_participantes",
            "quantidade_setores_ativos",
            "orgaos_maior_quantidade_fluxos",
            "distribuicao_publico_alvo",
            "calculado_em",
        )
        read_only_fields = fields


class SerializadorColetaEflow(serializers.ModelSerializer):
    """Expõe o snapshot e seus indicadores, sem devolver o binário original."""

    resultados_calculo = SerializadorResultadoCalculoEflow(
        many=True,
        read_only=True,
    )

    class Meta:
        model = ColetaEflow
        fields = (
            "id",
            "situacao",
            "arquivo_nome",
            "arquivo_hash_sha256",
            "arquivo_tamanho_bytes",
            "iniciada_em",
            "concluida_em",
            "quantidade_fluxos",
            "quantidade_orgaos_participantes",
            "quantidade_setores_ativos",
            "orgaos_maior_quantidade_fluxos",
            "distribuicao_publico_alvo",
            "codigo_erro",
            "mensagem_erro",
            "resultados_calculo",
            "criado_por_id",
            "criado_por_nome",
        )
        read_only_fields = fields


class SerializadorDefinicaoFluxoEflow(serializers.ModelSerializer):
    """Representa uma linha normalizada da exportação E-Flow."""

    coleta_id = serializers.UUIDField(read_only=True)
    patriarca_id = serializers.IntegerField(read_only=True)
    patriarca_sigla = serializers.CharField(source="patriarca.sigla", read_only=True)
    patriarca_nome = serializers.CharField(source="patriarca.nome", read_only=True)

    class Meta:
        model = DefinicaoFluxoEflow
        fields = (
            "id",
            "coleta_id",
            "id_externo",
            "nome",
            "versao_origem",
            "publico_alvo",
            "patriarca_id",
            "patriarca_sigla",
            "patriarca_nome",
            "patriarca_texto",
            "orgao",
            "setor",
        )
        read_only_fields = fields


class SerializadorEventoAuditoriaEflow(serializers.ModelSerializer):
    """Expõe a trilha append-only de uma coleta E-Flow."""

    coleta_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = EventoAuditoriaEflow
        fields = (
            "id",
            "coleta_id",
            "tipo_evento",
            "mensagem",
            "metadados",
            "criado_por_id",
            "criado_por_nome",
            "criado_em",
        )
        read_only_fields = fields


class SerializadorPreferenciaExibicaoEflow(serializers.ModelSerializer):
    """Expõe a preferência individual e a ação atualmente autorizada."""

    usuario_id = serializers.IntegerField(read_only=True)
    acoes_disponiveis = serializers.SerializerMethodField()

    class Meta:
        model = PreferenciaExibicaoEflow
        fields = (
            "id",
            "usuario_id",
            "perfil_preferido",
            "atualizado_em",
            "atualizado_por_id",
            "atualizado_por_nome",
            "acoes_disponiveis",
        )
        read_only_fields = fields

    def get_acoes_disponiveis(self, objeto) -> list[str]:
        if self.context.get("pode_alterar"):
            return ["alterar_preferencia_exibicao"]
        return []


class SerializadorAlteracaoPreferenciaEflow(serializers.Serializer):
    """Restringe a escolha aos dois perfis fechados."""

    perfil_preferido = serializers.ChoiceField(choices=PerfilCalculoEflow.choices)


class SerializadorEventoAuditoriaPreferenciaEflow(serializers.ModelSerializer):
    """Expõe somente eventos da preferência do usuário autenticado."""

    preferencia_id = serializers.IntegerField(read_only=True)

    class Meta:
        model = EventoAuditoriaPreferenciaEflow
        fields = (
            "id",
            "preferencia_id",
            "tipo_evento",
            "perfil_anterior",
            "perfil_atual",
            "criado_por_id",
            "criado_por_nome",
            "criado_em",
        )
        read_only_fields = fields
