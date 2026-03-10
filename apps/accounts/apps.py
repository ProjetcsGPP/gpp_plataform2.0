from django.apps import AppConfig


class AccountsConfig(AppConfig):
    name = "apps.accounts"
    verbose_name = "Accounts"

    def ready(self):
        import apps.accounts.signals  # noqa: F401 — registra signals de invalidação de cache
