from django.http import JsonResponse
from django.urls import path


def health_check(request):
    """Vivacidade do processo; não verifica banco, IAM nem integrações."""
    response = JsonResponse({"status": "ok", "service": "gpp_plataform2"})
    response["Cache-Control"] = "no-store"
    return response


urlpatterns = [
    path("", health_check, name="health_check"),
]
