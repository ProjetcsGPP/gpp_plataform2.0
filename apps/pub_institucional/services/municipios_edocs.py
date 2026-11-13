"""Regras auditadas do cadastro municipal relacionado ao E-Docs."""

from dataclasses import dataclass

from django.db import IntegrityError, transaction

from apps.pub_institucional.models import (
    EventoAuditoriaMunicipioEdocs, MunicipioEdocs, SituacaoMunicipioEdocs,
    VigenciaSituacaoMunicipioEdocs)


class ErroMunicipioEdocs(ValueError):
    """Decisão municipal inválida ou concorrente."""


@dataclass(frozen=True)
class AtorAuditoriaMunicipioEdocs:
    usuario_id: int
    nome: str


def _auditoria(ator):
    return {
        "criado_por_id": ator.usuario_id,
        "criado_por_nome": ator.nome,
        "atualizado_por_id": ator.usuario_id,
        "atualizado_por_nome": ator.nome,
    }


def _atualizacao(ator):
    return {
        "atualizado_por_id": ator.usuario_id,
        "atualizado_por_nome": ator.nome,
    }


def _validar_codigo(codigo_ibge):
    if (
        isinstance(codigo_ibge, bool)
        or not isinstance(codigo_ibge, int)
        or not 3_200_000 <= codigo_ibge <= 3_299_999
    ):
        raise ErroMunicipioEdocs(
            "Informe um código IBGE de município do Espírito Santo."
        )


def _validar_competencia(ano, mes):
    if ano < 2024 or mes not in range(1, 13):
        raise ErroMunicipioEdocs(
            "A competência deve ser igual ou posterior a janeiro de 2024."
        )


def _competencia_anterior(ano, mes):
    if mes == 1:
        return ano - 1, 12
    return ano, mes - 1


def _vigencia_aberta(municipio):
    return municipio.vigencias_situacao.filter(
        ano_fim__isnull=True,
        mes_fim__isnull=True,
    ).first()


def _retrato(municipio):
    vigencia = _vigencia_aberta(municipio)
    return {
        "codigo_ibge": municipio.codigo_ibge,
        "nome": municipio.nome,
        "ativo": municipio.ativo,
        "versao": municipio.versao,
        "situacao": vigencia.situacao if vigencia else None,
        "ano_inicio": vigencia.ano_inicio if vigencia else None,
        "mes_inicio": vigencia.mes_inicio if vigencia else None,
    }


def _evento(municipio, ator, tipo, mensagem, anterior, atual, justificativa):
    EventoAuditoriaMunicipioEdocs.objects.create(
        municipio=municipio,
        tipo_evento=tipo,
        mensagem=mensagem,
        dados_anteriores=anterior,
        dados_atuais=atual,
        metadados={"justificativa": justificativa},
        **_auditoria(ator),
    )


@transaction.atomic
def cadastrar_municipio_edocs(
    *, codigo_ibge, nome, situacao, ano_inicio, mes_inicio, justificativa, ator
):
    """Cadastra município sem fabricar uma identidade externa do E-Docs."""

    _validar_codigo(codigo_ibge)
    _validar_competencia(ano_inicio, mes_inicio)
    nome = nome.strip()
    justificativa = justificativa.strip()
    if not nome:
        raise ErroMunicipioEdocs("Informe o nome do município.")
    if not justificativa:
        raise ErroMunicipioEdocs("A inclusão exige justificativa.")
    if situacao not in SituacaoMunicipioEdocs.values:
        raise ErroMunicipioEdocs("Situação municipal não reconhecida.")
    try:
        municipio = MunicipioEdocs.objects.create(
            codigo_ibge=codigo_ibge,
            nome=nome,
            **_auditoria(ator),
        )
    except IntegrityError as exc:
        raise ErroMunicipioEdocs("O código IBGE já está cadastrado.") from exc
    VigenciaSituacaoMunicipioEdocs.objects.create(
        municipio=municipio,
        situacao=situacao,
        ano_inicio=ano_inicio,
        mes_inicio=mes_inicio,
        justificativa=justificativa,
        **_auditoria(ator),
    )
    _evento(
        municipio,
        ator,
        "MUNICIPIO_CADASTRADO",
        "Município cadastrado para acompanhamento do E-Docs.",
        {},
        _retrato(municipio),
        justificativa,
    )
    return municipio


@transaction.atomic
def alterar_situacao_municipio_edocs(
    municipio_id,
    *,
    situacao,
    ano_inicio,
    mes_inicio,
    versao,
    justificativa,
    ator,
):
    """Abre nova vigência sem reescrever a situação de meses anteriores."""

    _validar_competencia(ano_inicio, mes_inicio)
    if situacao not in SituacaoMunicipioEdocs.values:
        raise ErroMunicipioEdocs("Situação municipal não reconhecida.")
    justificativa = justificativa.strip()
    if not justificativa:
        raise ErroMunicipioEdocs("A alteração exige justificativa.")
    municipio = MunicipioEdocs.objects.select_for_update().get(pk=municipio_id)
    if municipio.versao != versao:
        raise ErroMunicipioEdocs(
            "O cadastro foi alterado por outro usuário. Atualize a consulta."
        )
    anterior = _retrato(municipio)
    vigencia = _vigencia_aberta(municipio)
    inicio = (ano_inicio, mes_inicio)
    if vigencia and inicio <= (vigencia.ano_inicio, vigencia.mes_inicio):
        raise ErroMunicipioEdocs(
            "A nova competência deve ser posterior à situação vigente."
        )
    if vigencia:
        vigencia.ano_fim, vigencia.mes_fim = _competencia_anterior(*inicio)
        vigencia.save(update_fields=("ano_fim", "mes_fim", "atualizado_em"))
    VigenciaSituacaoMunicipioEdocs.objects.create(
        municipio=municipio,
        situacao=situacao,
        ano_inicio=ano_inicio,
        mes_inicio=mes_inicio,
        justificativa=justificativa,
        **_auditoria(ator),
    )
    municipio.versao += 1
    for campo, valor in _atualizacao(ator).items():
        setattr(municipio, campo, valor)
    municipio.save()
    _evento(
        municipio,
        ator,
        "SITUACAO_ALTERADA",
        "Situação municipal do E-Docs alterada.",
        anterior,
        _retrato(municipio),
        justificativa,
    )
    return municipio


@transaction.atomic
def corrigir_cadastro_municipio_edocs(
    municipio_id, *, codigo_ibge, nome, versao, justificativa, ator
):
    """Corrige código ou nome mantendo concorrência otimista e auditoria."""

    _validar_codigo(codigo_ibge)
    nome = nome.strip()
    justificativa = justificativa.strip()
    if not nome or not justificativa:
        raise ErroMunicipioEdocs("Informe nome e justificativa.")
    municipio = MunicipioEdocs.objects.select_for_update().get(pk=municipio_id)
    if municipio.versao != versao:
        raise ErroMunicipioEdocs(
            "O cadastro foi alterado por outro usuário. Atualize a consulta."
        )
    anterior = _retrato(municipio)
    municipio.codigo_ibge = codigo_ibge
    municipio.nome = nome
    municipio.versao += 1
    for campo, valor in _atualizacao(ator).items():
        setattr(municipio, campo, valor)
    try:
        municipio.save()
    except IntegrityError as exc:
        raise ErroMunicipioEdocs("O código IBGE já está cadastrado.") from exc
    _evento(
        municipio,
        ator,
        "CADASTRO_CORRIGIDO",
        "Cadastro municipal do E-Docs corrigido.",
        anterior,
        _retrato(municipio),
        justificativa,
    )
    return municipio
