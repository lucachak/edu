from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("estabelecimentos", "0004_estabelecimento_codigo_convite"),
    ]

    operations = [
        migrations.AddField(
            model_name="estabelecimento",
            name="codigo_acesso",
            field=models.CharField(
                blank=True,
                help_text="Código que o cliente digita para encontrar a cantina. Ex.: SENAI01, CANT42.",
                max_length=20,
                null=True,
                unique=True,
                verbose_name="código de acesso para clientes",
            ),
        ),
    ]
