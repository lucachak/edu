from django.contrib import admin

from .models import EventoPagamento, item_pedido, pagamento, pedido, retirada


class ItemInline(admin.TabularInline):
    model = item_pedido
    extra = 0
    readonly_fields = ("produto", "nome_produto", "quantidade", "preco_unitario", "disponibilidade")
    can_delete = False


@admin.register(pedido)
class PedidoAdmin(admin.ModelAdmin):
    """Somente leitura dos campos sensíveis: status muda pelas regras do sistema."""

    list_display = ("id", "usuario", "estabelecimento", "status", "valor_total", "token_retirada", "data_pedido")
    list_filter = ("status", "estabelecimento")
    search_fields = ("id", "token_retirada", "usuario__email")
    readonly_fields = (
        "usuario", "estabelecimento", "codigo", "subtotal", "taxa_servico", "valor_total", "status",
        "token_retirada", "reserva_expira_em", "confirmado_em", "cancelado_em", "motivo_cancelamento",
        "data_disponibilidade", "metodo_pagamento",
    )
    inlines = [ItemInline]


@admin.register(pagamento)
class PagamentoAdmin(admin.ModelAdmin):
    list_display = ("pedido", "provedor", "metodo_pagamento", "status", "status_provedor", "valor_pago", "pago_em")
    list_filter = ("provedor", "status")
    readonly_fields = [f.name for f in pagamento._meta.fields]


@admin.register(EventoPagamento)
class EventoAdmin(admin.ModelAdmin):
    list_display = ("pagamento", "origem", "autenticado", "status_provedor", "recebido_em")
    readonly_fields = ("pagamento", "origem", "autenticado", "status_provedor", "payload", "recebido_em")


@admin.register(retirada)
class RetiradaAdmin(admin.ModelAdmin):
    list_display = ("pedido", "data_retirada", "confirmado_por", "token_utilizado")
    readonly_fields = ("pedido", "data_retirada", "confirmado_por", "token_utilizado", "local_retirada")
