from django.contrib import admin

from .models import CardapioEspecial, Categoria, DisponibilidadeOnline, Produto, movimentacao


@admin.register(Categoria)
class CategoriaAdmin(admin.ModelAdmin):
    list_display = ("nome", "estabelecimento", "ordem")
    list_filter = ("estabelecimento",)


@admin.register(Produto)
class ProdutoAdmin(admin.ModelAdmin):
    list_display = ("nome", "estabelecimento", "categoria", "preco", "ativo")
    list_filter = ("estabelecimento", "ativo")
    search_fields = ("nome",)


@admin.register(DisponibilidadeOnline)
class DisponibilidadeAdmin(admin.ModelAdmin):
    list_display = ("produto", "data", "quantidade_ofertada", "quantidade_comprometida")
    list_filter = ("data", "produto__estabelecimento")
    readonly_fields = ("quantidade_comprometida",)


@admin.register(CardapioEspecial)
class CardapioEspecialAdmin(admin.ModelAdmin):
    list_display = ("titulo", "estabelecimento", "data", "ativo")


@admin.register(movimentacao)
class MovimentacaoAdmin(admin.ModelAdmin):
    list_display = ("produto", "tipo_movimentacao", "funcionario", "data_movimentacao", "detalhe")
    list_filter = ("tipo_movimentacao",)
