"""Limite independente para consumidores anônimos da API pública."""

from django.conf import settings
from rest_framework.throttling import AnonRateThrottle


class TaxaPublicacoesPublicas(AnonRateThrottle):
    scope = "publicacoes_publicas"

    def get_rate(self):
        """Lê a taxa por request para respeitar configuração e testes isolados."""

        return settings.PUBLICACOES_PUBLIC_THROTTLE_RATE
