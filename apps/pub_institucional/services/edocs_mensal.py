"""Orquestra a série histórica mensal dos relatórios quantitativos E-Docs."""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from uuid import UUID

from celery import signature
from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Max
from django.utils import timezone

from apps.pub_institucional.edocs_tempo_real import publicar_evento_edocs
from apps.pub_institucional.models import (CodigoFonteMensalEdocs,
                                           ColetaMensalEdocs, CompetenciaEdocs,
                                           EventoAuditoriaColetaMensalEdocs,
                                           FonteBrutaColetaMensalEdocs,
                                           PatriarcaEdocs,
                                           ResultadoMensalOrganizacaoEdocs,
                                           ResultadoMensalPatriarcaEdocs,
                                           SituacaoColetaMensalEdocs,
                                           SituacaoColetaPatriarcas,
                                           TipoEventoColetaMensalEdocs)
from apps.pub_institucional.services.cliente_edocs import (ClienteEdocs,
                                                           ErroEdocs)
from apps.pub_institucional.services.patriarcas_edocs import (
    AtorAuditoriaEdocs, sincronizar_patriarcas_edocs)

logger = logging.getLogger(__name__)


class ErroColetaMensalEdocs(ValueError):
    """A coleta não pode ser solicitada ou processada com segurança."""


@dataclass(frozen=True)
class _RespostaFonte:
    codigo: str
    conteudo: list[dict]
    patriarca: PatriarcaEdocs | None = None


def _auditoria(ator: AtorAuditoriaEdocs) -> dict:
    return {
        "criado_por_id": ator.usuario_id,
        "criado_por_nome": ator.nome,
        "atualizado_por_id": ator.usuario_id,
        "atualizado_por_nome": ator.nome,
    }


