"""Inferência auditável da primeira implantação observada no E-Docs."""

from django.db import transaction

from apps.pub_institucional.models import (
    CriterioImplantacaoEdocs,
    EventoAuditoriaImplantacaoEdocs,
    ImplantacaoPatriarcaEdocs,
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
        criadas.append(implantacao)
    return criadas
