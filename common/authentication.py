"""Verificação CSRF compartilhada por autenticações baseadas em cookie."""

from rest_framework.authentication import CSRFCheck
from rest_framework.exceptions import PermissionDenied


def enforce_csrf(request):
    """Aplica a mesma validação usada pelo SessionAuthentication do DRF."""
    check = CSRFCheck(lambda django_request: None)
    check.process_request(request)
    reason = check.process_view(request, None, (), {})
    if reason:
        raise PermissionDenied(f"CSRF Failed: {reason}")
