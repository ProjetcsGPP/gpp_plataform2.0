"""
Extensões OpenAPI para o drf-spectacular.
Registra o AppContextAuthentication como esquema de segurança via cookie.
"""
from drf_spectacular.extensions import OpenApiAuthenticationExtension


class AppContextAuthenticationExtension(OpenApiAuthenticationExtension):
    target_class = "apps.accounts.authentication.AppContextAuthentication"
    name = "gppSessionAuth"

    def get_security_definition(self, auto_schema):
        return {
            "type": "apiKey",
            "in": "cookie",
            "name": "gpp_session_{APP}",
            "description": (
                "Autenticação via cookie de sessão GPP. "
                "O nome do cookie varia por aplicação: "
                "`gpp_session_PORTAL`, `gpp_session_ACOES_PNGI`, etc. "
                "Obtenha o cookie fazendo POST em `/api/accounts/login/`."
            ),
        }
