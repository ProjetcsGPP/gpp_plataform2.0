"""Contratos de entrada e saída da API administrativa E-Docs."""

from rest_framework import serializers

from apps.pub_institucional.models import (
    ColetaPatriarcasEdocs,
    DecisaoDivergenciaPatriarca,
    DivergenciaPatriarcaEdocs,
    EventoAuditoriaPatriarcaEdocs,
    PatriarcaEdocs,
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
            "ativo",
            "versao",
            "criado_em",
            "atualizado_em",
            "acoes_disponiveis",
        )
        read_only_fields = fields

    def get_acoes_disponiveis(self, objeto) -> list[str]:
        if self.context.get("pode_selecionar") and objeto.ativo:
            return ["alterar_selecao_coleta"]
        return []


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
