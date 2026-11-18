"""Schema OpenAPI exclusivo da projeção pública."""

from rest_framework import serializers


class SerializadorErroPublico(serializers.Serializer):
    codigo = serializers.CharField()
    detalhe = serializers.CharField()


class SerializadorResumoPublicacaoPublica(serializers.Serializer):
    id = serializers.UUIDField()
    versao = serializers.IntegerField()
    titulo = serializers.CharField()
    competencia = serializers.CharField()
    publicada_em = serializers.DateTimeField()


class SerializadorPontoSeriePublica(serializers.Serializer):
    competencia = serializers.CharField()
    valor = serializers.CharField(allow_null=True)
    valor_acumulado = serializers.CharField(allow_null=True)
    proveniencia = serializers.DictField()


class SerializadorSeriePublica(serializers.Serializer):
    codigo = serializers.CharField()
    titulo = serializers.CharField()
    periodicidade = serializers.CharField()
    natureza = serializers.CharField()
    unidade = serializers.CharField(allow_null=True)
    precisao = serializers.IntegerField(allow_null=True)
    serie_completa = serializers.BooleanField()
    pontos = SerializadorPontoSeriePublica(many=True)


class SerializadorSecaoPublica(serializers.Serializer):
    ordem = serializers.IntegerField()
    codigo = serializers.CharField(allow_null=True)
    titulo = serializers.CharField()
    fonte = serializers.CharField()
    perfil_calculo = serializers.CharField()
    conteudo = serializers.DictField()


class SerializadorPublicacaoPublica(SerializadorResumoPublicacaoPublica):
    schema_version = serializers.CharField()
    secoes = SerializadorSecaoPublica(many=True)


class SerializadorSecaoSeriesPublicas(serializers.Serializer):
    ordem = serializers.IntegerField()
    codigo = serializers.CharField(allow_null=True)
    titulo = serializers.CharField()
    fonte = serializers.CharField()
    series_historicas = SerializadorSeriePublica(many=True)


class SerializadorSeriesPublicacaoPublica(SerializadorResumoPublicacaoPublica):
    schema_version = serializers.CharField()
    secoes = SerializadorSecaoSeriesPublicas(many=True)


class SerializadorHistoricoPublico(serializers.Serializer):
    schema_version = serializers.CharField()
    quantidade = serializers.IntegerField()
    resultados = SerializadorResumoPublicacaoPublica(many=True)
