#!/usr/bin/env python3
"""Exclui cargas de organograma e todos os dados de teste dependentes.

Pare o servidor e os workers Celery antes da execução.

Exemplos:
    .venv/bin/python scripts/limpar_cargas_organograma.py --patriarca 1
    .venv/bin/python scripts/limpar_cargas_organograma.py --all --yes
"""

from __future__ import annotations

import argparse

from _reset_carga_org_lot import (
    delete_lotation_data,
    lotation_preview,
    print_counts,
    require_confirmation,
    scope_description,
    setup_django,
)


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Limpa organogramas, lotações dependentes, envios à PRODEST, "
            "eventos e processos de carga inicial."
        )
    )
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument("--patriarca", type=int, help="ID do patriarca a limpar.")
    scope.add_argument("--all", action="store_true", help="Limpa todos os patriarcas.")
    parser.add_argument(
        "--force-active",
        action="store_true",
        help="Permite excluir mesmo quando há envio à PRODEST em andamento.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Confirma a exclusão sem solicitar digitação interativa.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    setup_django()

    from django.db import transaction
    from django.db.models import Q

    from apps.carga_org_lot.models import (
        CasoValidacaoImportacao,
        EnvioOrganogramaProdest,
        EventoIntegracaoProdest,
        ImportacaoPlanilha,
        ProcessoCargaInicial,
        ResolucaoValidacao,
        StatusEnvioOrganograma,
    )

    patriarch_id = None if args.all else args.patriarca
    organograms = ImportacaoPlanilha.objects.filter(idtipocarga_id=3)
    processes = ProcessoCargaInicial.objects.all()
    submissions = EnvioOrganogramaProdest.objects.all()
    if patriarch_id is not None:
        organograms = organograms.filter(idpatriarca_id=patriarch_id)
        processes = processes.filter(idpatriarca_id=patriarch_id)
        submissions = submissions.filter(
            idimportacaoplanilha__idpatriarca_id=patriarch_id
        )

    organogram_ids = list(organograms.values_list("pk", flat=True))
    process_ids = list(processes.values_list("pk", flat=True))
    submission_ids = list(submissions.values_list("pk", flat=True))
    active_submissions = submissions.filter(
        strstatus__in=[
            StatusEnvioOrganograma.SOLICITANDO,
            StatusEnvioOrganograma.PROCESSANDO,
        ]
    ).count()
    if patriarch_id is None:
        events = EventoIntegracaoProdest.objects.all()
    else:
        event_filter = Q(idenvioorganograma_id__in=submission_ids) | Q(
            idprocessocargainicial_id__in=process_ids
        )
        event_filter |= Q(idpatriarca_id=patriarch_id)
        events = EventoIntegracaoProdest.objects.filter(event_filter)

    preview = {
        "importacoes_organograma": len(organogram_ids),
        "envios_prodest": len(submission_ids),
        "envios_em_andamento": active_submissions,
        "eventos_integracao": events.count(),
        "processos_carga_inicial": len(process_ids),
        **lotation_preview(organogram_ids=organogram_ids),
    }
    print_counts("Dados encontrados:", preview)
    if not any(preview.values()):
        print("Nenhuma carga de organograma foi encontrada para o escopo informado.")
        return
    if active_submissions and not args.force_active:
        raise SystemExit(
            "Há envio à PRODEST em andamento. Pare os workers e use "
            "--force-active somente se tiver certeza de que é um teste local."
        )

    require_confirmation(
        description=(
            f"organograma e lotações dependentes de {scope_description(patriarch_id)}"
        ),
        assume_yes=args.yes,
    )

    with transaction.atomic():
        deleted = delete_lotation_data(organogram_ids=organogram_ids)
        deleted["eventos_integracao"] = events.delete()[0]
        deleted["envios_prodest"] = EnvioOrganogramaProdest.objects.filter(
            pk__in=submission_ids
        ).delete()[0]

        organogram_cases = CasoValidacaoImportacao.objects.filter(
            idrelatoriovalidacao__idimportacaoplanilha_id__in=organogram_ids
        )
        deleted["resolucoes_organograma"] = ResolucaoValidacao.objects.filter(
            idcasovalidacao__in=organogram_cases
        ).delete()[0]
        deleted["organogramas_e_dependencias"] = (
            ImportacaoPlanilha.objects.filter(pk__in=organogram_ids).delete()[0]
        )
        deleted["processos_e_historicos"] = ProcessoCargaInicial.objects.filter(
            pk__in=process_ids
        ).delete()[0]

    print_counts("Exclusões concluídas:", deleted)


if __name__ == "__main__":
    main()
