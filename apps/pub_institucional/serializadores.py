"""Contratos de entrada e saída da API administrativa E-Docs."""

from django.conf import settings
from rest_framework import serializers

from apps.pub_institucional.models import (ColetaEflow, ColetaMensalEdocs,
                                           ConfiguracaoVisaoPublicacao,
                                           ColetaPatriarcasEdocs,
                                           DecisaoDivergenciaPatriarca,
                                           DefinicaoFluxoEflow,
                                           DivergenciaPatriarcaEdocs,
                                           EventoAuditoriaColetaMensalEdocs,
                                           EventoAuditoriaEflow,
                                           EventoAuditoriaPatriarcaEdocs,
                                           EventoAuditoriaPreferenciaEflow,
                                           FonteBrutaColetaMensalEdocs,
                                           HistoricoPublicacao,
                                           ImplantacaoPatriarcaEdocs,
                                           PatriarcaEdocs, PerfilCalculoEflow,
                                           PreferenciaExibicaoEflow,
                                           Publicacao,
                                           ResultadoCalculoEflow,
                                           ResultadoMensalOrganizacaoEdocs,
                                           ResultadoMensalPatriarcaEdocs,
                                           SecaoPublicacao,
                                           SituacaoColetaMensalEdocs,
                                           SituacaoDivergenciaPatriarca)
from apps.pub_institucional.services.patriarcas_edocs import DECISOES_VALIDAS


class SerializadorPatriarcaEdocs(serializers.ModelSerializer):
    """Representa o cadastro definitivo sem permitir edição genérica."""

    acoes_disponiveis = serializers.SerializerMethodField()
    implantacao_edocs_observada = serializers.SerializerMethodField()

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
            "implantacao_edocs_observada",
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

    def get_implantacao_edocs_observada(self, objeto) -> dict | None:
        try:
            implantacao = objeto.implantacao_edocs_observada
        except ImplantacaoPatriarcaEdocs.DoesNotExist:
            return None
        return {
            "ano": implantacao.ano,
            "mes": implantacao.mes,
            "competencia": f"{implantacao.ano:04d}-{implantacao.mes:02d}",
            "coleta_evidencia_id": str(implantacao.coleta_evidencia_id),
            "criterio": implantacao.criterio,
            "totais_evidencia": implantacao.totais_evidencia,
            "criado_em": implantacao.criado_em,
        }


class SerializadorImplantacaoPatriarcaEdocs(serializers.ModelSerializer):
    patriarca_sigla = serializers.CharField(source="patriarca.sigla", read_only=True)
    patriarca_nome = serializers.CharField(source="patriarca.nome", read_only=True)
    competencia = serializers.SerializerMethodField()
    coleta_evidencia_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = ImplantacaoPatriarcaEdocs
        fields = (
            "id",
            "patriarca_id",
            "patriarca_sigla",
            "patriarca_nome",
            "ano",
            "mes",
            "competencia",
            "coleta_evidencia_id",
            "criterio",
            "totais_evidencia",
            "criado_em",
        )
        read_only_fields = fields

    def get_competencia(self, objeto) -> str:
        return f"{objeto.ano:04d}-{objeto.mes:02d}"


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
    acoes_disponiveis = serializers.SerializerMethodField()

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
            "acoes_disponiveis",
        )
        read_only_fields = fields

    def get_acoes_disponiveis(self, objeto) -> list[str]:
        if (
            self.context.get("pode_solicitar")
            and objeto.situacao == SituacaoColetaMensalEdocs.SOLICITADA
        ):
            return ["reencaminhar"]
        return []


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
            "versao_calculo",
            "economia_papel_kg",
            "gases_poluentes_kg",
            "economia_papel_reais",
            "economia_insumos_reais",
            "economia_impressao_reais",
            "economia_total_reais",
            "economia_agua_m3",
            "arvores_salvas",
        )
        read_only_fields = fields


