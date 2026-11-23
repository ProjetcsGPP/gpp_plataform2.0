"""Adaptador temporário para a autorização IAM no processo monolítico.

Esta interface reúne os pontos de entrada HTTP e WebSocket das aplicações.
Não é um contrato de comunicação entre serviços: o transporte, a prova de
identidade e o tratamento de indisponibilidade ainda dependem do gate I2.
"""

from apps.accounts.services.application_registry import ApplicationRegistry
from apps.accounts.services.authorization_service import AuthorizationService


def obter_aplicacao(codigo_interno):
    """Resolve uma aplicação pelo cadastro autoritativo atual."""
    return ApplicationRegistry().get(codigo_interno)


def autorizar(usuario, permissao, *, aplicacao=None, contexto=None):
    """Preserva a decisão e a auditoria do AuthorizationService existente."""
    return AuthorizationService(usuario, aplicacao).can(permissao, context=contexto)
