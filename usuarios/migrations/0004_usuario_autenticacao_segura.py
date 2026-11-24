"""Transforma ``Usuario`` em usuário de autenticação do Django.

O modelo da migração 0003 guardava a senha em texto puro (campo ``senha``)
e não podia ser usado pelo login do Django. Esta migração:

* adiciona os campos de autenticação (password com hash, last_login,
  is_superuser, is_staff, is_active, date_joined, grupos e permissões);
* converte qualquer senha existente em texto puro para hash seguro antes de
  remover o campo antigo (o banco original não tinha usuários, mas a
  conversão garante que nenhum dado seja perdido);
* adiciona CPF, telefone, cantina selecionada e favoritos.
"""

import django.utils.timezone
from django.contrib.auth.hashers import make_password
from django.db import migrations, models

import usuarios.models


def converter_senhas(apps, schema_editor):
    Usuario = apps.get_model("usuarios", "Usuario")
    for usuario in Usuario.objects.all():
        usuario.password = make_password(usuario.senha or None)
        usuario.save(update_fields=["password"])


class Migration(migrations.Migration):

    dependencies = [
        ("auth", "0012_alter_user_first_name_max_length"),
        ("estabelecimentos", "0002_alter_estabelecimento_unique_id"),
        ("usuarios", "0003_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="usuario",
            name="password",
            field=models.CharField(default="", max_length=128, verbose_name="password"),
            preserve_default=False,
        ),
        migrations.RunPython(converter_senhas, migrations.RunPython.noop),
        migrations.RemoveField(model_name="usuario", name="senha"),
        migrations.AlterModelOptions(
            name="usuario",
            options={"verbose_name": "usuário", "verbose_name_plural": "usuários"},
        ),
        migrations.AlterModelOptions(
            name="vinculo",
            options={"verbose_name": "vínculo", "verbose_name_plural": "vínculos"},
        ),
        migrations.AlterModelManagers(
            name="usuario",
            managers=[("objects", usuarios.models.UsuarioManager())],
        ),
        migrations.AddField(
            model_name="usuario",
            name="last_login",
            field=models.DateTimeField(blank=True, null=True, verbose_name="last login"),
        ),
        migrations.AddField(
            model_name="usuario",
            name="is_superuser",
            field=models.BooleanField(
                default=False,
                help_text="Designates that this user has all permissions without explicitly assigning them.",
                verbose_name="superuser status",
            ),
        ),
        migrations.AddField(
            model_name="usuario",
            name="is_active",
            field=models.BooleanField(default=True, verbose_name="ativo"),
        ),
        migrations.AddField(
            model_name="usuario",
            name="is_staff",
            field=models.BooleanField(
                default=False, help_text="Permite entrar no /admin/ técnico do Django.",
                verbose_name="acesso ao admin do Django",
            ),
        ),
        migrations.AddField(
            model_name="usuario",
            name="date_joined",
            field=models.DateTimeField(default=django.utils.timezone.now, verbose_name="cadastrado em"),
        ),
        migrations.AddField(
            model_name="usuario",
            name="groups",
            field=models.ManyToManyField(
                blank=True,
                help_text="The groups this user belongs to. A user will get all permissions granted to each of their groups.",
                related_name="user_set", related_query_name="user", to="auth.group", verbose_name="groups",
            ),
        ),
        migrations.AddField(
            model_name="usuario",
            name="user_permissions",
            field=models.ManyToManyField(
                blank=True, help_text="Specific permissions for this user.",
                related_name="user_set", related_query_name="user", to="auth.permission",
                verbose_name="user permissions",
            ),
        ),
        migrations.AddField(
            model_name="usuario",
            name="cpf",
            field=models.CharField(
                blank=True, help_text="Somente números. Exigido pelo PagSeguro para gerar cobranças.",
                max_length=11, verbose_name="CPF",
            ),
        ),
        migrations.AddField(
            model_name="usuario",
            name="telefone",
            field=models.CharField(blank=True, max_length=20),
        ),
        migrations.AddField(
            model_name="usuario",
            name="estabelecimento_atual",
            field=models.ForeignKey(
                blank=True, help_text="Cantina selecionada pelo cliente para comprar.", null=True,
                on_delete=models.deletion.SET_NULL, related_name="+", to="estabelecimentos.estabelecimento",
            ),
        ),
        migrations.AddField(
            model_name="usuario",
            name="favoritos",
            field=models.ManyToManyField(
                blank=True, related_name="favoritado_por", to="estabelecimentos.estabelecimento",
            ),
        ),
        migrations.AlterField(
            model_name="usuario",
            name="data_nascimento",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="vinculo",
            name="criado_em",
            field=models.DateTimeField(auto_now_add=True, null=True),
        ),
        migrations.AddField(
            model_name="vinculo",
            name="pode_gerenciar_produtos",
            field=models.BooleanField(
                default=True, help_text="Permite cadastrar/editar produtos e disponibilidade.",
            ),
        ),
        migrations.AddConstraint(
            model_name="vinculo",
            constraint=models.UniqueConstraint(
                fields=("usuario", "estabelecimento"), name="vinculo_unico_por_estabelecimento",
            ),
        ),
    ]
