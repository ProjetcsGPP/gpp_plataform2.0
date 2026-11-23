"""
AppContextAuthentication

Authenticator leve que lê o request.user já populado pelo AppContextMiddleware.
Substitui o SessionAuthentication como default e preserva sua verificação de
CSRF para toda requisição autenticada por cookie.
"""

from rest_framework.authentication import BaseAuthentication

from common.authentication import enforce_csrf


class AppContextAuthentication(BaseAuthentication):
    """
    Lê request.user do objeto Django request original (_request),
    que já foi populado pelo AppContextMiddleware via AccountsSession.
    Como APIView é isenta do CsrfViewMiddleware por padrão, o check precisa
    acontecer aqui depois que a sessão multi-cookie foi autenticada.
    """

    def authenticate(self, request):
        user = getattr(request._request, "user", None)
        if user is None or not user.is_authenticated:
            return None
        enforce_csrf(request)
        return (user, None)

    def authenticate_header(self, request):
        return "Cookie"