class SerializadorSomatoriosEdocs(serializers.Serializer):
    """Campos numericos comuns aos consolidados do E-Docs."""

    total_processos = serializers.IntegerField(read_only=True)
    total_documentos = serializers.IntegerField(read_only=True)
    total_paginas = serializers.IntegerField(read_only=True)
    economia_papel_kg = serializers.DecimalField(
        max_digits=28, decimal_places=5, read_only=True
    )
    gases_poluentes_kg = serializers.DecimalField(
        max_digits=28, decimal_places=4, read_only=True
    )
    economia_papel_reais = serializers.DecimalField(
        max_digits=28, decimal_places=2, read_only=True
    )
    economia_insumos_reais = serializers.DecimalField(
        max_digits=28, decimal_places=2, read_only=True
    )
    economia_impressao_reais = serializers.DecimalField(
        max_digits=28, decimal_places=2, read_only=True
    )
    economia_total_reais = serializers.DecimalField(
        max_digits=28, decimal_places=2, read_only=True
    )
    economia_agua_m3 = serializers.DecimalField(
        max_digits=28, decimal_places=2, read_only=True
    )
    arvores_salvas = serializers.DecimalField(
        max_digits=28, decimal_places=4, read_only=True
    )


class SerializadorTotaisResultadoMensalEdocs(SerializadorSomatoriosEdocs):
    """Consolidado de todos os municipios da mesma revisao mensal."""

    coleta_id = serializers.UUIDField(read_only=True)
    quantidade_municipios = serializers.IntegerField(read_only=True)
    versao_calculo = serializers.CharField(read_only=True)


class SerializadorTotaisHistoricosEdocs(SerializadorSomatoriosEdocs):
    """Consolidado anual ou historico, geral ou de um municipio."""

    ano = serializers.IntegerField(read_only=True, allow_null=True)
    patriarca_id = serializers.IntegerField(read_only=True, allow_null=True)
    codigo_municipio = serializers.IntegerField(read_only=True, allow_null=True)
    nome_municipio = serializers.CharField(read_only=True, allow_null=True)
    quantidade_competencias = serializers.IntegerField(read_only=True)
    quantidade_municipios = serializers.IntegerField(read_only=True)
    versoes_calculo = serializers.ListField(
        child=serializers.CharField(),
        read_only=True,
    )


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
    ano_vigencia_inicio = serializers.IntegerField(min_value=2024, max_value=9999)
    mes_vigencia_inicio = serializers.IntegerField(min_value=1, max_value=12)
    vigencia_retroativa = serializers.BooleanField(required=False, default=False)

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
            "ano_vigencia_inicio",
            "mes_vigencia_inicio",
            "vigencia_retroativa",
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


class SerializadorConfiguracaoVisaoPublicacao(serializers.ModelSerializer):
    """Configuração reutilizável; versões publicadas congelam sua fotografia."""

    patriarcas_ids = serializers.PrimaryKeyRelatedField(
        source="patriarcas",
        queryset=PatriarcaEdocs.objects.all(),
        many=True,
        required=False,
    )

    class Meta:
        model = ConfiguracaoVisaoPublicacao
        fields = (
            "id",
            "codigo",
            "nome",
            "descricao",
            "fonte",
            "escopo",
            "perfil_calculo_eflow",
            "ativa",
            "versao",
            "patriarcas_ids",
            "criado_em",
            "atualizado_em",
        )
        read_only_fields = ("id", "versao", "criado_em", "atualizado_em")

    def validate(self, atributos):
        fonte = atributos.get("fonte", getattr(self.instance, "fonte", None))
        perfil = atributos.get(
            "perfil_calculo_eflow",
            getattr(self.instance, "perfil_calculo_eflow", ""),
        )
        escopo = atributos.get("escopo", getattr(self.instance, "escopo", None))
        patriarcas = atributos.get("patriarcas", [])
        if fonte == "EFLOW" and perfil not in PerfilCalculoEflow.values:
            raise serializers.ValidationError(
                {"perfil_calculo_eflow": "Informe um perfil E-Flow válido."}
            )
        if fonte == "EDOCS":
            atributos["perfil_calculo_eflow"] = ""
        if escopo == "PERSONALIZADO" and not (
            patriarcas or (self.instance and self.instance.patriarcas.exists())
        ):
            raise serializers.ValidationError(
                {"patriarcas_ids": "Selecione ao menos um patriarca."}
            )
        return atributos


