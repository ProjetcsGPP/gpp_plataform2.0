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
from django.db.models import Count, Max, OuterRef, Subquery, Sum
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
from apps.pub_institucional.services.calculos_edocs import (
    VERSAO_CALCULO_EDOCS, calcular_indicadores_edocs)
from apps.pub_institucional.services.cliente_edocs import (ClienteEdocs,
                                                           ErroEdocs)
from apps.pub_institucional.services.patriarcas_edocs import (
    AtorAuditoriaEdocs, sincronizar_patriarcas_edocs)
from apps.pub_institucional.services.implantacao_edocs import (
    registrar_implantacoes_observadas)

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


def _agendar_processamento(coleta_id) -> None:
    transaction.on_commit(
        lambda: signature(
            "pub_institucional.processar_coleta_mensal_edocs",
            args=(str(coleta_id),),
        ).delay()
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
            SituacaoColetaMensalEdocs.SOLICITADA,
            SituacaoColetaMensalEdocs.EXECUTANDO,
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
        _agendar_processamento(coleta.pk)
    publicar_evento_edocs("edocs.mensal.coleta.solicitada", _resumo(coleta))
    return coleta


@transaction.atomic
def reencaminhar_coleta_mensal_edocs(
    coleta_id,
    *,
    ator: AtorAuditoriaEdocs | None = None,
) -> ColetaMensalEdocs:
    """Reenvia uma solicitação que ainda não começou, sem criar nova revisão."""

    coleta = ColetaMensalEdocs.objects.select_for_update().select_related(
        "competencia"
    ).get(pk=coleta_id)
    if coleta.situacao != SituacaoColetaMensalEdocs.SOLICITADA:
        raise ErroColetaMensalEdocs(
            "Somente uma coleta ainda solicitada pode ser reencaminhada."
        )
    ator = ator or AtorAuditoriaEdocs(nome="recuperacao_automatica")
    coleta.atualizado_por_id = ator.usuario_id
    coleta.atualizado_por_nome = ator.nome
    coleta.save(
        update_fields=(
            "atualizado_por_id",
            "atualizado_por_nome",
            "atualizado_em",
        )
    )
    _criar_evento(
        coleta,
        ator,
        TipoEventoColetaMensalEdocs.REENCAMINHADA,
        "Solicitação mensal E-Docs reencaminhada para processamento.",
    )
    _agendar_processamento(coleta.pk)
    publicar_evento_edocs("edocs.mensal.coleta.reencaminhada", _resumo(coleta))
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
            _criar_resultado_patriarca(
                coleta,
                patriarca,
                dado_processos,
                dado_documentos,
                ator,
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


def _criar_resultado_patriarca(
    coleta,
    patriarca,
    dado_processos,
    dado_documentos,
    ator,
):
    total_processos = dado_processos.get("totalProcessos")
    total_paginas = dado_documentos.get("totalPaginas")
    indicadores = calcular_indicadores_edocs(
        total_paginas=total_paginas,
        total_processos=total_processos,
    )
    return ResultadoMensalPatriarcaEdocs(
        coleta=coleta,
        patriarca=patriarca,
        id_patriarca_externo=patriarca.id_externo,
        sigla_patriarca=patriarca.sigla,
        nome_patriarca=patriarca.nome,
        codigo_municipio=patriarca.codigo_municipio,
        total_processos=total_processos,
        total_documentos=dado_documentos.get("totalDocumentos"),
        total_paginas=total_paginas,
        **indicadores.__dict__,
        **_auditoria(ator),
    )


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
        if coleta.situacao != SituacaoColetaMensalEdocs.SOLICITADA:
            return coleta
        coleta.situacao = SituacaoColetaMensalEdocs.EXECUTANDO
        coleta.iniciada_em = timezone.now()
        coleta.save(update_fields=("situacao", "iniciada_em", "atualizado_em"))
        ator = AtorAuditoriaEdocs(
            coleta.criado_por_id,
            coleta.criado_por_nome or "sistema",
        )
        _criar_evento(
            coleta,
            ator,
            TipoEventoColetaMensalEdocs.EXECUCAO_INICIADA,
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
    coleta.situacao = SituacaoColetaMensalEdocs.SUCESSO
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
                "versao_calculo": item.versao_calculo,
                "economia_papel_kg": str(item.economia_papel_kg),
                "gases_poluentes_kg": str(item.gases_poluentes_kg),
                "economia_papel_reais": str(item.economia_papel_reais),
                "economia_insumos_reais": str(item.economia_insumos_reais),
                "economia_impressao_reais": str(item.economia_impressao_reais),
                "economia_total_reais": str(item.economia_total_reais),
                "economia_agua_m3": str(item.economia_agua_m3),
                "arvores_salvas": str(item.arvores_salvas),
            }
            for item in resultados_patriarcas
        ]
    )
    coleta.save()
    registrar_implantacoes_observadas(
        coleta,
        resultados_patriarcas,
        ator=ator,
    )
    _criar_evento(
        coleta,
        ator,
        TipoEventoColetaMensalEdocs.SUCESSO,
        "Coleta mensal E-Docs concluída.",
        _resumo(coleta),
    )
    publicar_evento_edocs("edocs.mensal.coleta.concluida", _resumo(coleta))


