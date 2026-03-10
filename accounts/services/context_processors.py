# accounts/context_processors.py
from accounts.models import UserRole


def active_role_context(request):
    """
    Adiciona informações do papel ativo ao contexto do template
    """
    context = {
        "active_role": None,
        "active_role_name": None,
        "user_roles_for_app": [],
        "app_code": None,
    }

    if not request.user.is_authenticated:
        return context

    # Detectar o app_code da URL baseado no namespace
    app_code = None
    if hasattr(request, "resolver_match") and request.resolver_match:
        namespace = request.resolver_match.namespace

        # Mapear namespace para código da aplicação
        namespace_to_code = {
            "acoes_pngi_web": "ACOES_PNGI",
            "carga_org_lot_web": "CARGA_ORG_LOT",
            "portal": "PORTAL",
        }

        app_code = namespace_to_code.get(namespace)

    context["app_code"] = app_code

    if not app_code:
        return context

    # Buscar papel ativo na sessão
    session_key = f"active_role_{app_code}"
    active_role_id = request.session.get(session_key)

    if active_role_id:
        try:
            user_role = UserRole.objects.select_related("role", "aplicacao").get(
                id=active_role_id, user=request.user
            )
            context["active_role"] = user_role
            context["active_role_name"] = user_role.role.nomeperfil
        except UserRole.DoesNotExist:
            # Papel não existe mais, limpar sessão
            if session_key in request.session:
                del request.session[session_key]

    # Buscar todos os papéis do usuário para este app
    if app_code:
        from accounts.models import Aplicacao

        try:
            aplicacao = Aplicacao.objects.get(codigointerno=app_code)
            context["user_roles_for_app"] = UserRole.objects.filter(
                user=request.user, aplicacao=aplicacao
            ).select_related("role")
        except Aplicacao.DoesNotExist:
            pass

    return context
