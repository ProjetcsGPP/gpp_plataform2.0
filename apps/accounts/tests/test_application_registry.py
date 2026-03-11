"""
Testes unitários do ApplicationRegistry.

Cobre:
  - Cache hit: não consulta o banco
  - Cache miss: carrega do banco e popula cache
  - Invalidate: limpa a chave de cache
"""
from unittest.mock import MagicMock, patch

from django.test import TestCase
from django.core.cache import cache

from apps.accounts.services.application_registry import (
    ApplicationRegistry,
    CACHE_KEY,
    CACHE_TTL,
)


class ApplicationRegistryTests(TestCase):

    def setUp(self):
        # Garante cache limpo antes de cada teste
        cache.clear()

    # ── Cache hit ─────────────────────────────────────────────────────────────

    def test_cache_hit(self):
        """
        Quando o cache já possui os dados, _load() deve retorná-los
        sem executar nenhuma query ao banco.
        """
        fake_app = MagicMock()
        fake_app.codigointerno = "acoes_pngi"
        cached_data = {"acoes_pngi": fake_app}
        cache.set(CACHE_KEY, cached_data, CACHE_TTL)

        registry = ApplicationRegistry()
        # Patching Aplicacao.objects.all para garantir que não é chamado
        with patch("apps.accounts.services.application_registry.cache.get",
                   wraps=cache.get) as mock_cache_get, \
             patch("apps.accounts.models.Aplicacao.objects") as mock_manager:

            result = registry.get("acoes_pngi")

        self.assertEqual(result, fake_app)
        mock_manager.all.assert_not_called()

    # ── Cache miss ────────────────────────────────────────────────────────────

    def test_cache_miss_loads_from_db(self):
        """
        Quando o cache está vazio, _load() deve consultar o banco e
        popular o cache com os dados carregados.
        """
        fake_app = MagicMock()
        fake_app.codigointerno = "portal"

        # Cache garantidamente vazio (setUp já limpou)
        with patch("apps.accounts.services.application_registry.Aplicacao") as MockAplicacao:
            MockAplicacao.objects.all.return_value = [fake_app]

            registry = ApplicationRegistry()
            result = registry.get("portal")

        self.assertEqual(result, fake_app)
        # Após o miss, o cache deve ter sido populado
        cached = cache.get(CACHE_KEY)
        self.assertIsNotNone(cached)
        self.assertIn("portal", cached)

    # ── Invalidate ────────────────────────────────────────────────────────────

    def test_invalidate_clears_cache(self):
        """
        invalidate() deve remover a chave do cache.
        Na próxima chamada _load() irá ao banco novamente.
        """
        fake_app = MagicMock()
        fake_app.codigointerno = "carga_org_lot"
        cache.set(CACHE_KEY, {"carga_org_lot": fake_app}, CACHE_TTL)

        registry = ApplicationRegistry()
        registry.invalidate()

        self.assertIsNone(cache.get(CACHE_KEY))

    # ── all() ─────────────────────────────────────────────────────────────────

    def test_all_returns_list(self):
        """all() deve retornar uma lista de todas as Aplicacoes."""
        app1 = MagicMock(codigointerno="app1")
        app2 = MagicMock(codigointerno="app2")
        cache.set(CACHE_KEY, {"app1": app1, "app2": app2}, CACHE_TTL)

        registry = ApplicationRegistry()
        result = registry.all()

        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 2)
        self.assertIn(app1, result)
        self.assertIn(app2, result)

    # ── get() com chave inexistente ───────────────────────────────────────────

    def test_get_unknown_returns_none(self):
        """get() com código inexistente deve retornar None."""
        cache.set(CACHE_KEY, {"portal": MagicMock()}, CACHE_TTL)
        registry = ApplicationRegistry()
        self.assertIsNone(registry.get("nao_existe"))
