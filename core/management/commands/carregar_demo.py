"""Cria dados FICTÍCIOS para demonstração do FastLine.

Nada aqui é credencial real. Os pedidos históricos são marcados como pagos
"no balcão" (provedor ``balcao``) para alimentar o dashboard; nenhum deles
finge ter passado pelo PagSeguro.

Uso:  python manage.py carregar_demo
O comando é idempotente: pode ser executado de novo sem duplicar dados.
"""

import random
import shutil
from datetime import datetime, time, timedelta
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from estabelecimentos.models import estabelecimento as Estabelecimento
from pedidos.models import (
    StatusPagamento,
    StatusPedido,
    gerar_token_retirada,
    item_pedido,
    pagamento as Pagamento,
    pedido as Pedido,
    retirada as Retirada,
)
from produtos.models import CardapioEspecial, Categoria, DisponibilidadeOnline, Produto
from usuarios.models import Permissao, Usuario, Vinculo

SENHA_DEMO = "FastLine@2026"

CANTINAS = [
    {
        "nome": "Cantina Principal", "local": "Térreo", "endereco": "SENAI - Roberto Simonsen",
        "email": "cantina1@escola.edu.br", "identificacao": "CANT-001",
        "descricao": "Salgados assados e fritos, bebidas e lanches rápidos.",
        "abre": time(7, 0), "fecha": time(21, 30),
    },
    {
        "nome": "Cantina Secundária", "local": "5º Andar", "endereco": "SENAI - Roberto Simonsen",
        "email": "cantina2@escola.edu.br", "identificacao": "CANT-002",
        "descricao": "Cafés, sucos naturais e doces.",
        "abre": time(8, 0), "fecha": time(18, 0),
    },
]

# (nome, categoria, preço, imagem, quantidade ofertada hoje, descrição)
PRODUTOS = {
    "Cantina Principal": [
        ("Coxinha de Frango", "Salgado", "5.00", "coxinha.jpg", 20, "Coxinha frita com recheio de frango desfiado."),
        ("Bauru", "Salgado", "6.50", "bauru.jpg", 15, "Massa folhada com presunto, queijo e tomate."),
        ("Esfirra de Frango", "Salgado", "6.00", "esfirra.jpg", 12, "Esfirra aberta de frango."),
        ("Croissant", "Salgado", "6.50", "croissant.jpg", 3, "Croissant de chocolate."),
        ("Refrigerante 350ml", "Bebida em Lata", "7.00", "coca-cola.jpg", 24, "Cola gelada em lata."),
        ("Guaraná 350ml", "Bebida em Lata", "7.00", "guarana.jpg", 0, "Guaraná gelado em lata."),
        ("Suco de Laranja", "Suco", "2.50", "suco-laranja.jpg", 10, "Suco natural de laranja, 300ml."),
        ("Suco de Limão", "Suco", "2.50", "suco-limao.jpg", 10, "Limonada natural, 300ml."),
        ("Brigadeiro", "Sobremesa", "4.00", None, 30, "Brigadeiro gourmet."),
    ],
    "Cantina Secundária": [
        ("Croissant", "Salgado", "6.50", "croissant.jpg", 8, "Croissant de chocolate."),
        ("Pão de Queijo", "Salgado", "1.80", None, 40, "Porção individual."),
        ("Suco de Laranja", "Suco", "2.50", "suco-laranja.jpg", 15, "Suco natural de laranja, 300ml."),
        ("Café Expresso", "Bebida", "4.00", None, 50, "Café 100% arábica."),
    ],
}

FUNCIONARIOS = [
    ("Marina Operadora", "funcionario@fastline.dev", "Cantina Principal", "Atendente"),
    ("Paulo Secundária", "funcionario2@fastline.dev", "Cantina Secundária", "Gerente"),
]
CLIENTES = [
    ("Ronaldo Caires da Rosa", "cliente@fastline.dev"),
    ("Ana Souza", "ana@fastline.dev"),
    ("Bruno Lima", "bruno@fastline.dev"),
]


