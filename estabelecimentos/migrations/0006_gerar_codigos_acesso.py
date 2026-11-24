"""Gera um código de acesso para cada cantina que ainda não tem um.

Migração só de dados: não apaga nada. Códigos já cadastrados são mantidos,
apenas normalizados para maiúsculas.
"""

import re
import secrets

from django.db import migrations

ALFABETO = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


def gerar_codigos(apps, schema_editor):
    Estabelecimento = apps.get_model("estabelecimentos", "estabelecimento")
    usados = {
        (c or "").upper()
        for c in Estabelecimento.objects.exclude(codigo_acesso__isnull=True).values_list("codigo_acesso", flat=True)
    }
    for cantina in Estabelecimento.objects.all():
        atual = re.sub(r"[^A-Za-z0-9]", "", cantina.codigo_acesso or "").upper()
        if not atual:
            while True:
                atual = "".join(secrets.choice(ALFABETO) for _ in range(6))
                if atual not in usados:
                    break
        usados.add(atual)
        if atual != cantina.codigo_acesso:
            cantina.codigo_acesso = atual
            cantina.save(update_fields=["codigo_acesso"])


class Migration(migrations.Migration):

    dependencies = [
        ("estabelecimentos", "0005_estabelecimento_codigo_acesso"),
    ]

    operations = [
        migrations.RunPython(gerar_codigos, migrations.RunPython.noop),
    ]
