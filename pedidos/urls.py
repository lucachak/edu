from django.urls import path

from . import views

app_name = "pedidos"

urlpatterns = [
    path("carrinho/", views.carrinho, name="carrinho"),
    path("carrinho/adicionar/<int:produto_id>/", views.carrinho_adicionar, name="carrinho_adicionar"),
    path("carrinho/atualizar/<int:produto_id>/", views.carrinho_atualizar, name="carrinho_atualizar"),
    path("carrinho/remover/<int:produto_id>/", views.carrinho_remover, name="carrinho_remover"),
    path("checkout/", views.checkout, name="checkout"),
    path("checkout/confirmar/", views.checkout_confirmar, name="checkout_confirmar"),
    path("meus-tickets/", views.tickets, name="tickets"),
    path("pedido/<uuid:codigo>/pagamento/", views.pagamento, name="pagamento"),
    path("pedido/<uuid:codigo>/pagamento/novo/", views.tentar_novamente, name="tentar_novamente"),
    path("pedido/<uuid:codigo>/retorno/", views.retorno, name="retorno"),
    path("pedido/<uuid:codigo>/status/", views.status_pedido, name="status"),
    path("pedido/<uuid:codigo>/confirmado/", views.confirmado, name="confirmado"),
    path("pedido/<uuid:codigo>/cancelar/", views.cancelar, name="cancelar"),
    path("pagamentos/webhook/pagseguro/", views.webhook_pagseguro, name="webhook_pagseguro"),
]
