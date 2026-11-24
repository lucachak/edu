import django.core.validators
import django.utils.timezone
from django.contrib.auth.hashers import make_password
from django.db import migrations, models
import django.db.models.deletion
import produtos.models
from decimal import Decimal


def criar_cantina_demo(apps, schema_editor):
    Estabelecimento = apps.get_model("estabelecimentos", "estabelecimento")
    Usuario = apps.get_model("usuarios", "Usuario")
    Vinculo = apps.get_model("usuarios", "Vinculo")
    Categoria = apps.get_model("produtos", "Categoria")
    Produto = apps.get_model("produtos", "Produto")
    CardapioEspecial = apps.get_model("produtos", "CardapioEspecial")

    cantina, _ = Estabelecimento.objects.get_or_create(
        codigo_convite="FASTLINE-DEMO-2026",
        defaults={
            "nome": "Cantina Demonstração FastLine",
            "endereco": "Unidade de demonstração",
            "local": "Balcão principal",
            "descricao": "Cantina de demonstração do projeto FastLine.",
            "ativo": True,
        },
    )
    gerente, criado = Usuario.objects.get_or_create(
        email="gerente@fastline.demo",
        defaults={
            "nome": "Gerente da Cantina Demo",
            "password": make_password("FastLineDemo2026!"),
            "permissao": "funcionario",
            "is_active": True,
            "is_staff": False,
            "is_superuser": False,
            "date_joined": django.utils.timezone.now(),
        },
    )
    Vinculo.objects.get_or_create(
        usuario=gerente,
        estabelecimento=cantina,
        defaults={"funcao": "gerente", "ativo": True, "pode_gerenciar_produtos": True},
    )
    salgados, _ = Categoria.objects.get_or_create(estabelecimento=cantina, nome="Salgados", defaults={"ordem": 1})
    bebidas, _ = Categoria.objects.get_or_create(estabelecimento=cantina, nome="Bebidas", defaults={"ordem": 2})
    demo_produtos = [
        ("Coxinha de frango", "Massa macia com recheio de frango.", Decimal("6.00"), salgados, "demo/coxinha.jpg"),
        ("Esfirra", "Esfirra assada para o intervalo.", Decimal("5.50"), salgados, "demo/esfirra.jpg"),
        ("Suco de laranja", "Suco gelado.", Decimal("4.00"), bebidas, "demo/suco-laranja.jpg"),
    ]
    for nome, descricao, preco, categoria, imagem in demo_produtos:
        Produto.objects.get_or_create(estabelecimento=cantina, nome=nome, defaults={"descricao": descricao, "preco": preco, "categoria": categoria, "imagem": imagem, "ativo": True})
    CardapioEspecial.objects.get_or_create(estabelecimento=cantina, titulo="Almoço de demonstração", data=django.utils.timezone.localdate(), defaults={"descricao": "Arroz, feijão, frango grelhado e salada.", "imagem": "demo/almoco.jpg", "preco": Decimal("18.00"), "ativo": True})


class Migration(migrations.Migration):
    dependencies = [
    ("estabelecimentos", "0004_estabelecimento_codigo_convite"),
    ("usuarios", "0004_usuario_autenticacao_segura"),
    ("produtos", "0003_cardapioespecial_imagem_cardapioespecial_preco"),
    ("pedidos", "0002_status_token_pagseguro"),
]
    operations = [
        migrations.AddField(
            model_name="pedido",
            name="token_expira_em",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="pagamento",
            name="metodo_pagamento",
            field=models.CharField(choices=[("pix", "PIX"), ("cartao", "Cartão"), ("cartao_credito", "Cartão de crédito"), ("cartao_debito", "Cartão de débito"), ("dinheiro", "Dinheiro"), ("balcao", "Pagamento no balcão"), ("simulado", "Pagamento simulado (demonstração)")], max_length=20),
        ),
        migrations.AlterField(
            model_name="pagamento",
            name="provedor",
            field=models.CharField(choices=[("pagseguro", "PagSeguro"), ("balcao", "Balcão (confirmado por funcionário)"), ("simulador", "Simulador (demonstração)")], default="pagseguro", max_length=20),
        ),
        migrations.RunPython(criar_cantina_demo, migrations.RunPython.noop),
    ]