class Command(BaseCommand):
    help = "Cria usuários de teste, cantinas, produtos e pedidos fictícios para demonstração."

    def add_arguments(self, parser):
        parser.add_argument("--sem-historico", action="store_true", help="Não cria pedidos históricos.")

    @transaction.atomic
    def handle(self, *args, sem_historico=False, **options):
        random.seed(42)
        cantinas = self._cantinas()
        self._usuarios(cantinas)
        produtos = self._produtos(cantinas)
        if not sem_historico and not Pedido.objects.filter(usuario__email__endswith="@fastline.dev").exists():
            self._historico(cantinas, produtos)
        self.stdout.write(self.style.SUCCESS("Dados de demonstração prontos."))
        self.stdout.write(f"Senha de todos os usuários de teste: {SENHA_DEMO}")
        self.stdout.write("  admin@fastline.dev (administrador)")
        for _, email, cantina, _ in FUNCIONARIOS:
            self.stdout.write(f"  {email} (funcionário - {cantina})")
        for _, email in CLIENTES:
            self.stdout.write(f"  {email} (cliente)")

    # ------------------------------------------------------------------
    def _cantinas(self):
        resultado = {}
        for dados in CANTINAS:
            obj, _ = Estabelecimento.objects.update_or_create(
                nome=dados["nome"],
                defaults={
                    "local": dados["local"], "endereco": dados["endereco"], "email": dados["email"],
                    "identificacao": dados["identificacao"], "descricao": dados["descricao"],
                    "horario_abertura": dados["abre"], "horario_fechamento": dados["fecha"], "ativo": True,
                },
            )
            resultado[obj.nome] = obj
        return resultado

    def _usuario(self, email, nome, permissao, **extra):
        usuario = Usuario.objects.filter(email=email).first()
        if usuario is None:
            usuario = Usuario.objects.create_user(email=email, password=SENHA_DEMO, nome=nome, permissao=permissao, **extra)
        return usuario

    def _usuarios(self, cantinas):
        admin = self._usuario("admin@fastline.dev", "Administrador FastLine", Permissao.ADMIN)
        admin.is_staff = True
        admin.is_superuser = True
        admin.save(update_fields=["is_staff", "is_superuser"])
        for nome, email, cantina, funcao in FUNCIONARIOS:
            u = self._usuario(email, nome, Permissao.FUNCIONARIO)
            Vinculo.objects.get_or_create(
                usuario=u, estabelecimento=cantinas[cantina], defaults={"funcao": funcao},
            )
        for i, (nome, email) in enumerate(CLIENTES):
            self._usuario(
                email, nome, Permissao.CLIENTE,
                data_nascimento=datetime(2000 + i, 5, 10).date(),
                estabelecimento_atual=cantinas["Cantina Principal"] if i else None,
            )

    def _copiar_imagem(self, arquivo):
        origem = Path(settings.BASE_DIR) / "static" / "img" / "produtos" / arquivo
        destino_rel = Path("produtos") / "demo" / arquivo
        destino = Path(settings.MEDIA_ROOT) / destino_rel
        if origem.exists():
            destino.parent.mkdir(parents=True, exist_ok=True)
            if not destino.exists():
                shutil.copyfile(origem, destino)
            return str(destino_rel).replace("\\", "/")
        return ""

    def _produtos(self, cantinas):
        hoje = timezone.localdate()
        todos = {}
        for nome_cantina, itens in PRODUTOS.items():
            cantina = cantinas[nome_cantina]
            for ordem, (nome, cat_nome, preco, imagem, qtd, descricao) in enumerate(itens):
                categoria, _ = Categoria.objects.get_or_create(
                    estabelecimento=cantina, nome=cat_nome,
                    defaults={"ordem": ["Salgado", "Bebida em Lata", "Bebida", "Suco", "Sobremesa"].index(cat_nome)
                              if cat_nome in ["Salgado", "Bebida em Lata", "Bebida", "Suco", "Sobremesa"] else 9},
                )
                produto, criado = Produto.objects.get_or_create(
                    estabelecimento=cantina, nome=nome,
                    defaults={"categoria": categoria, "preco": Decimal(preco), "descricao": descricao},
                )
                if imagem and not produto.imagem:
                    produto.imagem = self._copiar_imagem(imagem)
                    produto.save(update_fields=["imagem"])
                DisponibilidadeOnline.objects.get_or_create(
                    produto=produto, data=hoje, defaults={"quantidade_ofertada": qtd},
                )
                todos.setdefault(nome_cantina, []).append(produto)
        CardapioEspecial.objects.get_or_create(
            estabelecimento=cantinas["Cantina Principal"], data=hoje, titulo="Almoço do dia",
            defaults={"descricao": "Arroz, feijão, frango grelhado e salada. Peça os salgados junto!"},
        )
        return todos

    def _historico(self, cantinas, produtos):
        """Pedidos pagos nos últimos 6 dias (fictícios, pagos no balcão)."""
        clientes = list(Usuario.objects.filter(permissao=Permissao.CLIENTE, email__endswith="@fastline.dev"))
        funcionario = Usuario.objects.get(email="funcionario@fastline.dev")
        agora = timezone.now()
        for dias_atras in range(6, 0, -1):
            for n in range(random.randint(2, 4)):
                cantina = cantinas["Cantina Principal"]
                momento = agora - timedelta(days=dias_atras, hours=random.randint(0, 6), minutes=random.randint(0, 59))
                escolhidos = random.sample(produtos[cantina.nome], k=random.randint(1, 2))
                p = Pedido.objects.create(
                    usuario=random.choice(clientes), estabelecimento=cantina, status=StatusPedido.RETIRADO,
                    data_disponibilidade=momento.date(), metodo_pagamento="balcao", reserva_liberada=False,
                )
                total = Decimal("0.00")
                for prod in escolhidos:
                    qtd = random.randint(1, 3)
                    item_pedido.objects.create(
                        pedido=p, produto=prod, nome_produto=prod.nome, quantidade=qtd, preco_unitario=prod.preco,
                    )
                    total += prod.preco * qtd
                token = gerar_token_retirada()
                while Pedido.objects.filter(token_retirada=token).exists():
                    token = gerar_token_retirada()
                Pedido.objects.filter(pk=p.pk).update(
                    subtotal=total, valor_total=total, data_pedido=momento, confirmado_em=momento,
                    token_retirada=token,
                )
                Pagamento.objects.create(
                    pedido=p, metodo_pagamento="balcao", valor_pago=total, provedor="balcao",
                    status=StatusPagamento.PAGO, pago_em=momento, confirmado_por=funcionario,
                    mensagem="Dado fictício de demonstração.",
                )
                r = Retirada.objects.create(
                    pedido=p, local_retirada=cantina.local_completo, confirmado_por=funcionario, token_utilizado=token,
                )
                Retirada.objects.filter(pk=r.pk).update(data_retirada=momento + timedelta(minutes=15))
