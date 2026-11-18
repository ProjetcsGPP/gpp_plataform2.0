"""Inferência auditável da primeira implantação observada no E-Docs."""

from django.db import transaction

from apps.pub_institucional.models import (
    CriterioImplantacaoEdocs,
    EventoAuditoriaImplantacaoEdocs,
    EventoAuditoriaMunicipioEdocs,
    ImplantacaoPatriarcaEdocs,
    MunicipioEdocs,
)


def _possui_atividade(resultado) -> bool:
    return any(
        (valor or 0) > 0
        for valor in (
            resultado.total_processos,
            resultado.total_documentos,
            resultado.total_paginas,
        )
    )


def _competencia_anterior(ano, mes):
    if mes == 1:
        return ano - 1, 12
    return ano, mes - 1


def _sincronizar_cadastro_municipal(implantacao, resultado, *, ator):
    """Reflete a evidência oficial no cadastro municipal sem decisão humana."""

    codigo_ibge = resultado.codigo_municipio
    if codigo_ibge is None or not 3_200_000 <= codigo_ibge <= 3_299_999:
        return None
    auditoria = {
        "criado_por_id": ator.usuario_id,
        "criado_por_nome": ator.nome,
        "atualizado_por_id": ator.usuario_id,
        "atualizado_por_nome": ator.nome,
    }
    municipio, criado = MunicipioEdocs.objects.get_or_create(
        codigo_ibge=codigo_ibge,
        defaults={"nome": resultado.nome_patriarca, **auditoria},
    )
    anterior = {
        "codigo_ibge": municipio.codigo_ibge,
        "nome": municipio.nome,
        "versao": municipio.versao,
        "implantacao_edocs_observada": None,
    }
    vigencia = municipio.vigencias_situacao.filter(
        ano_fim__isnull=True,
        mes_fim__isnull=True,
    ).first()
    if vigencia is not None:
        inicio_manual = (vigencia.ano_inicio, vigencia.mes_inicio)
        inicio_oficial = (implantacao.ano, implantacao.mes)
        if inicio_manual < inicio_oficial:
            vigencia.ano_fim, vigencia.mes_fim = _competencia_anterior(
                implantacao.ano,
                implantacao.mes,
            )
        else:
            vigencia.ano_fim, vigencia.mes_fim = inicio_manual
        vigencia.save(
            update_fields=("ano_fim", "mes_fim", "atualizado_em")
        )
    municipio.versao += int(not criado)
    municipio.atualizado_por_id = ator.usuario_id
    municipio.atualizado_por_nome = ator.nome
    municipio.save()
    atual = {
        "codigo_ibge": municipio.codigo_ibge,
        "nome": municipio.nome,
        "versao": municipio.versao,
        "implantacao_edocs_observada": {
            "ano": implantacao.ano,
            "mes": implantacao.mes,
            "criterio": implantacao.criterio,
        },
    }
    EventoAuditoriaMunicipioEdocs.objects.create(
        municipio=municipio,
        tipo_evento="IMPLANTACAO_COM_USO_OBSERVADA",
        mensagem=(
            "Município atualizado automaticamente por atividade na API "
            "oficial E-Docs."
        ),
        dados_anteriores=anterior,
        dados_atuais=atual,
        metadados={
            "origem": "API_OFICIAL_EDOCS",
            "coleta_id": str(implantacao.coleta_evidencia_id),
            "patriarca_id": implantacao.patriarca_id,
        },
        **auditoria,
    )
    return municipio


@transaction.atomic
def registrar_implantacoes_observadas(coleta, resultados, *, ator) -> list:
    """Registra somente a primeira competência positiva de cada patriarca."""

    criadas = []
    for resultado in resultados:
        if not _possui_atividade(resultado):
            continue
        implantacao, criada = ImplantacaoPatriarcaEdocs.objects.get_or_create(
            patriarca_id=resultado.patriarca_id,
            defaults={
                "ano": coleta.competencia.ano,
                "mes": coleta.competencia.mes,
                "coleta_evidencia": coleta,
                "criterio": CriterioImplantacaoEdocs.ATIVIDADE_API,
                "totais_evidencia": {
                    "total_processos": resultado.total_processos,
                    "total_documentos": resultado.total_documentos,
                    "total_paginas": resultado.total_paginas,
                },
                "criado_por_id": ator.usuario_id,
                "criado_por_nome": ator.nome,
                "atualizado_por_id": ator.usuario_id,
                "atualizado_por_nome": ator.nome,
            },
        )
        if not criada:
            continue
        EventoAuditoriaImplantacaoEdocs.objects.create(
            implantacao=implantacao,
            mensagem="Implantação inferida por atividade na API oficial E-Docs.",
            metadados={
                "coleta_id": str(coleta.pk),
                "ano": coleta.competencia.ano,
                "mes": coleta.competencia.mes,
                "criterio": CriterioImplantacaoEdocs.ATIVIDADE_API,
            },
            criado_por_id=ator.usuario_id,
            criado_por_nome=ator.nome,
            atualizado_por_id=ator.usuario_id,
            atualizado_por_nome=ator.nome,
        )
        _sincronizar_cadastro_municipal(
            implantacao,
            resultado,
            ator=ator,
        )
        criadas.append(implantacao)
    return criadas
