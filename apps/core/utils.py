"""
GPP Plataform 2.0 — Accounts Utils
FASE-0: utilitários de suporte à autenticação via sessão.
"""


def get_client_ip(request):
    """
    Retorna o IP real do cliente, considerando proxies reversos.
    Prioriza o primeiro IP do cabeçalho X-Forwarded-For.
    """
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")
