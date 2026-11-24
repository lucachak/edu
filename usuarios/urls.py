from django.urls import path

from . import views

app_name = "usuarios"

urlpatterns = [
    path("entrar/", views.entrar, name="login"),
    path("cadastro/", views.cadastro, name="cadastro"),
    path("cadastro-funcionario/", views.cadastro_funcionario, name="cadastro_funcionario"),
    path("confirmar-responsavel/<str:token>/", views.confirmar_responsavel, name="confirmar_responsavel"),
    path("vincular-cantina/", views.vincular_cantina, name="vincular_cantina"),
    path("sair/", views.sair, name="logout"),
    path("minha-conta/", views.perfil, name="perfil"),
    path("minha-conta/senha/", views.alterar_senha, name="senha"),
]
