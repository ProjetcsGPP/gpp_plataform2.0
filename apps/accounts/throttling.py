"""Throttles específicos para os endpoints públicos de autenticação."""

from django.conf import settings
from rest_framework.throttling import SimpleRateThrottle


class LoginRateThrottle(SimpleRateThrottle):
    """Limita tentativas por IP mesmo quando outro cookie já está autenticado."""

    scope = "login"

    def get_rate(self):
        return settings.LOGIN_THROTTLE_RATE

    def get_cache_key(self, request, view):
        ident = self.get_ident(request)
        return self.cache_format % {"scope": self.scope, "ident": ident}
