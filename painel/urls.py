from django.urls import path

from . import views

app_name = "painel"

urlpatterns = [
    path("", views.pedidos, name="pedidos"),
    path("pedidos/<int:pk>/status/", views.pedido_status, name="pedido_status"),
    path("pedidos/<int:pk>/pagamento-balcao/", views.pedido_pagamento_balcao, name="pedido_pagamento_balcao"),
    path("token/", views.token, name="token"),
    path("token/confirmar/", views.token_confirmar, name="token_confirmar"),
    path("itens/", views.itens, name="itens"),
    path("itens/<int:pk>/editar/", views.produto_editar, name="produto_editar"),
    path("itens/<int:pk>/remover/", views.produto_remover, name="produto_remover"),
    path("cardapio-especial/", views.especiais, name="especiais"),
    path("cardapio-especial/<int:pk>/remover/", views.especial_remover, name="especial_remover"),
    path("vendas/", views.vendas, name="vendas"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("codigo-cantina/novo/", views.regenerar_codigo_cantina, name="regenerar_codigo"),
    path("trocar-estabelecimento/", views.trocar_estabelecimento, name="trocar_estabelecimento"),
    path("funcionarios/", views.funcionarios_pendentes, name="funcionarios"),
    path("funcionarios/<int:pk>/aprovar/", views.aprovar_funcionario, name="aprovar_funcionario"),
]
