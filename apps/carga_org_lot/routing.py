from django.urls import path

from .consumers import CargaOrgLotConsumer

websocket_urlpatterns = [
    path("ws/carga-org-lot/dashboard/", CargaOrgLotConsumer.as_asgi()),
    path(
        "ws/carga-org-lot/patriarcas/<int:patriarca_id>/",
        CargaOrgLotConsumer.as_asgi(),
    ),
    path(
        "ws/carga-org-lot/envios/<int:envio_id>/",
        CargaOrgLotConsumer.as_asgi(),
    ),
]
