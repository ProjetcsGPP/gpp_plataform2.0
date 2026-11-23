from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.core"
    verbose_name = "Núcleo do Sistema GPP Plataform 2.0"

    def ready(self):
        # O perfil de Carga ainda instala todos os modelos para leitura, mas
        # nunca pode ser o proprietário de migrações do banco compartilhado.
        from django.db.models.signals import pre_migrate

        from .migration_guards import bloquear_migracao_carga_piloto

        pre_migrate.connect(
            bloquear_migracao_carga_piloto,
            dispatch_uid="core.bloquear_migracao_carga_piloto",
        )