def _hash_canonico(valor) -> str:
    conteudo = json.dumps(
        valor,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(conteudo).hexdigest()


def _validar_competencia(ano: int, mes: int) -> None:
    if isinstance(ano, bool) or not isinstance(ano, int) or not 2000 <= ano <= 9999:
        raise ErroColetaMensalEdocs("Informe um ano válido entre 2000 e 9999.")
    if isinstance(mes, bool) or not isinstance(mes, int) or not 1 <= mes <= 12:
        raise ErroColetaMensalEdocs("Informe um mês válido entre 1 e 12.")


def _criar_evento(coleta, ator, tipo_evento, mensagem, metadados=None):
    return EventoAuditoriaColetaMensalEdocs.objects.create(
        coleta=coleta,
        tipo_evento=tipo_evento,
        mensagem=mensagem,
        metadados=metadados or {},
        **_auditoria(ator),
    )


@transaction.atomic
def solicitar_coleta_mensal_edocs(
    *,
    ano: int,
    mes: int,
    ator: AtorAuditoriaEdocs | None = None,
    agendar: bool = True,
) -> ColetaMensalEdocs:
    """Cria uma revisão e congela a seleção vigente de patriarcas."""

    _validar_competencia(ano, mes)
    ator = ator or AtorAuditoriaEdocs()
    competencia, _ = CompetenciaEdocs.objects.get_or_create(
        ano=ano,
        mes=mes,
        defaults=_auditoria(ator),
    )
    competencia = CompetenciaEdocs.objects.select_for_update().get(
        pk=competencia.pk
    )
    if competencia.coletas.filter(
        situacao__in=(
            SituacaoColetaMensalEdocs.AGENDADA,
            SituacaoColetaMensalEdocs.EM_EXECUCAO,
        )
    ).exists():
        raise ErroColetaMensalEdocs(
            "Já existe uma coleta ativa para esta competência."
        )

    patriarcas = list(
        PatriarcaEdocs.objects.filter(ativo=True, coletar_detalhes=True)
        .order_by("id_externo")
        .values("id", "id_externo", "sigla", "nome")
    )
    if not patriarcas:
        raise ErroColetaMensalEdocs(
            "Nenhum patriarca ativo foi selecionado para a coleta detalhada."
        )
    retrato = [
        {
            "id": item["id"],
            "id_externo": str(item["id_externo"]),
            "sigla": item["sigla"],
            "nome": item["nome"],
        }
        for item in patriarcas
    ]
    revisao = (
        competencia.coletas.aggregate(maior=Max("revisao"))["maior"] or 0
    ) + 1
    try:
        coleta = ColetaMensalEdocs.objects.create(
            competencia=competencia,
            revisao=revisao,
            ambiente=settings.GPP_EDOCS_ENVIRONMENT,
            patriarcas_solicitados=retrato,
            **_auditoria(ator),
        )
    except IntegrityError as exc:
        raise ErroColetaMensalEdocs(
            "Não foi possível criar uma revisão concorrente para a competência."
        ) from exc
    _criar_evento(
        coleta,
        ator,
        TipoEventoColetaMensalEdocs.SOLICITADA,
        "Coleta mensal E-Docs solicitada.",
        {"ano": ano, "mes": mes, "revisao": revisao},
    )
    if agendar:
        transaction.on_commit(
            lambda: signature(
                "pub_institucional.processar_coleta_mensal_edocs",
                args=(str(coleta.pk),),
            ).delay()
        )
    publicar_evento_edocs("edocs.mensal.coleta.solicitada", _resumo(coleta))
    return coleta


class _ClienteCatalogoObtido:
    def __init__(self, conteudo):
        self.conteudo = conteudo

    def listar_patriarcas(self):
        return self.conteudo


def _persistir_fonte(coleta, resposta: _RespostaFonte, ator):
    return FonteBrutaColetaMensalEdocs.objects.create(
        coleta=coleta,
        codigo_fonte=resposta.codigo,
        patriarca=resposta.patriarca,
        id_patriarca_externo=(
            resposta.patriarca.id_externo if resposta.patriarca else None
        ),
        conteudo=resposta.conteudo,
        hash_sha256=_hash_canonico(resposta.conteudo),
        **_auditoria(ator),
    )


def _obter_uuid(registro, campo, contexto):
    try:
        return UUID(str(registro[campo]))
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise ErroColetaMensalEdocs(
            f"O E-Docs retornou {campo} inválido em {contexto}."
        ) from exc


def _obter_total(registro, campo, contexto):
    valor = registro.get(campo)
    if isinstance(valor, bool) or not isinstance(valor, int) or valor < 0:
        raise ErroColetaMensalEdocs(
            f"O E-Docs retornou {campo} inválido em {contexto}."
        )
    return valor


def _indexar_patriarcas(registros, campos_totais, contexto):
    indice = {}
    for registro in registros:
        identificador = _obter_uuid(registro, "idPatriarca", contexto)
        if identificador in indice:
            raise ErroColetaMensalEdocs(
                f"O E-Docs duplicou idPatriarca em {contexto}."
            )
        indice[identificador] = {
            campo: _obter_total(registro, campo, contexto)
            for campo in campos_totais
        }
    return indice


def _indexar_organizacoes(registros, campos_totais, contexto):
    indice = {}
    for registro in registros:
        id_patriarca = _obter_uuid(registro, "idPatriarca", contexto)
        id_organizacao = _obter_uuid(registro, "idOrganizacao", contexto)
        chave = (id_patriarca, id_organizacao)
        if chave in indice:
            raise ErroColetaMensalEdocs(
                f"O E-Docs duplicou uma organização em {contexto}."
            )
        nome = registro.get("nomeOrganizacao")
        if not isinstance(nome, str) or not nome.strip() or len(nome.strip()) > 300:
            raise ErroColetaMensalEdocs(
                f"O E-Docs retornou nomeOrganizacao inválido em {contexto}."
            )
        indice[chave] = {
            "nome_organizacao": nome.strip(),
            **{
                campo: _obter_total(registro, campo, contexto)
                for campo in campos_totais
            },
        }
    return indice


def _normalizar_resultados(coleta, fontes, patriarcas, ator):
    processos = _indexar_patriarcas(
        fontes[CodigoFonteMensalEdocs.EDOC_01],
        ("totalProcessos",),
        CodigoFonteMensalEdocs.EDOC_01,
    )
    documentos = _indexar_patriarcas(
        fontes[CodigoFonteMensalEdocs.EDOC_03],
        ("totalDocumentos", "totalPaginas"),
        CodigoFonteMensalEdocs.EDOC_03,
    )
    resultados_patriarcas = []
    resultados_organizacoes = []
    for patriarca in patriarcas:
        identificador = patriarca.id_externo
        dado_processos = processos.get(identificador, {})
        dado_documentos = documentos.get(identificador, {})
        resultados_patriarcas.append(
            ResultadoMensalPatriarcaEdocs(
                coleta=coleta,
                patriarca=patriarca,
                id_patriarca_externo=identificador,
                sigla_patriarca=patriarca.sigla,
                nome_patriarca=patriarca.nome,
                codigo_municipio=patriarca.codigo_municipio,
                total_processos=dado_processos.get("totalProcessos"),
                total_documentos=dado_documentos.get("totalDocumentos"),
                total_paginas=dado_documentos.get("totalPaginas"),
                **_auditoria(ator),
            )
        )
        processos_org = _indexar_organizacoes(
            fontes[(CodigoFonteMensalEdocs.EDOC_02, identificador)],
            ("totalProcessos",),
            f"{CodigoFonteMensalEdocs.EDOC_02}/{identificador}",
        )
        documentos_org = _indexar_organizacoes(
            fontes[(CodigoFonteMensalEdocs.EDOC_04, identificador)],
            ("totalDocumentos", "totalPaginas"),
            f"{CodigoFonteMensalEdocs.EDOC_04}/{identificador}",
        )
        for chave in sorted(set(processos_org) | set(documentos_org), key=str):
            dado_proc = processos_org.get(chave, {})
            dado_doc = documentos_org.get(chave, {})
            nome = dado_doc.get("nome_organizacao") or dado_proc.get(
                "nome_organizacao"
            )
            resultados_organizacoes.append(
                ResultadoMensalOrganizacaoEdocs(
                    coleta=coleta,
                    patriarca=patriarca,
                    id_patriarca_externo=identificador,
                    nome_patriarca=patriarca.nome,
                    id_organizacao_externo=chave[1],
                    nome_organizacao=nome,
                    total_processos=dado_proc.get("totalProcessos"),
                    total_documentos=dado_doc.get("totalDocumentos"),
                    total_paginas=dado_doc.get("totalPaginas"),
                    **_auditoria(ator),
                )
            )
    return resultados_patriarcas, resultados_organizacoes


def executar_coleta_mensal_edocs(  # pylint: disable=too-many-locals
    coleta_id,
    *,
    cliente: ClienteEdocs | None = None,
) -> ColetaMensalEdocs:
    """Executa uma revisão agendada e mantém evidências mesmo em falha."""

    with transaction.atomic():
        coleta = ColetaMensalEdocs.objects.select_for_update().select_related(
            "competencia"
        ).get(pk=coleta_id)
        if coleta.situacao != SituacaoColetaMensalEdocs.AGENDADA:
            return coleta
        coleta.situacao = SituacaoColetaMensalEdocs.EM_EXECUCAO
        coleta.iniciada_em = timezone.now()
        coleta.save(update_fields=("situacao", "iniciada_em", "atualizado_em"))
        ator = AtorAuditoriaEdocs(
            coleta.criado_por_id,
            coleta.criado_por_nome or "sistema",
        )
        _criar_evento(
            coleta,
            ator,
            TipoEventoColetaMensalEdocs.INICIADA,
            "Coleta mensal E-Docs iniciada.",
        )

    fontes = {}
    try:
        api = cliente or ClienteEdocs()
        mes = f"{coleta.competencia.mes:02d}"
        ano = coleta.competencia.ano
        ids_banco = [item["id"] for item in coleta.patriarcas_solicitados]
        patriarcas = list(PatriarcaEdocs.objects.filter(pk__in=ids_banco))
        if len(patriarcas) != len(ids_banco):
            raise ErroColetaMensalEdocs(
                "A seleção congelada contém patriarca indisponível no cadastro."
            )
        catalogo = api.listar_patriarcas()
        _persistir_fonte(
            coleta,
            _RespostaFonte(CodigoFonteMensalEdocs.EDOC_05, catalogo),
            ator,
        )
        comparacao = sincronizar_patriarcas_edocs(
            ator=ator,
            cliente=_ClienteCatalogoObtido(catalogo),
        )
        if comparacao.situacao == SituacaoColetaPatriarcas.FALHOU:
            raise ErroColetaMensalEdocs(
                "A validação do catálogo de patriarcas falhou."
            )
        ids_catalogo = {str(item.get("id")) for item in catalogo}
        ausentes = [
            str(item.id_externo)
            for item in patriarcas
            if str(item.id_externo) not in ids_catalogo
        ]
        if ausentes:
            raise ErroColetaMensalEdocs(
                "Há patriarca selecionado ausente no catálogo atual do E-Docs."
            )

        fontes[CodigoFonteMensalEdocs.EDOC_01] = api.relatorio_processos(mes, ano)
        _persistir_fonte(
            coleta,
            _RespostaFonte(
                CodigoFonteMensalEdocs.EDOC_01,
                fontes[CodigoFonteMensalEdocs.EDOC_01],
            ),
            ator,
        )
        fontes[CodigoFonteMensalEdocs.EDOC_03] = api.relatorio_documentos(mes, ano)
        _persistir_fonte(
            coleta,
            _RespostaFonte(
                CodigoFonteMensalEdocs.EDOC_03,
                fontes[CodigoFonteMensalEdocs.EDOC_03],
            ),
            ator,
        )
        for patriarca in patriarcas:
            identificador = patriarca.id_externo
            processos = api.relatorio_processos_por_patriarca(
                identificador, mes, ano
            )
            documentos = api.relatorio_documentos_por_patriarca(
                identificador, mes, ano
            )
            fontes[(CodigoFonteMensalEdocs.EDOC_02, identificador)] = processos
            fontes[(CodigoFonteMensalEdocs.EDOC_04, identificador)] = documentos
            _persistir_fonte(
                coleta,
                _RespostaFonte(CodigoFonteMensalEdocs.EDOC_02, processos, patriarca),
                ator,
            )
            _persistir_fonte(
                coleta,
                _RespostaFonte(CodigoFonteMensalEdocs.EDOC_04, documentos, patriarca),
                ator,
            )
        resultados_patriarcas, resultados_organizacoes = _normalizar_resultados(
            coleta, fontes, patriarcas, ator
        )
        _concluir_coleta(
            coleta,
            ator,
            resultados_patriarcas,
            resultados_organizacoes,
        )
    except (ErroEdocs, ErroColetaMensalEdocs) as exc:
        _marcar_falha(coleta, ator, exc.__class__.__name__, str(exc))
    except Exception:
        logger.exception("Falha interna na coleta mensal E-Docs %s", coleta.pk)
        _marcar_falha(
            coleta,
            ator,
            "ErroInternoColetaMensalEdocs",
            "A coleta falhou durante o processamento interno.",
        )
    return ColetaMensalEdocs.objects.get(pk=coleta.pk)


@transaction.atomic
def _concluir_coleta(coleta, ator, resultados_patriarcas, resultados_organizacoes):
    coleta = ColetaMensalEdocs.objects.select_for_update().get(pk=coleta.pk)
    ResultadoMensalPatriarcaEdocs.objects.bulk_create(resultados_patriarcas)
    ResultadoMensalOrganizacaoEdocs.objects.bulk_create(resultados_organizacoes)
    coleta.situacao = SituacaoColetaMensalEdocs.CONCLUIDA
    coleta.concluida_em = timezone.now()
    coleta.quantidade_patriarcas = len(resultados_patriarcas)
    coleta.quantidade_organizacoes = len(resultados_organizacoes)
    coleta.quantidade_fontes_brutas = coleta.fontes_brutas.count()
    coleta.hash_resultado = _hash_canonico(
        [
            {
                "id_patriarca": str(item.id_patriarca_externo),
                "processos": item.total_processos,
                "documentos": item.total_documentos,
                "paginas": item.total_paginas,
            }
            for item in resultados_patriarcas
        ]
    )
    coleta.save()
    _criar_evento(
        coleta,
        ator,
        TipoEventoColetaMensalEdocs.CONCLUIDA,
        "Coleta mensal E-Docs concluída.",
        _resumo(coleta),
    )
    publicar_evento_edocs("edocs.mensal.coleta.concluida", _resumo(coleta))


@transaction.atomic
def _marcar_falha(coleta, ator, codigo, mensagem):
    coleta = ColetaMensalEdocs.objects.select_for_update().get(pk=coleta.pk)
    coleta.situacao = SituacaoColetaMensalEdocs.FALHOU
    coleta.concluida_em = timezone.now()
    coleta.quantidade_fontes_brutas = coleta.fontes_brutas.count()
    coleta.codigo_erro = codigo[:80]
    coleta.mensagem_erro = mensagem[:500]
    coleta.save()
    _criar_evento(
        coleta,
        ator,
        TipoEventoColetaMensalEdocs.FALHOU,
        "Coleta mensal E-Docs falhou.",
        {"codigo_erro": coleta.codigo_erro},
    )
    publicar_evento_edocs("edocs.mensal.coleta.falhou", _resumo(coleta))
    return coleta


def _resumo(coleta):
    return {
        "coleta_id": str(coleta.pk),
        "ano": coleta.competencia.ano,
        "mes": coleta.competencia.mes,
        "revisao": coleta.revisao,
        "situacao": coleta.situacao,
        "quantidade_patriarcas": coleta.quantidade_patriarcas,
        "quantidade_organizacoes": coleta.quantidade_organizacoes,
        "quantidade_fontes_brutas": coleta.quantidade_fontes_brutas,
    }
