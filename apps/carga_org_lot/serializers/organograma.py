"""Serializers de edição e envio de organogramas."""

from rest_framework import serializers

from common.serializers import AuditableModelSerializer

from ..models import (
    EnvioOrganogramaProdest,
    ImportacaoPlanilha,
    ItemOrganograma,
    Patriarca,
    StatusEnvioOrganograma,
    StatusImportacaoLocal,
)
from ..services.organograma import (
    ORGAN_ACRONYM_MAX_LENGTH,
    ORGAN_NAME_MAX_LENGTH,
    ORGANOGRAMA_TYPE_ID,
    UNIT_ACRONYM_MAX_LENGTH,
    UNIT_NAME_MAX_LENGTH,
)


class ItemOrganogramaSerializer(AuditableModelSerializer):
    idimportacaoplanilha_id = serializers.PrimaryKeyRelatedField(
        source="idimportacaoplanilha",
        queryset=ImportacaoPlanilha.objects.filter(idtipocarga_id=ORGANOGRAMA_TYPE_ID),
    )
    idpai_id = serializers.PrimaryKeyRelatedField(
        source="idpai",
        queryset=ItemOrganograma.objects.all(),
        required=False,
        allow_null=True,
    )
    pai_sigla = serializers.CharField(source="idpai.strsigla", read_only=True)
    strabaorigem = serializers.CharField(
        required=False,
        allow_blank=True,
        default="Edição manual",
    )
    intlinhaorigem = serializers.IntegerField(required=False, min_value=0, default=0)

    class Meta(AuditableModelSerializer.Meta):
        model = ItemOrganograma
        fields = AuditableModelSerializer.Meta.fields + [
            "iditemorganograma",
            "idimportacaoplanilha_id",
            "idpai_id",
            "pai_sigla",
            "strnome",
            "strsigla",
            "strresponsavel",
            "strcargo",
            "flggeradoautomaticamente",
            "strnumero",
            "strreferenciapai",
            "strabaorigem",
            "intlinhaorigem",
        ]
        read_only_fields = AuditableModelSerializer.Meta.read_only_fields + [
            "iditemorganograma",
            "pai_sigla",
            "strreferenciapai",
            "flggeradoautomaticamente",
        ]

    def validate_strnome(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("O nome é obrigatório.")
        return value

    def validate_strsigla(self, value):
        value = value.strip().upper()
        if not value or " " in value:
            raise serializers.ValidationError("Informe uma sigla sem espaços.")
        return value

    def validate(self, attrs):
        importacao = attrs.get("idimportacaoplanilha") or getattr(
            self.instance, "idimportacaoplanilha", None
        )
        if (
            self.instance is not None
            and "idimportacaoplanilha" in attrs
            and attrs["idimportacaoplanilha"].pk
            != self.instance.idimportacaoplanilha_id
        ):
            raise serializers.ValidationError(
                {
                    "idimportacaoplanilha_id": (
                        "Um item existente não pode ser movido para outra importação."
                    )
                }
            )
        if (
            importacao is not None
            and importacao.strstatusimportacao == StatusImportacaoLocal.REJEITADA
        ):
            raise serializers.ValidationError(
                "Os itens de uma importação rejeitada não podem ser alterados."
            )
        pai = attrs.get("idpai")
        if "idpai" not in attrs and self.instance is not None:
            pai = self.instance.idpai
        if pai is not None and importacao is not None:
            if pai.idimportacaoplanilha_id != importacao.pk:
                raise serializers.ValidationError(
                    {"idpai_id": "O pai deve pertencer à mesma importação."}
                )
            if self.instance is not None and pai.pk == self.instance.pk:
                raise serializers.ValidationError(
                    {"idpai_id": "Uma unidade não pode ser pai de si mesma."}
                )
            ancestor = pai
            visited = set()
            while ancestor is not None and ancestor.pk not in visited:
                if self.instance is not None and ancestor.pk == self.instance.pk:
                    raise serializers.ValidationError(
                        {"idpai_id": "A relação informada cria um ciclo hierárquico."}
                    )
                visited.add(ancestor.pk)
                ancestor = ancestor.idpai
        if importacao is not None:
            nome = attrs.get("strnome") or getattr(self.instance, "strnome", "")
            sigla = attrs.get("strsigla") or getattr(self.instance, "strsigla", "")
            items = list(
                ItemOrganograma.objects.filter(idimportacaoplanilha=importacao)
            )
            by_id = {item.pk: item for item in items}
            entity_type = self._entity_type(pai, by_id)
            self._validate_prodest_lengths(nome, sigla, entity_type)
            self._validate_acronym_scope(items, pai, sigla)
        if "idpai" in attrs or self.instance is None:
            attrs["strreferenciapai"] = pai.strsigla if pai is not None else ""
        return attrs

    @staticmethod
    def _entity_type(parent, by_id):
        if parent is None:
            return "root"
        parent = by_id.get(parent.pk, parent)
        if parent.idpai_id is None:
            return "organ"
        return "unit"

    @staticmethod
    def _validate_prodest_lengths(name, acronym, entity_type):
        if entity_type == "root":
            return
        if entity_type == "organ":
            name_maximum = ORGAN_NAME_MAX_LENGTH
            acronym_maximum = ORGAN_ACRONYM_MAX_LENGTH
            entity_name = "órgão"
        else:
            name_maximum = UNIT_NAME_MAX_LENGTH
            acronym_maximum = UNIT_ACRONYM_MAX_LENGTH
            entity_name = "unidade"

        errors = {}
        if len(name) > name_maximum:
            errors["strnome"] = (
                f"O nome do {entity_name} deve ter no máximo "
                f"{name_maximum} caracteres."
            )
        if len(acronym) > acronym_maximum:
            errors["strsigla"] = (
                f"A sigla do {entity_name} deve ter no máximo "
                f"{acronym_maximum} caracteres."
            )
        if errors:
            raise serializers.ValidationError(errors)

    def _validate_acronym_scope(self, items, parent, acronym):
        """Valida a árvore resultante, inclusive quando uma subárvore é movida."""
        current_id = self.instance.pk if self.instance is not None else -1
        parent_by_id = {item.pk: item.idpai_id for item in items}
        acronym_by_id = {item.pk: item.strsigla for item in items}
        parent_by_id[current_id] = parent.pk if parent is not None else None
        acronym_by_id[current_id] = acronym

        roots = [
            item_id
            for item_id, parent_id in parent_by_id.items()
            if parent_id is None
        ]
        if len(roots) != 1:
            return
        root_id = roots[0]

        unit_groups = {}
        for item_id, item_acronym in acronym_by_id.items():
            organ_id = self._owning_organ_id(item_id, parent_by_id, root_id)
            if organ_id is not None and item_acronym:
                unit_groups.setdefault((organ_id, item_acronym), []).append(item_id)

        if any(len(item_ids) > 1 for item_ids in unit_groups.values()):
            raise serializers.ValidationError(
                {
                    "strsigla": (
                        "A sigla da unidade deve ser única dentro do órgão, "
                        "inclusive entre ramos diferentes."
                    )
                }
            )

        if parent is not None and parent.idpai_id is None:
            duplicate_organ = any(
                item_id != current_id
                and parent_by_id.get(item_id) == root_id
                and item_acronym == acronym
                for item_id, item_acronym in acronym_by_id.items()
            )
            if duplicate_organ:
                raise serializers.ValidationError(
                    {"strsigla": "Já existe um órgão com esta sigla."}
                )

    @staticmethod
    def _owning_organ_id(item_id, parent_by_id, root_id):
        parent_id = parent_by_id.get(item_id)
        if parent_id is None or parent_id == root_id:
            return None
        visited = {item_id}
        current_id = parent_id
        while current_id is not None and current_id not in visited:
            if parent_by_id.get(current_id) == root_id:
                return current_id
            visited.add(current_id)
            current_id = parent_by_id.get(current_id)
        return None


class SolicitarEnvioOrganogramaSerializer(serializers.Serializer):
    idimportacaoplanilha_id = serializers.PrimaryKeyRelatedField(
        source="idimportacaoplanilha",
        queryset=ImportacaoPlanilha.objects.filter(
            idtipocarga_id=ORGANOGRAMA_TYPE_ID
        ),
    )
    dry_run = serializers.BooleanField(default=True)

    def validate(self, attrs):
        importacao = attrs["idimportacaoplanilha"]
        if EnvioOrganogramaProdest.objects.filter(
            idimportacaoplanilha__idpatriarca=importacao.idpatriarca,
            strstatus__in=[
                StatusEnvioOrganograma.SOLICITANDO,
                StatusEnvioOrganograma.PROCESSANDO,
            ],
        ).exists():
            raise serializers.ValidationError(
                {
                    "idimportacaoplanilha_id": (
                        "Já existe uma carga inicial em processamento para "
                        "este patriarca. Aguarde sua conclusão."
                    )
                }
            )
        return attrs


class ConsultarCargasIniciaisProdestSerializer(serializers.Serializer):
    patriarca = serializers.PrimaryKeyRelatedField(
        queryset=Patriarca.objects.all(),
    )
    limit = serializers.IntegerField(default=10, min_value=1, max_value=10)


class EnvioOrganogramaProdestSerializer(AuditableModelSerializer):
    idimportacaoplanilha_id = serializers.IntegerField(read_only=True)
    idprocessocargainicial_id = serializers.IntegerField(read_only=True)
    idpatriarca_id = serializers.IntegerField(
        source="idimportacaoplanilha.idpatriarca_id",
        read_only=True,
    )
    patriarca_nome = serializers.CharField(
        source="idimportacaoplanilha.idpatriarca.strnome",
        read_only=True,
    )
    importacao_referencia = serializers.CharField(
        source="idimportacaoplanilha.strreferencia",
        read_only=True,
    )
    modo = serializers.SerializerMethodField()
    status_nome = serializers.CharField(
        source="get_strstatus_display",
        read_only=True,
    )
    finalizada_prodest = serializers.SerializerMethodField()
    relatorio_disponivel = serializers.SerializerMethodField()
    etapas_prodest = serializers.SerializerMethodField()
    fase_atual_nome = serializers.CharField(
        source="get_strfaseatual_display", read_only=True
    )
    fase_atual = serializers.CharField(source="strfaseatual", read_only=True)
    status_atual = serializers.CharField(
        source="strstatusoperacional", read_only=True
    )
    status_atual_nome = serializers.CharField(
        source="get_strstatusoperacional_display", read_only=True
    )
    mensagem_atual = serializers.CharField(
        source="strmensagematual", read_only=True
    )
    acoes_disponiveis = serializers.SerializerMethodField()
    ultimo_evento_id = serializers.SerializerMethodField()

    class Meta(AuditableModelSerializer.Meta):
        model = EnvioOrganogramaProdest
        fields = AuditableModelSerializer.Meta.fields + [
            "idenvioorganograma",
            "idimportacaoplanilha_id",
            "idprocessocargainicial_id",
            "idpatriarca_id",
            "patriarca_nome",
            "importacao_referencia",
            "flgdryrun",
            "modo",
            "strambiente",
            "idexternocarga",
            "strstatus",
            "status_nome",
            "finalizada_prodest",
            "relatorio_disponivel",
            "etapas_prodest",
            "strhashpayload",
            "jsonstatusprodest",
            "jsonrelatorioprodest",
            "strmensagemerro",
            "strfaseatual",
            "fase_atual",
            "fase_atual_nome",
            "status_atual",
            "status_atual_nome",
            "strmensagematual",
            "mensagem_atual",
            "datultimaatividade",
            "datproximaconsulta",
            "acoes_disponiveis",
            "ultimo_evento_id",
            "datsolicitacao",
            "datultimaconsulta",
            "datfinalizacao",
        ]
        read_only_fields = fields

    def get_modo(self, instance) -> str:
        return "SIMULACAO" if instance.flgdryrun else "DEFINITIVO"

    def get_acoes_disponiveis(self, instance) -> dict:
        active = instance.strstatus in {
            StatusEnvioOrganograma.SOLICITANDO,
            StatusEnvioOrganograma.PROCESSANDO,
        }
        return {
            "consultar_detalhes": True,
            "consultar_status": bool(instance.idexternocarga and active),
            "consultar_relatorio": bool(
                instance.idexternocarga and instance.jsonstatusprodest.get("finalizada")
            ),
            "tentar_novamente": instance.strstatus == StatusEnvioOrganograma.ERRO,
        }

    def get_ultimo_evento_id(self, instance) -> int | None:
        event = instance.eventos_integracao_prodest.filter(
            strvisibilidade="OPERACIONAL"
        ).first()
        return event.pk if event else None

    def get_finalizada_prodest(self, instance) -> bool:
        return bool(instance.jsonstatusprodest.get("finalizada"))

    def get_relatorio_disponivel(self, instance) -> bool:
        return bool(instance.jsonrelatorioprodest)

    def get_etapas_prodest(self, instance) -> list[dict]:
        stage_names = {
            1: "Análise inicial",
            2: "Validação",
            3: "Organograma",
            4: "Lotação",
            5: "Relatório",
            6: "Acesso Cidadão legado",
        }
        status_names = {
            1: "Pendente",
            2: "Em processamento",
            3: "Finalizada",
            4: "Erro",
            5: "Ignorada",
        }
        result = []
        for stage in instance.jsonstatusprodest.get("etapas", []):
            if not isinstance(stage, dict):
                continue
            item = dict(stage)
            try:
                stage_code = int(item.get("etapa"))
            except (TypeError, ValueError):
                stage_code = None
            try:
                status_code = int(item.get("status"))
            except (TypeError, ValueError):
                status_code = None
            item["etapa_nome"] = stage_names.get(stage_code, "Desconhecida")
            item["status_nome"] = status_names.get(status_code, "Desconhecido")
            result.append(item)
        return result
