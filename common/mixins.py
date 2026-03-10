"""
GPP Plataform 2.0 — Mixins de Segurança
Uso obrigatório em todas as ViewSets que retornam recursos de usuário.
"""
import logging

from rest_framework.exceptions import PermissionDenied

security_logger = logging.getLogger("gpp.security")


class SecureQuerysetMixin:
    """
    Proteção obrigatória contra IDOR (Insecure Direct Object Reference).

    Garante que o queryset seja sempre filtrado pelo escopo do usuário.
    Em caso de falha no carregamento do escopo, retorna queryset vazio
    (fail-closed) em vez de vazar todos os registros.

    Uso:
        class MinhaViewSet(SecureQuerysetMixin, viewsets.ModelViewSet):
            scope_field = "orgao"   # campo do model a filtrar
            scope_source = "orgao"  # atributo do profile do usuário
    """

    scope_field = "orgao"    # campo no model
    scope_source = "orgao"   # atributo em request.user.profile

    def get_queryset(self):
        qs = super().get_queryset()
        return self.filter_queryset_by_scope(qs)

    def filter_queryset_by_scope(self, qs):
        user = self.request.user

        try:
            profile = user.profile
            scope_value = getattr(profile, self.scope_source, None)
        except AttributeError:
            scope_value = None

        if scope_value is None:
            security_logger.warning(
                "IDOR_SCOPE_MISSING user_id=%s view=%s",
                getattr(user, "id", "anonymous"),
                self.__class__.__name__,
            )
            return qs.none()  # fail-closed

        return qs.filter(**{self.scope_field: scope_value})


class AuditableMixin:
    """
    Preenche automaticamente created_by e updated_by
    nos models que herdam de AuditableModel.
    """

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user, updated_by=self.request.user)

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)
