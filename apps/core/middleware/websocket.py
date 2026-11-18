"""Autenticação profunda da plataforma para conexões WebSocket."""

from http.cookies import SimpleCookie

from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser
from django.db.models import Q
from django.utils import timezone

from apps.accounts.models import AccountsSession, UserRole


class MiddlewareSessaoAplicacaoWebSocket:
    """Resolve a sessão pelo contexto associado ao prefixo da rota."""

    def __init__(self, aplicacao, *, contextos_por_prefixo):
        self.aplicacao = aplicacao
        self.contextos_por_prefixo = {
            prefixo.strip("/"): contexto
            for prefixo, contexto in contextos_por_prefixo.items()
        }

    async def __call__(self, escopo, receber, enviar):
        escopo = dict(escopo)
        escopo["user"], escopo["app_context"] = await self._resolver(escopo)
        return await self.aplicacao(escopo, receber, enviar)

    @database_sync_to_async
    def _resolver(self, escopo):
        contexto = self._obter_contexto(escopo.get("path", ""))
        if contexto is None:
            return AnonymousUser(), None

        cabecalhos = dict(escopo.get("headers", []))
        cookies = SimpleCookie()
        cookies.load(cabecalhos.get(b"cookie", b"").decode("latin1"))
        pares = {
            nome: item.value
            for nome, item in cookies.items()
            if nome.startswith("gpp_session_")
        }
        if not pares:
            return AnonymousUser(), contexto

        nome_cookie = f"gpp_session_{contexto}"
        if nome_cookie in pares:
            sessao = (
                AccountsSession.objects.filter(
                    session_key=pares[nome_cookie],
                    session_cookie_name=nome_cookie,
                    app_context=contexto,
                    revoked=False,
                    expires_at__gt=timezone.now(),
                )
                .select_related("user")
                .first()
            )
            if sessao:
                return sessao.user, contexto

        consulta = Q()
        for nome, valor in pares.items():
            consulta |= Q(session_cookie_name=nome, session_key=valor)
        sessao = (
            AccountsSession.objects.filter(
                consulta,
                revoked=False,
                expires_at__gt=timezone.now(),
                app_context__isnull=False,
            )
            .select_related("user")
            .order_by("-created_at")
            .first()
        )
        if not sessao:
            return AnonymousUser(), contexto
        administrador = sessao.user.is_superuser or UserRole.objects.filter(
            user=sessao.user,
            role__codigoperfil="PORTAL_ADMIN",
        ).exists()
        if not administrador:
            return AnonymousUser(), contexto
        return sessao.user, contexto

    def _obter_contexto(self, caminho):
        caminho = caminho.strip("/")
        for prefixo, contexto in self.contextos_por_prefixo.items():
            if caminho.startswith(prefixo):
                return contexto
        return None
