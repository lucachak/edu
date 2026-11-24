from django.contrib import admin

from .models import estabelecimento


@admin.register(estabelecimento)
class EstabelecimentoAdmin(admin.ModelAdmin):
    list_display = ("nome", "codigo_acesso", "local", "ativo", "unique_id")
    list_filter = ("ativo",)
    search_fields = ("nome", "endereco", "codigo_acesso")
    readonly_fields = ("unique_id",)
