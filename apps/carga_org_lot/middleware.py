from http.cookies import SimpleCookie

from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser
from django.db.models import Q
from django.utils import timezone

from apps.accounts.models import AccountsSession, UserRole


class AppSessionWebSocketMiddleware:
    """Autentica WebSocket usando os cookies multiaplicação do projeto."""

    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        scope = dict(scope)
        scope["user"], scope["app_context"] = await self._resolve(scope)
        return await self.inner(scope, receive, send)

    @database_sync_to_async
    def _resolve(self, scope):
        headers = dict(scope.get("headers", []))
        cookie = SimpleCookie()
        cookie.load(headers.get(b"cookie", b"").decode("latin1"))
        pairs = {
            name: morsel.value
            for name, morsel in cookie.items()
            if name.startswith("gpp_session_")
        }
        if not pairs:
            return AnonymousUser(), None

        preferred = "gpp_session_CARGA_ORG_LOT"
        if preferred in pairs:
            session = (
                AccountsSession.objects.filter(
                    session_key=pairs[preferred],
                    session_cookie_name=preferred,
                    app_context="CARGA_ORG_LOT",
                    revoked=False,
                    expires_at__gt=timezone.now(),
                )
                .select_related("user")
                .first()
            )
            if session:
                return session.user, "CARGA_ORG_LOT"

        query = Q()
        for name, value in pairs.items():
            query |= Q(session_cookie_name=name, session_key=value)
        session = (
            AccountsSession.objects.filter(
                query, revoked=False, expires_at__gt=timezone.now()
            )
            .select_related("user")
            .order_by("-created_at")
            .first()
        )
        if not session:
            return AnonymousUser(), None
        is_admin = session.user.is_superuser or UserRole.objects.filter(
            user=session.user,
            role__codigoperfil="PORTAL_ADMIN",
        ).exists()
        if not is_admin:
            return AnonymousUser(), None
        return session.user, "CARGA_ORG_LOT"
