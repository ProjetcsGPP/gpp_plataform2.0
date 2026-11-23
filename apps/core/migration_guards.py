"""Proteções de propriedade de migração nos perfis de execução piloto."""

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


def bloquear_migracao_carga_piloto(sender, **kwargs):
    """Impede qualquer ``migrate`` iniciado sob o perfil exclusivo de Carga."""
    if getattr(settings, "GPP_BLOQUEAR_MIGRACOES_NO_PROCESSO_CARGA", False):
        raise ImproperlyConfigured(
            "O perfil carga_piloto não executa migrações. "
            "Aplique-as pelo processo de plataforma, em janela controlada."
        )
