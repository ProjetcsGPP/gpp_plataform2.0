"""Sincronização controlada do catálogo de patriarcas do E-Docs."""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from uuid import UUID

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.pub_institucional.edocs_tempo_real import publicar_evento_edocs
from apps.pub_institucional.models import (ColetaPatriarcasEdocs,
                                           DecisaoDivergenciaPatriarca,
                                           DescricaoTipoAgenteEdocs,
                                           DivergenciaPatriarcaEdocs,
                                           EventoAuditoriaPatriarcaEdocs,
                                           ObservacaoPatriarcaEdocs,
                                           PatriarcaEdocs,
                                           SituacaoColetaPatriarcas,
                                           SituacaoDivergenciaPatriarca,
                                           TipoAgenteEdocs,
                                           TipoComparacaoPatriarca,
                                           TipoEventoAuditoriaPatriarca)
from apps.pub_institucional.services.cliente_edocs import (ClienteEdocs,
                                                           ErroEdocs)

logger = logging.getLogger(__name__)


class ErroValidacaoPatriarcasEdocs(ValueError):
    """O catálogo remoto não atende ao contrato mínimo esperado."""


class ErroDecisaoPatriarcaEdocs(ValueError):
    """A decisão solicitada não é válida para a divergência."""


@dataclass(frozen=True)
class AtorAuditoriaEdocs:
    usuario_id: int | None = None
    nome: str = "sistema"


CAMPOS_REMOTOS = (
    "id_externo",
    "sigla",
    "nome",
    "tipo_agente",
    "descricao_tipo_agente",
)


def _valores_auditoria(ator: AtorAuditoriaEdocs) -> dict:
    return {
        "criado_por_id": ator.usuario_id,
        "criado_por_nome": ator.nome,
        "atualizado_por_id": ator.usuario_id,
        "atualizado_por_nome": ator.nome,
    }


def _valores_atualizacao_auditoria(ator: AtorAuditoriaEdocs) -> dict:
    return {
        "atualizado_por_id": ator.usuario_id,
        "atualizado_por_nome": ator.nome,
    }


