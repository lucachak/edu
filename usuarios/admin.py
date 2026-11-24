from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import Usuario, Vinculo


class VinculoInline(admin.TabularInline):
    model = Vinculo
    extra = 0


@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    ordering = ("nome",)
    list_display = ("nome", "email", "permissao", "is_active", "is_staff")
    list_filter = ("permissao", "is_active", "is_staff")
    search_fields = ("nome", "email")
    readonly_fields = ("codigo_conta", "last_login", "date_joined")
    inlines = [VinculoInline]
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Dados pessoais", {"fields": ("nome", "data_nascimento", "cpf", "telefone", "codigo_conta")}),
        ("Permissões", {"fields": ("permissao", "is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Cliente", {"fields": ("estabelecimento_atual", "favoritos")}),
        ("Datas", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (None, {"classes": ("wide",), "fields": ("email", "nome", "permissao", "password1", "password2")}),
    )
    filter_horizontal = ("groups", "user_permissions", "favoritos")


@admin.register(Vinculo)
class VinculoAdmin(admin.ModelAdmin):
    list_display = ("usuario", "estabelecimento", "funcao", "ativo", "pode_gerenciar_produtos")
    list_filter = ("ativo", "estabelecimento")