@transaction.atomic
def _marcar_falha(coleta, ator, codigo, mensagem):
    coleta = ColetaMensalEdocs.objects.select_for_update().get(pk=coleta.pk)
    coleta.situacao = SituacaoColetaMensalEdocs.ERRO
    coleta.concluida_em = timezone.now()
    coleta.quantidade_fontes_brutas = coleta.fontes_brutas.count()
    coleta.codigo_erro = codigo[:80]
    coleta.mensagem_erro = mensagem[:500]
    coleta.save()
    _criar_evento(
        coleta,
        ator,
        TipoEventoColetaMensalEdocs.ERRO,
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
        "versao_calculo": VERSAO_CALCULO_EDOCS,
    }


def _somar_resultados(resultados, **contagens) -> dict:
    totais = resultados.aggregate(
        **contagens,
        total_processos=Sum("total_processos"),
        total_documentos=Sum("total_documentos"),
        total_paginas=Sum("total_paginas"),
        economia_papel_kg=Sum("economia_papel_kg"),
        gases_poluentes_kg=Sum("gases_poluentes_kg"),
        economia_papel_reais=Sum("economia_papel_reais"),
        economia_insumos_reais=Sum("economia_insumos_reais"),
        economia_impressao_reais=Sum("economia_impressao_reais"),
        economia_total_reais=Sum("economia_total_reais"),
        economia_agua_m3=Sum("economia_agua_m3"),
        arvores_salvas=Sum("arvores_salvas"),
    )
    campos_numericos = (
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
    for campo in campos_numericos:
        if totais[campo] is None:
            totais[campo] = 0
    return totais


def obter_totais_resultados_mensais_edocs(coleta_id) -> dict:
    """Soma todos os resultados da revisao sem depender da pagina da API."""

    resultados = ResultadoMensalPatriarcaEdocs.objects.filter(
        coleta_id=coleta_id
    )
    totais = _somar_resultados(
        resultados,
        quantidade_municipios=Count("id"),
    )
    totais.update(
        coleta_id=coleta_id,
        versao_calculo=(
            resultados.values_list("versao_calculo", flat=True).first()
            or VERSAO_CALCULO_EDOCS
        ),
    )
    return totais


def obter_totais_historicos_edocs(
    *,
    ano: int | None = None,
    patriarca_id: int | None = None,
) -> dict:
    """Consolida a ultima revisao bem-sucedida de cada competencia."""

    ultima_coleta_sucesso = (
        ColetaMensalEdocs.objects.filter(
            competencia_id=OuterRef("coleta__competencia_id"),
            situacao=SituacaoColetaMensalEdocs.SUCESSO,
        )
        .order_by("-revisao")
        .values("pk")[:1]
    )
    resultados = ResultadoMensalPatriarcaEdocs.objects.filter(
        coleta_id=Subquery(ultima_coleta_sucesso)
    )
    if ano is not None:
        resultados = resultados.filter(coleta__competencia__ano=ano)
    patriarca = None
    if patriarca_id is not None:
        resultados = resultados.filter(patriarca_id=patriarca_id)
        patriarca = PatriarcaEdocs.objects.filter(pk=patriarca_id).first()

    totais = _somar_resultados(
        resultados,
        quantidade_competencias=Count(
            "coleta__competencia_id",
            distinct=True,
        ),
        quantidade_municipios=Count("patriarca_id", distinct=True),
    )
    totais.update(
        ano=ano,
        patriarca_id=patriarca_id,
        codigo_municipio=patriarca.codigo_municipio if patriarca else None,
        nome_municipio=patriarca.nome if patriarca else None,
        versoes_calculo=list(
            resultados.order_by()
            .values_list("versao_calculo", flat=True)
            .distinct()
        ),
    )
    return totais