def _calcular_hash_canonico(valor) -> str:
    codificado = json.dumps(
        valor,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(codificado).hexdigest()


TIPO_POR_DESCRICAO = {
    DescricaoTipoAgenteEdocs.CIDADAO: TipoAgenteEdocs.CIDADAO,
    DescricaoTipoAgenteEdocs.PAPEL: TipoAgenteEdocs.PAPEL,
    DescricaoTipoAgenteEdocs.GRUPO: TipoAgenteEdocs.GRUPO,
    DescricaoTipoAgenteEdocs.UNIDADE: TipoAgenteEdocs.UNIDADE,
    DescricaoTipoAgenteEdocs.ORGANIZACAO: TipoAgenteEdocs.ORGANIZACAO,
    DescricaoTipoAgenteEdocs.SISTEMA: TipoAgenteEdocs.SISTEMA,
    DescricaoTipoAgenteEdocs.NAO_IDENTIFICADO: TipoAgenteEdocs.NAO_IDENTIFICADO,
}


def _normalizar_registro(registro: dict) -> dict:
    try:
        id_externo = UUID(str(registro["id"]))
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise ErroValidacaoPatriarcasEdocs(
            "O E-Docs retornou patriarca sem identificador UUID válido."
        ) from exc
    nome = registro.get("nome")
    if not isinstance(nome, str) or not nome.strip():
        raise ErroValidacaoPatriarcasEdocs(
            "O E-Docs retornou patriarca sem nome válido."
        )
    tipo_agente = registro.get("tipoAgente")
    descricao_tipo_agente = registro.get("descricaoTipoAgente")
    if (
        not isinstance(tipo_agente, int)
        or isinstance(tipo_agente, bool)
        or tipo_agente not in TipoAgenteEdocs.values
    ):
        raise ErroValidacaoPatriarcasEdocs(
            "O E-Docs retornou código de tipo de agente inválido."
        )
    if descricao_tipo_agente not in DescricaoTipoAgenteEdocs.values:
        raise ErroValidacaoPatriarcasEdocs(
            "O E-Docs retornou descrição de tipo de agente inválida."
        )
    if TIPO_POR_DESCRICAO[descricao_tipo_agente] != tipo_agente:
        raise ErroValidacaoPatriarcasEdocs(
            "O código e a descrição do tipo de agente são divergentes."
        )
    normalizado = {
        "id_externo": id_externo,
        "sigla": str(registro.get("sigla") or "").strip(),
        "nome": nome.strip(),
        "tipo_agente": tipo_agente,
        "descricao_tipo_agente": descricao_tipo_agente,
    }
    limites = {"sigla": 80, "nome": 300, "descricao_tipo_agente": 20}
    if any(
        len(normalizado[campo]) > limite for campo, limite in limites.items()
    ):
        raise ErroValidacaoPatriarcasEdocs(
            "O E-Docs retornou texto acima do limite aceito."
        )
    return normalizado


def _normalizar_catalogo(resposta: list[dict]) -> list[dict]:
    if not resposta:
        raise ErroValidacaoPatriarcasEdocs(
            "O E-Docs retornou um catálogo vazio; a ausência exige validação."
        )
    normalizado = [_normalizar_registro(registro) for registro in resposta]
    identificadores = [registro["id_externo"] for registro in normalizado]
    if len(identificadores) != len(set(identificadores)):
        raise ErroValidacaoPatriarcasEdocs(
            "O E-Docs retornou identificadores de patriarca duplicados."
        )
    return sorted(
        normalizado,
        key=lambda registro: str(registro["id_externo"]),
    )


def _retrato(patriarca: PatriarcaEdocs | None) -> dict:
    if patriarca is None:
        return {}
    return {
        campo: (
            str(getattr(patriarca, campo))
            if campo == "id_externo"
            else getattr(patriarca, campo)
        )
        for campo in CAMPOS_REMOTOS
    } | {
        "ativo": patriarca.ativo,
        "coletar_detalhes": patriarca.coletar_detalhes,
        "codigo_municipio": patriarca.codigo_municipio,
        "municipio_implantado": patriarca.municipio_implantado,
        "municipio_em_implantacao": patriarca.municipio_em_implantacao,
        "municipio_manifestou_interesse": (
            patriarca.municipio_manifestou_interesse
        ),
        "municipio_implantado_sem_uso_edocs": (
            patriarca.municipio_implantado_sem_uso_edocs
        ),
        "versao": patriarca.versao,
    }


def _identificar_campos_alterados(
    patriarca: PatriarcaEdocs,
    observado: dict,
) -> list[str]:
    alterados = [
        campo
        for campo in CAMPOS_REMOTOS[1:]
        if getattr(patriarca, campo) != observado[campo]
    ]
    if not patriarca.ativo:
        alterados.append("ativo")
    return alterados


def _criar_evento(*, ator, tipo_evento, mensagem, **kwargs):
    return EventoAuditoriaPatriarcaEdocs.objects.create(
        tipo_evento=tipo_evento,
        mensagem=mensagem,
        **kwargs,
        **_valores_auditoria(ator),
    )


def sincronizar_patriarcas_edocs(
    *,
    ator: AtorAuditoriaEdocs | None = None,
    cliente: ClienteEdocs | None = None,
) -> ColetaPatriarcasEdocs:
    """Consulta e compara, mas nunca altera automaticamente o catálogo definitivo."""

    ator = ator or AtorAuditoriaEdocs()
    coleta = ColetaPatriarcasEdocs.objects.create(
        ambiente=settings.GPP_EDOCS_ENVIRONMENT,
        situacao=SituacaoColetaPatriarcas.EM_EXECUCAO,
        iniciada_em=timezone.now(),
        **_valores_auditoria(ator),
    )
    _criar_evento(
        ator=ator,
        coleta=coleta,
        tipo_evento=TipoEventoAuditoriaPatriarca.COLETA_INICIADA,
        mensagem="Consulta ao catálogo de patriarcas iniciada.",
    )

    try:
        resposta = (cliente or ClienteEdocs()).listar_patriarcas()
        normalizado = _normalizar_catalogo(resposta)
        _persistir_comparacao(coleta, normalizado, ator)
    except (ErroEdocs, ErroValidacaoPatriarcasEdocs) as exc:
        _marcar_coleta_com_falha(coleta, ator, exc.__class__.__name__, str(exc))
        publicar_evento_edocs("edocs.patriarcas.coleta.falhou", _resumo(coleta))
        return coleta
    except Exception:
        logger.exception("Falha interna na sincronização de patriarcas do E-Docs")
        _marcar_coleta_com_falha(
            coleta,
            ator,
            "ErroInternoPatriarcasEdocs",
            "A consulta falhou durante o processamento interno.",
        )
        publicar_evento_edocs("edocs.patriarcas.coleta.falhou", _resumo(coleta))
        return coleta

    publicar_evento_edocs("edocs.patriarcas.coleta.concluida", _resumo(coleta))
    return coleta


def _marcar_coleta_com_falha(coleta, ator, codigo_erro, mensagem_erro):
    coleta.situacao = SituacaoColetaPatriarcas.FALHOU
    coleta.concluida_em = timezone.now()
    coleta.codigo_erro = codigo_erro
    coleta.mensagem_erro = mensagem_erro[:500]
    for campo, valor in _valores_atualizacao_auditoria(ator).items():
        setattr(coleta, campo, valor)
    coleta.save()
    _criar_evento(
        ator=ator,
        coleta=coleta,
        tipo_evento=TipoEventoAuditoriaPatriarca.COLETA_FALHOU,
        mensagem="A consulta ao catálogo de patriarcas falhou.",
        metadados={"codigo_erro": coleta.codigo_erro},
    )


@transaction.atomic
def _persistir_comparacao(coleta, normalizado, ator):
    catalogo = {
        registro.id_externo: registro
        for registro in PatriarcaEdocs.objects.select_for_update().all()
    }
    ids_remotos = {registro["id_externo"] for registro in normalizado}
    contagens = {opcao: 0 for opcao in TipoComparacaoPatriarca.values}

    for registro in normalizado:
        patriarca = catalogo.get(registro["id_externo"])
        campos_alterados = (
            _identificar_campos_alterados(patriarca, registro)
            if patriarca
            else []
        )
        comparacao = (
            TipoComparacaoPatriarca.NOVO
            if patriarca is None
            else TipoComparacaoPatriarca.ALTERADO
            if campos_alterados
            else TipoComparacaoPatriarca.COINCIDENTE
        )
        contagens[comparacao] += 1
        observacao = ObservacaoPatriarcaEdocs.objects.create(
            coleta=coleta,
            patriarca=patriarca,
            comparacao=comparacao,
            hash_conteudo=_calcular_hash_canonico(registro),
            **registro,
            **_valores_auditoria(ator),
        )
        if comparacao != TipoComparacaoPatriarca.COINCIDENTE:
            _registrar_divergencia(
                coleta=coleta,
                observacao=observacao,
                patriarca=patriarca,
                observado=registro,
                comparacao=comparacao,
                campos_alterados=campos_alterados,
                ator=ator,
            )

    ausentes = [
        patriarca
        for id_externo, patriarca in catalogo.items()
        if patriarca.ativo and id_externo not in ids_remotos
    ]
    contagens[TipoComparacaoPatriarca.AUSENTE] = len(ausentes)
    for patriarca in ausentes:
        _registrar_divergencia(
            coleta=coleta,
            observacao=None,
            patriarca=patriarca,
            observado=None,
            comparacao=TipoComparacaoPatriarca.AUSENTE,
            campos_alterados=["ativo"],
            ator=ator,
        )

    quantidade_pendentes = sum(
        contagens[valor]
        for valor in (
            TipoComparacaoPatriarca.NOVO,
            TipoComparacaoPatriarca.ALTERADO,
            TipoComparacaoPatriarca.AUSENTE,
        )
    )
    coleta.situacao = (
        SituacaoColetaPatriarcas.CONCLUIDA_COM_DIVERGENCIAS
        if quantidade_pendentes
        else SituacaoColetaPatriarcas.CONCLUIDA
    )
    coleta.concluida_em = timezone.now()
    coleta.hash_fonte = _calcular_hash_canonico(normalizado)
    coleta.quantidade_observados = len(normalizado)
    coleta.quantidade_coincidentes = contagens[TipoComparacaoPatriarca.COINCIDENTE]
    coleta.quantidade_novos = contagens[TipoComparacaoPatriarca.NOVO]
    coleta.quantidade_alterados = contagens[TipoComparacaoPatriarca.ALTERADO]
    coleta.quantidade_ausentes = contagens[TipoComparacaoPatriarca.AUSENTE]
    coleta.quantidade_pendentes = quantidade_pendentes
    for campo, valor in _valores_atualizacao_auditoria(ator).items():
        setattr(coleta, campo, valor)
    coleta.save()
    _criar_evento(
        ator=ator,
        coleta=coleta,
        tipo_evento=TipoEventoAuditoriaPatriarca.COLETA_CONCLUIDA,
        mensagem="Consulta ao catálogo de patriarcas concluída.",
        metadados=_resumo(coleta),
    )


def _registrar_divergencia(
    *,
    coleta,
    observacao,
    patriarca,
    observado,
    comparacao,
    campos_alterados,
    ator,
):
    dados_observados_json = (
        {**observado, "id_externo": str(observado["id_externo"])}
        if observado is not None
        else None
    )
    divergencia = DivergenciaPatriarcaEdocs.objects.create(
        coleta=coleta,
        observacao=observacao,
        patriarca=patriarca,
        id_externo=(
            observado["id_externo"] if observado is not None else patriarca.id_externo
        ),
        comparacao=comparacao,
        dados_esperados=_retrato(patriarca),
        dados_observados=dados_observados_json,
        campos_alterados=campos_alterados,
        **_valores_auditoria(ator),
    )
    _criar_evento(
        ator=ator,
        coleta=coleta,
        patriarca=patriarca,
        divergencia=divergencia,
        tipo_evento=TipoEventoAuditoriaPatriarca.DIVERGENCIA_DETECTADA,
        mensagem="Divergência no catálogo de patriarcas detectada.",
        dados_anteriores=_retrato(patriarca) or None,
        dados_atuais=dados_observados_json,
        metadados={"comparacao": comparacao, "campos_alterados": campos_alterados},
    )


def _resumo(coleta: ColetaPatriarcasEdocs) -> dict:
    return {
        "coleta_id": str(coleta.pk),
        "situacao": coleta.situacao,
        "ambiente": coleta.ambiente,
        "quantidade_observados": coleta.quantidade_observados,
        "quantidade_coincidentes": coleta.quantidade_coincidentes,
        "quantidade_novos": coleta.quantidade_novos,
        "quantidade_alterados": coleta.quantidade_alterados,
        "quantidade_ausentes": coleta.quantidade_ausentes,
        "quantidade_pendentes": coleta.quantidade_pendentes,
        "concluida_em": (
            coleta.concluida_em.isoformat() if coleta.concluida_em else None
        ),
    }


DECISOES_VALIDAS = {
    TipoComparacaoPatriarca.NOVO: {
        DecisaoDivergenciaPatriarca.ADICIONAR,
        DecisaoDivergenciaPatriarca.MANTER,
    },
    TipoComparacaoPatriarca.ALTERADO: {
        DecisaoDivergenciaPatriarca.ATUALIZAR,
        DecisaoDivergenciaPatriarca.MANTER,
    },
    TipoComparacaoPatriarca.AUSENTE: {
        DecisaoDivergenciaPatriarca.DESATIVAR,
        DecisaoDivergenciaPatriarca.MANTER,
    },
}


@transaction.atomic
# pylint: disable-next=too-many-statements,too-many-branches
def aplicar_decisao_divergencia_patriarca(
    divergencia_id: int,
    *,
    decisao: str,
    justificativa: str,
    ator: AtorAuditoriaEdocs,
    coletar_detalhes: bool | None = None,
) -> DivergenciaPatriarcaEdocs:
    """Aplica uma decisão humana à tabela definitiva e registra sua evidência."""

    divergencia = DivergenciaPatriarcaEdocs.objects.select_for_update().get(
        pk=divergencia_id
    )
    if divergencia.situacao != SituacaoDivergenciaPatriarca.PENDENTE:
        raise ErroDecisaoPatriarcaEdocs("A divergência já foi decidida.")
    if decisao not in DECISOES_VALIDAS[divergencia.comparacao]:
        raise ErroDecisaoPatriarcaEdocs(
            "A decisão não é válida para esse tipo de divergência."
        )
    justificativa = justificativa.strip()
    if not justificativa:
        raise ErroDecisaoPatriarcaEdocs("A decisão exige justificativa.")
    if DivergenciaPatriarcaEdocs.objects.filter(
        id_externo=divergencia.id_externo,
        situacao=SituacaoDivergenciaPatriarca.PENDENTE,
        criado_em__gt=divergencia.criado_em,
    ).exists():
        raise ErroDecisaoPatriarcaEdocs(
            "Existe divergência mais recente para esse patriarca."
        )

    catalogo_atual = PatriarcaEdocs.objects.select_for_update().filter(
        id_externo=divergencia.id_externo
    ).first()
    versao_esperada = divergencia.dados_esperados.get("versao")
    if divergencia.comparacao == TipoComparacaoPatriarca.NOVO:
        if catalogo_atual is not None:
            raise ErroDecisaoPatriarcaEdocs(
                "O patriarca já foi incluído; atualize as divergências."
            )
    elif catalogo_atual is None or catalogo_atual.versao != versao_esperada:
        raise ErroDecisaoPatriarcaEdocs(
            "O cadastro mudou após a comparação; faça uma nova consulta."
        )

    patriarca = None
    anterior = None
    tipo_evento = TipoEventoAuditoriaPatriarca.CATALOGO_MANTIDO
    if decisao == DecisaoDivergenciaPatriarca.ADICIONAR:
        valores = divergencia.dados_observados.copy()
        valores["id_externo"] = UUID(str(valores["id_externo"]))
        valores["coletar_detalhes"] = bool(coletar_detalhes)
        patriarca = PatriarcaEdocs.objects.create(
            **valores,
            **_valores_auditoria(ator),
        )
        tipo_evento = TipoEventoAuditoriaPatriarca.CATALOGO_INCLUIDO
    elif decisao == DecisaoDivergenciaPatriarca.ATUALIZAR:
        patriarca = catalogo_atual
        anterior = _retrato(patriarca)
        for campo in CAMPOS_REMOTOS[1:]:
            setattr(patriarca, campo, divergencia.dados_observados[campo])
        patriarca.ativo = True
        if coletar_detalhes is not None:
            patriarca.coletar_detalhes = coletar_detalhes
        patriarca.versao += 1
        for campo, valor in _valores_atualizacao_auditoria(ator).items():
            setattr(patriarca, campo, valor)
        patriarca.save()
        tipo_evento = TipoEventoAuditoriaPatriarca.CATALOGO_ATUALIZADO
    elif decisao == DecisaoDivergenciaPatriarca.DESATIVAR:
        patriarca = catalogo_atual
        anterior = _retrato(patriarca)
        patriarca.ativo = False
        patriarca.coletar_detalhes = False
        patriarca.versao += 1
        for campo, valor in _valores_atualizacao_auditoria(ator).items():
            setattr(patriarca, campo, valor)
        patriarca.save()
        tipo_evento = TipoEventoAuditoriaPatriarca.CATALOGO_DESATIVADO
    else:
        patriarca = divergencia.patriarca
        anterior = _retrato(patriarca) or None

    divergencia.patriarca = patriarca
    divergencia.decisao = decisao
    divergencia.justificativa = justificativa
    divergencia.situacao = (
        SituacaoDivergenciaPatriarca.MANTIDA
        if decisao == DecisaoDivergenciaPatriarca.MANTER
        else SituacaoDivergenciaPatriarca.APLICADA
    )
    divergencia.revisado_por_id = ator.usuario_id
    divergencia.revisado_por_nome = ator.nome
    divergencia.revisado_em = timezone.now()
    for campo, valor in _valores_atualizacao_auditoria(ator).items():
        setattr(divergencia, campo, valor)
    divergencia.save()

    DivergenciaPatriarcaEdocs.objects.filter(
        id_externo=divergencia.id_externo,
        situacao=SituacaoDivergenciaPatriarca.PENDENTE,
        criado_em__lte=divergencia.criado_em,
    ).exclude(pk=divergencia.pk).update(
        situacao=SituacaoDivergenciaPatriarca.SUBSTITUIDA,
        atualizado_por_id=ator.usuario_id,
        atualizado_por_nome=ator.nome,
        atualizado_em=timezone.now(),
    )
    _criar_evento(
        ator=ator,
        coleta=divergencia.coleta,
        patriarca=patriarca,
        divergencia=divergencia,
        tipo_evento=tipo_evento,
        mensagem="Decisão sobre divergência de patriarca registrada.",
        dados_anteriores=anterior,
        dados_atuais=_retrato(patriarca) or None,
        metadados={"decisao": decisao, "justificativa": justificativa},
    )
    publicar_evento_edocs(
        "edocs.patriarcas.divergencia.revisada",
        {
            "divergencia_id": divergencia.pk,
            "coleta_id": str(divergencia.coleta_id),
            "situacao": divergencia.situacao,
            "decisao": decisao,
        },
    )
    return divergencia


@transaction.atomic
def definir_selecao_coleta_patriarca(
    patriarca_id: int,
    *,
    coletar_detalhes: bool,
    justificativa: str,
    ator: AtorAuditoriaEdocs,
) -> PatriarcaEdocs:
    """Define explicitamente quais patriarcas alimentam as demais coletas."""

    patriarca = PatriarcaEdocs.objects.select_for_update().get(pk=patriarca_id)
    if coletar_detalhes and not patriarca.ativo:
        raise ErroDecisaoPatriarcaEdocs(
            "Patriarca inativo não pode ser selecionado para coleta."
        )
    justificativa = justificativa.strip()
    if not justificativa:
        raise ErroDecisaoPatriarcaEdocs("A alteração exige justificativa.")
    if patriarca.coletar_detalhes == coletar_detalhes:
        return patriarca
    anterior = _retrato(patriarca)
    patriarca.coletar_detalhes = coletar_detalhes
    patriarca.versao += 1
    for campo, valor in _valores_atualizacao_auditoria(ator).items():
        setattr(patriarca, campo, valor)
    patriarca.save()
    _criar_evento(
        ator=ator,
        patriarca=patriarca,
        tipo_evento=TipoEventoAuditoriaPatriarca.SELECAO_COLETA_ALTERADA,
        mensagem="Seleção do patriarca para coleta detalhada alterada.",
        dados_anteriores=anterior,
        dados_atuais=_retrato(patriarca),
        metadados={"justificativa": justificativa},
    )
    publicar_evento_edocs(
        "edocs.patriarcas.selecao_coleta.alterada",
        {
            "patriarca_id": patriarca.pk,
            "coletar_detalhes": patriarca.coletar_detalhes,
            "versao": patriarca.versao,
        },
    )
    return patriarca


@transaction.atomic
def definir_indicador_municipio_sem_edocs(
    patriarca_id: int,
    *,
    municipio_implantado_sem_uso_edocs: bool,
    justificativa: str,
    ator: AtorAuditoriaEdocs,
) -> PatriarcaEdocs:
    """Mantém o indicador manual e preserva a decisão na trilha de auditoria."""

    patriarca = PatriarcaEdocs.objects.select_for_update().get(pk=patriarca_id)
    justificativa = justificativa.strip()
    if not justificativa:
        raise ErroDecisaoPatriarcaEdocs("A alteração exige justificativa.")
    if (
        patriarca.municipio_implantado_sem_uso_edocs
        == municipio_implantado_sem_uso_edocs
    ):
        return patriarca
    anterior = _retrato(patriarca)
    patriarca.municipio_implantado_sem_uso_edocs = (
        municipio_implantado_sem_uso_edocs
    )
    patriarca.versao += 1
    for campo, valor in _valores_atualizacao_auditoria(ator).items():
        setattr(patriarca, campo, valor)
    patriarca.save()
    _criar_evento(
        ator=ator,
        patriarca=patriarca,
        tipo_evento=TipoEventoAuditoriaPatriarca.INDICADOR_SEM_EDOCS_ALTERADO,
        mensagem="Indicador de município implantado sem uso do E-Docs alterado.",
        dados_anteriores=anterior,
        dados_atuais=_retrato(patriarca),
        metadados={"justificativa": justificativa},
    )
    publicar_evento_edocs(
        "edocs.patriarcas.indicador_sem_edocs.alterado",
        {
            "patriarca_id": patriarca.pk,
            "municipio_implantado_sem_uso_edocs": (
                patriarca.municipio_implantado_sem_uso_edocs
            ),
            "versao": patriarca.versao,
        },
    )
    return patriarca


@transaction.atomic
def definir_indicadores_municipais_patriarca(
    patriarca_id: int,
    *,
    justificativa: str,
    ator: AtorAuditoriaEdocs,
    **alteracoes,
) -> PatriarcaEdocs:
    """Altera somente campos municipais explicitamente informados pelo gestor."""

    campos_permitidos = {
        "codigo_municipio",
        "municipio_implantado",
        "municipio_em_implantacao",
        "municipio_manifestou_interesse",
        "municipio_implantado_sem_uso_edocs",
    }
    if set(alteracoes) - campos_permitidos:
        raise ErroDecisaoPatriarcaEdocs("Há indicador municipal não reconhecido.")
    justificativa = justificativa.strip()
    if not justificativa:
        raise ErroDecisaoPatriarcaEdocs("A alteração exige justificativa.")
    if not alteracoes:
        raise ErroDecisaoPatriarcaEdocs("Informe ao menos um indicador municipal.")
    codigo = alteracoes.get("codigo_municipio")
    if codigo is not None and (
        isinstance(codigo, bool)
        or not isinstance(codigo, int)
        or not 1_000_000 <= codigo <= 9_999_999
    ):
        raise ErroDecisaoPatriarcaEdocs("O código municipal deve ter sete dígitos.")

    patriarca = PatriarcaEdocs.objects.select_for_update().get(pk=patriarca_id)
    if codigo is not None and PatriarcaEdocs.objects.filter(
        codigo_municipio=codigo
    ).exclude(pk=patriarca.pk).exists():
        raise ErroDecisaoPatriarcaEdocs(
            "O código municipal já está associado a outro patriarca."
        )
    efetivas = {
        campo: valor
        for campo, valor in alteracoes.items()
        if getattr(patriarca, campo) != valor
    }
    if not efetivas:
        return patriarca
    anterior = _retrato(patriarca)
    for campo, valor in efetivas.items():
        setattr(patriarca, campo, valor)
    patriarca.versao += 1
    for campo, valor in _valores_atualizacao_auditoria(ator).items():
        setattr(patriarca, campo, valor)
    try:
        patriarca.save()
    except IntegrityError as exc:
        raise ErroDecisaoPatriarcaEdocs(
            "O código municipal já está associado a outro patriarca."
        ) from exc
    _criar_evento(
        ator=ator,
        patriarca=patriarca,
        tipo_evento=(
            TipoEventoAuditoriaPatriarca.INDICADORES_MUNICIPAIS_ALTERADOS
        ),
        mensagem="Indicadores municipais do patriarca alterados.",
        dados_anteriores=anterior,
        dados_atuais=_retrato(patriarca),
        metadados={
            "justificativa": justificativa,
            "campos_alterados": sorted(efetivas),
        },
    )
    publicar_evento_edocs(
        "edocs.patriarcas.indicadores_municipais.alterados",
        {
            "patriarca_id": patriarca.pk,
            "campos_alterados": sorted(efetivas),
            "versao": patriarca.versao,
        },
    )
    return patriarca
