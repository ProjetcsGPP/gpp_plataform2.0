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
    app = registry.get("acoes_pngi")   # retorna Aplicacao ou None (case-insensitive)
    app = registry.get("ACOES_PNGI")   # equivalente
    apps = registry.all()               # retorna list[Aplicacao]

NORMALIZAÇÃO:
  O dict interno usa chaves sempre em maiúsculas.
  get() normaliza o argumento para maiúsculas antes da busca,
  tornando a pesquisa case-insensitive sem custo adicional.
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
        Case-insensitive — normaliza para maiúsculas internamente.
        """
        apps = self._load()
        return apps.get(codigo_interno.upper())

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
        Retorna dict { codigointerno.upper(): Aplicacao } — chaves sempre maiúsculas.
        """
        cached = cache.get(CACHE_KEY)
        if cached is not None:
            return cached

        from apps.accounts.models import Aplicacao

        # Normaliza chaves para maiúsculas para garantir lookup case-insensitive
        apps = {a.codigointerno.upper(): a for a in Aplicacao.objects.all()}
        cache.set(CACHE_KEY, apps, CACHE_TTL)

        logger.info("APP_REGISTRY_LOADED count=%s", len(apps))
        return apps
