"""Rotas WebSocket de Publicações Institucionais."""

from django.urls import path

from apps.pub_institucional.consumidores import ConsumidorEdocs

websocket_urlpatterns = [
    path("ws/pub-institucional/edocs/", ConsumidorEdocs.as_asgi()),
]
