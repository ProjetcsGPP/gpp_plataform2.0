from django.db import migrations


STATUS_PROGRESSO = [
    (1, "Novo"),
    (2, "Em progresso"),
    (3, "Enviando carga"),
    (4, "Carga processada"),
    (5, "Erro no envio"),
    (6, "Erro crítico"),
]

TIPOS_CARGA = [
    (3, "Organograma"),
    (4, "Lotações"),
    (5, "Lotações em pacote"),
]

STATUS_CARGA = [
    (0, "Análise inicial", 0),
    (1, "Aguardando organograma", 0),
    (2, "Organograma finalizado", 1),
    (3, "Aguardando Acesso Cidadão", 0),
    (4, "Acesso Cidadão finalizado", 1),
    (5, "Finalizado", 1),
    (6, "Erro", 0),
    (7, "Aguardando Acesso Cidadão da lotação", 0),
    (8, "Aguardando organograma da carga inicial", 0),
    (9, "Aguardando carga inicial de lotação", 0),
    (10, "Aguardando carga inicial de lotação em pacote", 0),
]


def seed_catalogos(apps, schema_editor):
    StatusProgresso = apps.get_model("carga_org_lot", "StatusProgresso")
    TipoCarga = apps.get_model("carga_org_lot", "TipoCarga")
    StatusCarga = apps.get_model("carga_org_lot", "StatusCarga")

    for pk, descricao in STATUS_PROGRESSO:
        StatusProgresso.objects.update_or_create(
            idstatusprogresso=pk,
            defaults={"strdescricao": descricao},
        )

    for pk, descricao in TIPOS_CARGA:
        TipoCarga.objects.update_or_create(
            idtipocarga=pk,
            defaults={"strdescricao": descricao},
        )

    for pk, descricao, sucesso in STATUS_CARGA:
        StatusCarga.objects.update_or_create(
            idstatuscarga=pk,
            defaults={
                "strdescricao": descricao,
                "flgsucesso": sucesso,
            },
        )


class Migration(migrations.Migration):
    dependencies = [
        ("carga_org_lot", "0002_refactor_auditablemodel_remove_fk_auth_user"),
    ]

    operations = [
        migrations.RunPython(seed_catalogos, migrations.RunPython.noop),
    ]
