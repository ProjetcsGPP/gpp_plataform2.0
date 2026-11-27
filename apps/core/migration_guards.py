"""Proteções de propriedade de migração nos perfis de execução piloto."""

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


def bloquear_migracao_carga_piloto(sender, **kwargs):
    """Impede ``migrate`` nos processos de domínio do piloto."""
    if getattr(settings, "GPP_BLOQUEAR_MIGRACOES_NO_PROCESSO_CARGA", False):
        raise ImproperlyConfigured(
            "O perfil carga_piloto não executa migrações. "
            "Aplique-as pelo processo de plataforma, em janela controlada."
        )
    if getattr(settings, "GPP_BLOQUEAR_MIGRACOES_NO_PROCESSO_PUBLICACOES", False):
        raise ImproperlyConfigured(
            "O perfil publicacoes_piloto não executa migrações. "
            "Aplique-as pelo processo de plataforma, em janela controlada."
        )
    if getattr(settings, "GPP_BLOQUEAR_MIGRACOES_NO_PROCESSO_ACOES", False):
        raise ImproperlyConfigured(
            "O perfil acoes_piloto não executa migrações. "
            "Aplique-as pelo processo de plataforma, em janela controlada."
        )
