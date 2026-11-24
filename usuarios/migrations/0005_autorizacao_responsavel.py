from datetime import date

from django.db import migrations, models


def preservar_contas_existentes(apps, schema_editor):
    Usuario = apps.get_model("usuarios", "Usuario")
    hoje = date.today()
    for usuario in Usuario.objects.all().iterator():
        nascimento = usuario.data_nascimento
        if nascimento:
            idade = hoje.year - nascimento.year - ((hoje.month, hoje.day) < (nascimento.month, nascimento.day))
            if idade < 17:
                usuario.responsavel_confirmado = False
                usuario.save(update_fields=["responsavel_confirmado"])


class Migration(migrations.Migration):
    dependencies = [
        ("usuarios", "0004_usuario_autenticacao_segura"),
    ]

    operations = [
        migrations.AddField(
            model_name="usuario",
            name="email_responsavel",
            field=models.EmailField(blank=True, max_length=254, verbose_name="e-mail do responsável"),
        ),
        migrations.AddField(
            model_name="usuario",
            name="responsavel_confirmado",
            field=models.BooleanField(default=True),
        ),
        migrations.RunPython(preservar_contas_existentes, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="usuario",
            name="responsavel_confirmado",
            field=models.BooleanField(default=False),
        ),
    ]