class SerializadorSecaoPublicacao(serializers.ModelSerializer):
    coleta_edocs_id = serializers.UUIDField(read_only=True, allow_null=True)
    coleta_eflow_id = serializers.UUIDField(read_only=True, allow_null=True)
    configuracao_visao_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = SecaoPublicacao
        fields = (
            "id",
            "ordem",
            "titulo",
            "fonte",
            "configuracao_visao_id",
            "coleta_edocs_id",
            "coleta_eflow_id",
            "perfil_calculo",
            "configuracao_congelada",
            "resultado",
            "calculada_em",
            "hash_resultado",
        )
        read_only_fields = fields


class SerializadorHistoricoPublicacao(serializers.ModelSerializer):
    class Meta:
        model = HistoricoPublicacao
        fields = (
            "id",
            "tipo_evento",
            "situacao_anterior",
            "situacao_atual",
            "justificativa",
            "metadados",
            "criado_por_id",
            "criado_por_nome",
            "criado_em",
        )
        read_only_fields = fields


class SerializadorPublicacao(serializers.ModelSerializer):
    competencia = serializers.SerializerMethodField()
    secoes = SerializadorSecaoPublicacao(many=True, read_only=True)
    acoes_disponiveis = serializers.SerializerMethodField()
    publicacao_anterior_id = serializers.UUIDField(
        read_only=True,
        allow_null=True,
    )

    class Meta:
        model = Publicacao
        fields = (
            "id",
            "serie_id",
            "versao",
            "titulo",
            "ano_referencia",
            "mes_referencia",
            "competencia",
            "situacao",
            "versao_registro",
            "publicacao_anterior_id",
            "justificativa_publicacao",
            "publicada_em",
            "publicada_por_id",
            "publicada_por_nome",
            "hash_conteudo",
            "secoes",
            "acoes_disponiveis",
            "criado_em",
            "atualizado_em",
        )
        read_only_fields = fields

    def get_competencia(self, objeto) -> str:
        return f"{objeto.ano_referencia:04d}-{objeto.mes_referencia:02d}"

    def get_acoes_disponiveis(self, objeto) -> list[str]:
        permissoes = self.context.get("permissoes_acoes", set())
        acoes = []
        if objeto.situacao == "RASCUNHO":
            if "calcular_publicacao" in permissoes:
                acoes.append("recalcular")
            if "change_publicacao" in permissoes:
                acoes.extend(("adicionar_secao", "remover_secao"))
        if objeto.situacao == "AGUARDANDO_PUBLICACAO":
            if "publicar_publicacao" in permissoes:
                acoes.append("publicar")
            if "change_publicacao" in permissoes:
                acoes.append("reabrir")
        if objeto.situacao == "PUBLICADA":
            if "substituir_publicacao" in permissoes:
                acoes.append("substituir")
            if "revogar_publicacao" in permissoes:
                acoes.append("revogar")
        if "visualizar_previa_publicacao" in permissoes:
            acoes.append("visualizar_previa")
        return acoes


class SerializadorCriacaoPublicacao(serializers.Serializer):
    titulo = serializers.CharField(max_length=250)
    ano_referencia = serializers.IntegerField(min_value=2024, max_value=9999)
    mes_referencia = serializers.IntegerField(min_value=1, max_value=12)


class SerializadorCriacaoSecaoPublicacao(serializers.Serializer):
    configuracao_visao_id = serializers.UUIDField()
    titulo = serializers.CharField(max_length=200)
    ordem = serializers.IntegerField(min_value=1, max_value=999)
    coleta_id = serializers.UUIDField(required=False)


class SerializadorRemocaoSecaoPublicacao(serializers.Serializer):
    secao_id = serializers.UUIDField()


class SerializadorTransicaoPublicacao(serializers.Serializer):
    justificativa = serializers.CharField(trim_whitespace=True)
    versao_registro = serializers.IntegerField(min_value=1, required=False)
