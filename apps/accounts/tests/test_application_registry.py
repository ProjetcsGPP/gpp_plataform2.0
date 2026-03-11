"""
Testes unitários do ApplicationRegistry.

Cobre:
  - Cache hit: não consulta o banco
  - Cache miss: carrega do banco e popula cache
  - Invalidate: limpa a chave de cache

Estratégia de isolamento:
  - MagicMock NÃO é picklável → não pode ser inserido no cache locmem do Django.
  - Solução: patch do cache.get/cache.set para operar em memória pura (dict),
    ou uso de instâncias reais de Aplicacao via banco de testes.
  - Para cache hit/miss: patchamos cache.get e cache.set diretamente,
    devolvendo/armazenando valores em um dict local (sem pickle).
  - Para testes de invalidate e all(): usamos Aplicacao real do banco de testes.
  - O patch de Aplicacao.objects.all deve apontar para
    'apps.accounts.models.Aplicacao' (onde a classe reside),
    pois _load() a importa localmente com `from apps.accounts.models import Aplicacao`.
"""
from unittest.mock import MagicMock, patch, call

from django.contrib.auth.models import Group
from django.test import TestCase
from django.core.cache import cache

from apps.accounts.models import Aplicacao
from apps.accounts.services.application_registry import (
    ApplicationRegistry,
    CACHE_KEY,
    CACHE_TTL,
)


class ApplicationRegistryTests(TestCase):

    def setUp(self):
        cache.clear()

    # ── Cache hit ─────────────────────────────────────────────────────────────

    def test_cache_hit(self):
        """
        Quando o cache já possui os dados, _load() deve retorná-los
        sem executar nenhuma query ao banco.
        O patch substitui cache.get por um dict local para evitar PicklingError.
        """
        fake_app = MagicMock()
        fake_app.codigointerno = "acoes_pngi"
        fake_cache_store = {CACHE_KEY: {"acoes_pngi": fake_app}}

        def mock_cache_get(key, default=None):
            return fake_cache_store.get(key, default)

        registry = ApplicationRegistry()

        with patch("apps.accounts.services.application_registry.cache.get",
                   side_effect=mock_cache_get), \
             patch("apps.accounts.models.Aplicacao.objects") as mock_manager:

            result = registry.get("acoes_pngi")

        self.assertEqual(result, fake_app)
        mock_manager.all.assert_not_called()

    # ── Cache miss ────────────────────────────────────────────────────────────

    def test_cache_miss_loads_from_db(self):
        """
        Quando o cache está vazio, _load() deve consultar o banco e
        popular o cache com os dados carregados.

        Patch correto: 'apps.accounts.models.Aplicacao' — onde a classe reside.
        _load() usa `from apps.accounts.models import Aplicacao` localmente.
        """
        fake_app = MagicMock()
        fake_app.codigointerno = "portal"

        captured_cache = {}

        def mock_cache_get(key, default=None):
            return captured_cache.get(key, default)

        def mock_cache_set(key, value, timeout=None):
            captured_cache[key] = value

        with patch("apps.accounts.services.application_registry.cache.get",
                   side_effect=mock_cache_get), \
             patch("apps.accounts.services.application_registry.cache.set",
                   side_effect=mock_cache_set), \
             patch("apps.accounts.models.Aplicacao.objects") as mock_manager:

            mock_manager.all.return_value = [fake_app]

            registry = ApplicationRegistry()
            result = registry.get("portal")

        self.assertEqual(result, fake_app)
        mock_manager.all.assert_called_once()
        # Cache deve ter sido populado após o miss
        self.assertIn(CACHE_KEY, captured_cache)
        self.assertIn("portal", captured_cache[CACHE_KEY])

    # ── Invalidate ────────────────────────────────────────────────────────────

    def test_invalidate_clears_cache(self):
        """
        invalidate() deve remover a chave do cache.
        Usa Aplicacao real para poder inserir no cache sem PicklingError.
        """
        app = Aplicacao.objects.create(
            codigointerno="carga_org_lot",
            nomeaplicacao="Carga Org Lot",
        )
        # Popula o cache com instância real (picklável)
        cache.set(CACHE_KEY, {"carga_org_lot": app}, CACHE_TTL)
        self.assertIsNotNone(cache.get(CACHE_KEY))

        registry = ApplicationRegistry()
        registry.invalidate()

        self.assertIsNone(cache.get(CACHE_KEY))

    # ── all() ─────────────────────────────────────────────────────────────────

    def test_all_returns_list(self):
        """
        all() deve retornar uma lista de todas as Aplicacoes.
        Usa instâncias reais para evitar PicklingError no cache locmem.
        """
        app1 = Aplicacao.objects.create(codigointerno="app1", nomeaplicacao="App 1")
        app2 = Aplicacao.objects.create(codigointerno="app2", nomeaplicacao="App 2")

        registry = ApplicationRegistry()
        result = registry.all()

        self.assertIsInstance(result, list)
        ids_result = [a.codigointerno for a in result]
        self.assertIn("app1", ids_result)
        self.assertIn("app2", ids_result)

    # ── get() com chave inexistente ───────────────────────────────────────────

    def test_get_unknown_returns_none(self):
        """
        get() com código inexistente deve retornar None.
        Usa instância real no cache para evitar PicklingError.
        """
        app = Aplicacao.objects.create(codigointerno="portal", nomeaplicacao="Portal")
        cache.set(CACHE_KEY, {"portal": app}, CACHE_TTL)

        registry = ApplicationRegistry()
        self.assertIsNone(registry.get("nao_existe"))
