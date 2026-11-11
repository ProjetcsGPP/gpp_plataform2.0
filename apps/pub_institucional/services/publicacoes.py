"""Serviços transacionais do workflow editorial de publicações."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.pub_institucional.models import (
    ColetaEflow,
    ColetaMensalEdocs,
    ConfiguracaoVisaoPublicacao,
    EscopoVisaoPublicacao,
    FonteVisaoPublicacao,
    HistoricoPublicacao,
    PerfilCalculoEflow,
    Publicacao,
    ResultadoMensalPatriarcaEdocs,
    SecaoPublicacao,
    SituacaoColetaEflow,
    SituacaoColetaMensalEdocs,
    SituacaoPublicacao,
    TipoEventoPublicacao,
)
from apps.pub_institucional.services.eflow import (
    calcular_indicadores_eflow_filtrados,
)


class ErroPublicacao(ValueError):
    """Operação editorial incompatível com o estado persistido."""

    def __init__(self, codigo: str, mensagem: str):
        super().__init__(mensagem)
        self.codigo = codigo


@dataclass(frozen=True)
class AtorAuditoriaPublicacao:
    usuario_id: int | None = None
    nome: str = "sistema"


def _auditoria(ator: AtorAuditoriaPublicacao) -> dict:
    return {
        "criado_por_id": ator.usuario_id,
        "criado_por_nome": ator.nome,
        "atualizado_por_id": ator.usuario_id,
        "atualizado_por_nome": ator.nome,
    }


def _atualizacao(ator: AtorAuditoriaPublicacao) -> dict:
    return {
        "atualizado_por_id": ator.usuario_id,
        "atualizado_por_nome": ator.nome,
    }


def _jsonificavel(valor):
    if isinstance(valor, Decimal):
        return str(valor)
    if isinstance(valor, dict):
        return {chave: _jsonificavel(item) for chave, item in valor.items()}
    if isinstance(valor, (list, tuple)):
        return [_jsonificavel(item) for item in valor]
    return valor


def _hash(valor) -> str:
    bruto = json.dumps(
        _jsonificavel(valor),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(bruto).hexdigest()


def _evento(
    publicacao,
    ator,
    tipo,
    anterior,
    atual,
    *,
    justificativa="",
    metadados=None,
):
    return HistoricoPublicacao.objects.create(
        publicacao=publicacao,
        tipo_evento=tipo,
        situacao_anterior=anterior,
        situacao_atual=atual,
        justificativa=justificativa,
        metadados=metadados or {},
        **_auditoria(ator),
    )


def _validar_competencia(ano: int, mes: int):
    if ano < 2024:
        raise ErroPublicacao(
            "ANO_REFERENCIA_INVALIDO",
            "O ano de referência deve ser igual ou posterior a 2024.",
        )
    if mes not in range(1, 13):
        raise ErroPublicacao(
            "MES_REFERENCIA_INVALIDO",
            "O mês de referência deve estar entre 1 e 12.",
        )


@transaction.atomic
def criar_publicacao(*, titulo: str, ano: int, mes: int, ator):
    _validar_competencia(ano, mes)
    publicacao = Publicacao.objects.create(
        titulo=titulo.strip(),
        ano_referencia=ano,
        mes_referencia=mes,
        **_auditoria(ator),
    )
    _evento(
        publicacao,
        ator,
        TipoEventoPublicacao.CRIADA,
        "",
        SituacaoPublicacao.RASCUNHO,
        metadados={"ano_referencia": ano, "mes_referencia": mes},
    )
    return publicacao


def _ids_patriarcas(configuracao):
    if configuracao.escopo == EscopoVisaoPublicacao.TODOS:
        return None
    if configuracao.escopo == EscopoVisaoPublicacao.MUNICIPIOS:
        from apps.pub_institucional.models import PatriarcaEdocs

        return list(
            PatriarcaEdocs.objects.filter(
                ativo=True,
                codigo_municipio__isnull=False,
            ).values_list("pk", flat=True)
        )
    return list(
        configuracao.selecoes_patriarcas.order_by("patriarca_id").values_list(
            "patriarca_id", flat=True
        )
    )


def selecionar_coleta_edocs(ano: int, mes: int):
    return (
        ColetaMensalEdocs.objects.filter(
            competencia__ano=ano,
            competencia__mes=mes,
            situacao=SituacaoColetaMensalEdocs.SUCESSO,
        )
        .order_by("-revisao")
        .first()
    )


def selecionar_coleta_eflow(ano: int, mes: int):
    return (
        ColetaEflow.objects.filter(situacao=SituacaoColetaEflow.CONCLUIDA)
        .filter(
            Q(ano_vigencia_inicio__lt=ano)
            | Q(ano_vigencia_inicio=ano, mes_vigencia_inicio__lte=mes)
        )
        .order_by("-ano_vigencia_inicio", "-mes_vigencia_inicio", "-concluida_em")
        .first()
    )


@transaction.atomic
def adicionar_secao(
    *,
    publicacao: Publicacao,
    configuracao: ConfiguracaoVisaoPublicacao,
    titulo: str,
    ordem: int,
    ator,
    coleta_id=None,
):
    publicacao = Publicacao.objects.select_for_update().get(pk=publicacao.pk)
    if publicacao.situacao != SituacaoPublicacao.RASCUNHO:
        raise ErroPublicacao(
            "PUBLICACAO_NAO_EDITAVEL",
            "Somente publicações em rascunho aceitam novas seções.",
        )
    if not configuracao.ativa:
        raise ErroPublicacao("VISAO_INATIVA", "A visão selecionada está inativa.")
    if configuracao.fonte == FonteVisaoPublicacao.EDOCS:
        coleta = (
            ColetaMensalEdocs.objects.filter(pk=coleta_id).first()
            if coleta_id
            else selecionar_coleta_edocs(
                publicacao.ano_referencia,
                publicacao.mes_referencia,
            )
        )
        if not coleta or coleta.situacao != SituacaoColetaMensalEdocs.SUCESSO:
            raise ErroPublicacao(
                "COLETA_EDOCS_INDISPONIVEL",
                "Não existe coleta E-Docs bem-sucedida para a competência.",
            )
        if (
            coleta.competencia.ano != publicacao.ano_referencia
            or coleta.competencia.mes != publicacao.mes_referencia
        ):
            raise ErroPublicacao(
                "COMPETENCIA_EDOCS_DIVERGENTE",
                "A coleta E-Docs não pertence à competência da publicação.",
            )
        campos_coleta = {"coleta_edocs": coleta}
        perfil = "PLANILHA_MUNICIPIOS_V1"
    else:
        coleta = (
            ColetaEflow.objects.filter(pk=coleta_id).first()
            if coleta_id
            else selecionar_coleta_eflow(
                publicacao.ano_referencia,
                publicacao.mes_referencia,
            )
        )
        if not coleta or coleta.situacao != SituacaoColetaEflow.CONCLUIDA:
            raise ErroPublicacao(
                "COLETA_EFLOW_INDISPONIVEL",
                "Não existe snapshot E-Flow vigente para a competência.",
            )
        inicio = (coleta.ano_vigencia_inicio, coleta.mes_vigencia_inicio)
        referencia = (publicacao.ano_referencia, publicacao.mes_referencia)
        if inicio > referencia:
            raise ErroPublicacao(
                "VIGENCIA_EFLOW_DIVERGENTE",
                "O snapshot E-Flow ainda não estava vigente na competência.",
            )
        campos_coleta = {"coleta_eflow": coleta}
        perfil = (
            configuracao.perfil_calculo_eflow
            or PerfilCalculoEflow.CONSOLIDADO_PUBLICACAO
        )
        if perfil not in PerfilCalculoEflow.values:
            raise ErroPublicacao(
                "PERFIL_EFLOW_INVALIDO",
                "A visão possui perfil E-Flow inválido.",
            )
    secao = SecaoPublicacao.objects.create(
        publicacao=publicacao,
        ordem=ordem,
        titulo=titulo.strip(),
        fonte=configuracao.fonte,
        configuracao_visao=configuracao,
        perfil_calculo=perfil,
        **campos_coleta,
        **_auditoria(ator),
    )
    publicacao.versao_registro += 1
    for campo, valor in _atualizacao(ator).items():
        setattr(publicacao, campo, valor)
    publicacao.save()
    return secao


def _resultado_edocs(secao, ids_patriarcas):
    consulta = ResultadoMensalPatriarcaEdocs.objects.filter(
        coleta=secao.coleta_edocs
    ).select_related("patriarca")
    if ids_patriarcas is not None:
        consulta = consulta.filter(patriarca_id__in=ids_patriarcas)
    itens = []
    campos_soma = (
        "total_processos",
        "total_documentos",
        "total_paginas",
        "economia_papel_kg",
        "gases_poluentes_kg",
        "economia_papel_reais",
        "economia_insumos_reais",
        "economia_impressao_reais",
        "economia_total_reais",
        "economia_agua_m3",
        "arvores_salvas",
    )
    totais = {campo: Decimal("0") for campo in campos_soma}
    for resultado in consulta.order_by("nome_patriarca"):
        item = {
            "patriarca_id": resultado.patriarca_id,
            "id_patriarca_externo": str(resultado.id_patriarca_externo),
            "codigo_municipio": resultado.codigo_municipio,
            "sigla_patriarca": resultado.sigla_patriarca,
            "nome_patriarca": resultado.nome_patriarca,
            "versao_calculo": resultado.versao_calculo,
        }
        for campo in campos_soma:
            valor = getattr(resultado, campo)
            item[campo] = valor
            totais[campo] += Decimal(valor or 0)
        itens.append(_jsonificavel(item))
    if not itens:
        raise ErroPublicacao(
            "VISAO_SEM_DADOS_EDOCS",
            "A visão não possui dados E-Docs na revisão selecionada.",
        )
    return {
        "quantidade_patriarcas": len(itens),
        "totais": _jsonificavel(totais),
        "patriarcas": itens,
    }


@transaction.atomic
def recalcular_publicacao(publicacao: Publicacao, *, ator):
    publicacao = Publicacao.objects.select_for_update().get(pk=publicacao.pk)
    if publicacao.situacao not in {
        SituacaoPublicacao.RASCUNHO,
        SituacaoPublicacao.EM_VALIDACAO,
    }:
        raise ErroPublicacao(
            "PUBLICACAO_NAO_RECALCULAVEL",
            "A situação atual não permite recalcular a publicação.",
        )
    secoes = list(
        publicacao.secoes.select_related(
            "configuracao_visao", "coleta_edocs", "coleta_eflow"
        )
    )
    if not secoes:
        raise ErroPublicacao(
            "PUBLICACAO_SEM_SECOES",
            "Inclua ao menos uma seção antes de calcular.",
        )
    anterior = publicacao.situacao
    publicacao.situacao = SituacaoPublicacao.EM_VALIDACAO
    publicacao.save(update_fields=("situacao", "atualizado_em"))
    _evento(
        publicacao,
        ator,
        TipoEventoPublicacao.RECALCULADA,
        anterior,
        SituacaoPublicacao.EM_VALIDACAO,
    )
    hashes = []
    for secao in secoes:
        configuracao = secao.configuracao_visao
        ids_patriarcas = _ids_patriarcas(configuracao)
        congelada = {
            "id": str(configuracao.pk),
            "codigo": configuracao.codigo,
            "nome": configuracao.nome,
            "fonte": configuracao.fonte,
            "escopo": configuracao.escopo,
            "versao": configuracao.versao,
            "patriarcas_ids": ids_patriarcas,
            "perfil_calculo": secao.perfil_calculo,
        }
        if secao.fonte == FonteVisaoPublicacao.EDOCS:
            resultado = _resultado_edocs(secao, ids_patriarcas)
        else:
            congelada["snapshot_eflow"] = {
                "coleta_id": str(secao.coleta_eflow_id),
                "ano_vigencia_inicio": secao.coleta_eflow.ano_vigencia_inicio,
                "mes_vigencia_inicio": secao.coleta_eflow.mes_vigencia_inicio,
                "vigencia_retroativa": secao.coleta_eflow.vigencia_retroativa,
            }
            resultado = calcular_indicadores_eflow_filtrados(
                secao.coleta_eflow,
                perfil=secao.perfil_calculo,
                patriarcas_ids=ids_patriarcas,
            )
        secao.configuracao_congelada = congelada
        secao.resultado = _jsonificavel(resultado)
        secao.calculada_em = timezone.now()
        secao.hash_resultado = _hash(
            {"configuracao": congelada, "resultado": secao.resultado}
        )
        for campo, valor in _atualizacao(ator).items():
            setattr(secao, campo, valor)
        secao.save()
        hashes.append(secao.hash_resultado)
    publicacao.situacao = SituacaoPublicacao.AGUARDANDO_PUBLICACAO
    publicacao.versao_registro += 1
    for campo, valor in _atualizacao(ator).items():
        setattr(publicacao, campo, valor)
    publicacao.save()
    _evento(
        publicacao,
        ator,
        TipoEventoPublicacao.VALIDADA,
        SituacaoPublicacao.EM_VALIDACAO,
        publicacao.situacao,
        metadados={"hashes_secoes": hashes},
    )
    return publicacao


@transaction.atomic
def reabrir_publicacao(publicacao: Publicacao, *, ator):
    """Retorna um candidato validado ao rascunho sem apagar sua evidência."""

    publicacao = Publicacao.objects.select_for_update().get(pk=publicacao.pk)
    if publicacao.situacao != SituacaoPublicacao.AGUARDANDO_PUBLICACAO:
        raise ErroPublicacao(
            "PUBLICACAO_NAO_REABRIVEL",
            "Somente uma publicação aguardando publicação pode ser reaberta.",
        )
    anterior = publicacao.situacao
    publicacao.situacao = SituacaoPublicacao.RASCUNHO
    publicacao.versao_registro += 1
    for campo, valor in _atualizacao(ator).items():
        setattr(publicacao, campo, valor)
    publicacao.save()
    _evento(
        publicacao,
        ator,
        TipoEventoPublicacao.ALTERADA,
        anterior,
        SituacaoPublicacao.RASCUNHO,
        metadados={"motivo": "reabertura_para_ajustes"},
    )
    return publicacao


@transaction.atomic
def remover_secao(publicacao: Publicacao, *, secao_id, ator):
    publicacao = Publicacao.objects.select_for_update().get(pk=publicacao.pk)
    if publicacao.situacao != SituacaoPublicacao.RASCUNHO:
        raise ErroPublicacao(
            "PUBLICACAO_NAO_EDITAVEL",
            "Somente publicações em rascunho aceitam remoção de seção.",
        )
    secao = publicacao.secoes.filter(pk=secao_id).first()
    if secao is None:
        raise ErroPublicacao(
            "SECAO_NAO_ENCONTRADA",
            "A seção não pertence à publicação.",
        )
    secao.delete()
    publicacao.versao_registro += 1
    for campo, valor in _atualizacao(ator).items():
        setattr(publicacao, campo, valor)
    publicacao.save()
    _evento(
        publicacao,
        ator,
        TipoEventoPublicacao.ALTERADA,
        SituacaoPublicacao.RASCUNHO,
        SituacaoPublicacao.RASCUNHO,
        metadados={"secao_removida_id": str(secao_id)},
    )
    return publicacao


@transaction.atomic
def publicar_publicacao(publicacao, *, justificativa: str, ator, versao_registro):
    publicacao = Publicacao.objects.select_for_update().get(pk=publicacao.pk)
    if publicacao.versao_registro != versao_registro:
        raise ErroPublicacao(
            "CONCORRENCIA_PUBLICACAO",
            "A publicação foi alterada por outra operação.",
        )
    if publicacao.situacao != SituacaoPublicacao.AGUARDANDO_PUBLICACAO:
        raise ErroPublicacao(
            "PUBLICACAO_NAO_VALIDADA",
            "A publicação deve estar validada antes da publicação.",
        )
    justificativa = justificativa.strip()
    if not justificativa:
        raise ErroPublicacao(
            "JUSTIFICATIVA_OBRIGATORIA",
            "Informe a justificativa da publicação.",
        )
    secoes = list(publicacao.secoes.order_by("ordem"))
    if not secoes or any(not secao.hash_resultado for secao in secoes):
        raise ErroPublicacao(
            "PUBLICACAO_SEM_RESULTADO",
            "Todas as seções devem possuir resultado calculado.",
        )
    anterior = publicacao.situacao
    agora = timezone.now()
    publicacao.situacao = SituacaoPublicacao.PUBLICADA
    publicacao.justificativa_publicacao = justificativa
    publicacao.publicada_em = agora
    publicacao.publicada_por_id = ator.usuario_id
    publicacao.publicada_por_nome = ator.nome
    publicacao.hash_conteudo = _hash(
        {
            "id": str(publicacao.pk),
            "serie_id": str(publicacao.serie_id),
            "versao": publicacao.versao,
            "ano_referencia": publicacao.ano_referencia,
            "mes_referencia": publicacao.mes_referencia,
            "secoes": [secao.hash_resultado for secao in secoes],
        }
    )
    publicacao.versao_registro += 1
    for campo, valor in _atualizacao(ator).items():
        setattr(publicacao, campo, valor)
    if publicacao.publicacao_anterior_id:
        anterior_publicada = Publicacao.objects.select_for_update().get(
            pk=publicacao.publicacao_anterior_id
        )
        if anterior_publicada.situacao != SituacaoPublicacao.PUBLICADA:
            raise ErroPublicacao(
                "VERSAO_ANTERIOR_NAO_VIGENTE",
                "A versão anterior não está mais publicada.",
            )
        anterior_publicada.situacao = SituacaoPublicacao.SUBSTITUIDA
        anterior_publicada.save(update_fields=("situacao", "atualizado_em"))
        _evento(
            anterior_publicada,
            ator,
            TipoEventoPublicacao.SUBSTITUIDA,
            SituacaoPublicacao.PUBLICADA,
            SituacaoPublicacao.SUBSTITUIDA,
            justificativa=justificativa,
            metadados={"substituida_por": str(publicacao.pk)},
        )
    publicacao.save()
    _evento(
        publicacao,
        ator,
        TipoEventoPublicacao.PUBLICADA,
        anterior,
        SituacaoPublicacao.PUBLICADA,
        justificativa=justificativa,
    )
    return publicacao


@transaction.atomic
def iniciar_substituicao(publicacao, *, ator):
    anterior = Publicacao.objects.select_for_update().get(pk=publicacao.pk)
    if anterior.situacao != SituacaoPublicacao.PUBLICADA:
        raise ErroPublicacao(
            "PUBLICACAO_NAO_SUBSTITUIVEL",
            "Somente uma publicação vigente pode iniciar substituição.",
        )
    nova = Publicacao.objects.create(
        serie_id=anterior.serie_id,
        versao=anterior.versao + 1,
        titulo=anterior.titulo,
        ano_referencia=anterior.ano_referencia,
        mes_referencia=anterior.mes_referencia,
        publicacao_anterior=anterior,
        **_auditoria(ator),
    )
    for secao in anterior.secoes.order_by("ordem"):
        SecaoPublicacao.objects.create(
            publicacao=nova,
            ordem=secao.ordem,
            titulo=secao.titulo,
            fonte=secao.fonte,
            configuracao_visao=secao.configuracao_visao,
            coleta_edocs=secao.coleta_edocs,
            coleta_eflow=secao.coleta_eflow,
            perfil_calculo=secao.perfil_calculo,
            **_auditoria(ator),
        )
    _evento(
        nova,
        ator,
        TipoEventoPublicacao.SUBSTITUICAO_INICIADA,
        "",
        SituacaoPublicacao.RASCUNHO,
        metadados={"publicacao_anterior": str(anterior.pk)},
    )
    return nova


@transaction.atomic
def revogar_publicacao(publicacao, *, justificativa: str, ator):
    publicacao = Publicacao.objects.select_for_update().get(pk=publicacao.pk)
    if publicacao.situacao != SituacaoPublicacao.PUBLICADA:
        raise ErroPublicacao(
            "PUBLICACAO_NAO_REVOGAVEL",
            "Somente uma publicação vigente pode ser revogada.",
        )
    justificativa = justificativa.strip()
    if not justificativa:
        raise ErroPublicacao(
            "JUSTIFICATIVA_OBRIGATORIA",
            "Informe a justificativa da revogação.",
        )
    publicacao.situacao = SituacaoPublicacao.REVOGADA
    publicacao.versao_registro += 1
    for campo, valor in _atualizacao(ator).items():
        setattr(publicacao, campo, valor)
    publicacao.save()
    _evento(
        publicacao,
        ator,
        TipoEventoPublicacao.REVOGADA,
        SituacaoPublicacao.PUBLICADA,
        SituacaoPublicacao.REVOGADA,
        justificativa=justificativa,
    )
    return publicacao
