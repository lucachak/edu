from django.urls import path

from . import views

app_name = "estabelecimentos"

urlpatterns = [
    path("", views.escolher, name="escolher"),
    path("buscar/", views.buscar_por_codigo, name="buscar"),
    path("<uuid:unique_id>/detalhes/", views.detalhes, name="detalhes"),
    path("<uuid:unique_id>/selecionar/", views.selecionar, name="selecionar"),
    path("<uuid:unique_id>/favorito/", views.alternar_favorito, name="favorito"),
]
