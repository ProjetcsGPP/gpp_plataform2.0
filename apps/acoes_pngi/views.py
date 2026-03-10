# Views da app acoes_pngi — implementar na fase de domínio.
# Todas as views DEVEM usar SecureQuerysetMixin para proteção IDOR.
#
# Exemplo:
# from common.mixins import SecureQuerysetMixin, AuditableMixin
# from rest_framework import viewsets
#
# class AcaoViewSet(SecureQuerysetMixin, AuditableMixin, viewsets.ModelViewSet):
#     scope_field = "orgao"
#     scope_source = "orgao"
