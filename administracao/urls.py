from django.urls import path

from . import views

app_name = "administracao"

urlpatterns = [
    path("", views.painel, name="painel"),
    path("estabelecimentos/", views.estabelecimentos, name="estabelecimentos"),
    path("estabelecimentos/novo/", views.estabelecimento_form, name="estabelecimento_novo"),
    path("estabelecimentos/<uuid:unique_id>/editar/", views.estabelecimento_form, name="estabelecimento_editar"),
    path("estabelecimentos/<uuid:unique_id>/ativo/", views.estabelecimento_ativo, name="estabelecimento_ativo"),
    path("usuarios/", views.usuarios, name="usuarios"),
    path("usuarios/novo/", views.usuario_form, name="usuario_novo"),
    path("usuarios/<int:pk>/", views.usuario_form, name="usuario_editar"),
    path("usuarios/<int:pk>/vinculos/", views.vinculo_adicionar, name="vinculo_adicionar"),
    path("vinculos/<int:pk>/alternar/", views.vinculo_alternar, name="vinculo_alternar"),
    path("vinculos/<int:pk>/remover/", views.vinculo_remover, name="vinculo_remover"),
]
