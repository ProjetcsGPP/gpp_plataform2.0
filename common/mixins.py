"""
GPP Plataform 2.0 — Mixins de Segurança e Auditoria
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
    Preenche automaticamente os campos de auditoria do AuditableModel.

    Campos preenchidos:
      - created_by_id   : request.user.pk
      - created_by_name : username do usuário (snapshot imutável)
      - updated_by_id   : request.user.pk
      - updated_by_name : username do usuário (snapshot da última alteração)

    O username é obtido via get_full_name() com fallback para username,
    garantindo que o snapshot seja legível mesmo sem nome completo cadastrado.

    Não usa FK — alinhado com a arquitetura IAM cookie-based do accounts.
    """

    @staticmethod
    def _resolve_user_name(user):
        """Retorna nome legível do usuário: full name se disponível, senao username."""
        full_name = user.get_full_name().strip()
        return full_name if full_name else user.username

    def perform_create(self, serializer):
        user = self.request.user
        name = self._resolve_user_name(user)
        serializer.save(
            created_by_id=user.pk,
            created_by_name=name,
            updated_by_id=user.pk,
            updated_by_name=name,
        )

    def perform_update(self, serializer):
        user = self.request.user
        name = self._resolve_user_name(user)
        serializer.save(
            updated_by_id=user.pk,
            updated_by_name=name,
        )
