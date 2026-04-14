"""
AppContextAuthentication

Authenticator leve que lê o request.user já populado pelo AppContextMiddleware.
Substitui o SessionAuthentication como default, eliminando o CSRF check do DRF
em todas as views — o CSRF já é tratado pelo CsrfViewMiddleware do Django.
"""
from rest_framework.authentication import BaseAuthentication


class AppContextAuthentication(BaseAuthentication):
    """
    Lê request.user do objeto Django request original (_request),
    que já foi populado pelo AppContextMiddleware via AccountsSession.
    Não faz CSRF check — isso é responsabilidade do CsrfViewMiddleware.
    """
    def authenticate(self, request):
        user = getattr(request._request, "user", None)
        if user is None or not user.is_authenticated:
            return None
        return (user, None)

    def authenticate_header(self, request):
        return "Cookie"
