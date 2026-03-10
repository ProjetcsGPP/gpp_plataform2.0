"""
ApplicationRegistry

Responsabilidade:
  Cache de todas as Aplicacoes da plataforma.
  Evita query ao banco a cada request para identificar a aplicação.

Estratégia de cache:
  - Chave: app_registry:all
  - TTL:   600s (10 minutos)
  - Invalidação: signal post_save/post_delete em Aplicacao
    (implementado em apps/accounts/signals.py)

Uso:
    registry = ApplicationRegistry()
    app = registry.get("acoes_pngi")   # retorna Aplicacao ou None
    apps = registry.all()               # retorna list[Aplicacao]
"""
import logging

from django.core.cache import cache

logger = logging.getLogger("gpp.security")

CACHE_KEY = "app_registry:all"
CACHE_TTL = 600  # 10 minutos


class ApplicationRegistry:
    def get(self, codigo_interno: str):
        """
        Retorna a Aplicacao com o codigointerno fornecido, ou None.
        """
        apps = self._load()
        return apps.get(codigo_interno)

    def all(self):
        """
        Retorna lista de todas as Aplicacoes.
        """
        return list(self._load().values())

    def invalidate(self):
        """
        Invalida o cache. Chamado pelos signals do accounts.
        """
        cache.delete(CACHE_KEY)
        logger.info("APP_REGISTRY_INVALIDATED")

    def _load(self) -> dict:
        """
        Carrega do cache ou banco.
        Retorna dict { codigointerno: Aplicacao }.
        """
        cached = cache.get(CACHE_KEY)
        if cached is not None:
            return cached

        from apps.accounts.models import Aplicacao

        apps = {a.codigointerno: a for a in Aplicacao.objects.all()}
        cache.set(CACHE_KEY, apps, CACHE_TTL)

        logger.info("APP_REGISTRY_LOADED count=%s", len(apps))
        return apps
