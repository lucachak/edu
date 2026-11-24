"""Fábricas de dados usadas pelos testes."""

from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from estabelecimentos.models import estabelecimento as Estabelecimento
from produtos.models import Categoria, DisponibilidadeOnline, Produto
from usuarios.models import Permissao, Usuario, Vinculo

SENHA = "Senha-Forte-123"


class FastLineTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.cantina_a = Estabelecimento.objects.create(nome="Cantina A", endereco="Rua 1", local="Térreo")
        cls.cantina_b = Estabelecimento.objects.create(nome="Cantina B", endereco="Rua 2", local="5º andar")
        cls.admin = Usuario.objects.create_user("admin@teste.com", SENHA, nome="Admin", permissao=Permissao.ADMIN)
        cls.func_a = Usuario.objects.create_user("func.a@teste.com", SENHA, nome="Func A", permissao=Permissao.FUNCIONARIO)
        cls.func_b = Usuario.objects.create_user("func.b@teste.com", SENHA, nome="Func B", permissao=Permissao.FUNCIONARIO)
        Vinculo.objects.create(usuario=cls.func_a, estabelecimento=cls.cantina_a, funcao="Atendente")
        Vinculo.objects.create(usuario=cls.func_b, estabelecimento=cls.cantina_b, funcao="Atendente")
        cls.cliente = Usuario.objects.create_user(
            "cliente@teste.com", SENHA, nome="Cliente Um", estabelecimento_atual=cls.cantina_a, cpf="52998224725",
        )
        cls.outro_cliente = Usuario.objects.create_user(
            "outro@teste.com", SENHA, nome="Cliente Dois", estabelecimento_atual=cls.cantina_a,
        )
        cls.cat_a = Categoria.objects.create(estabelecimento=cls.cantina_a, nome="Salgado")
        cls.cat_b = Categoria.objects.create(estabelecimento=cls.cantina_b, nome="Salgado")
        cls.coxinha = cls.produto(cls.cantina_a, "Coxinha", "5.00", 20, cls.cat_a)
        cls.suco = cls.produto(cls.cantina_a, "Suco", "2.50", 10, cls.cat_a)
        cls.pao_b = cls.produto(cls.cantina_b, "Pão de queijo B", "1.80", 10, cls.cat_b)

    @staticmethod
    def produto(cantina, nome, preco, quantidade, categoria=None):
        p = Produto.objects.create(
            estabelecimento=cantina, nome=nome, preco=Decimal(preco), categoria=categoria, descricao="",
        )
        DisponibilidadeOnline.objects.create(produto=p, data=timezone.localdate(), quantidade_ofertada=quantidade)
        return p

    def entrar(self, usuario):
        self.client.force_login(usuario)

    def disponivel(self, produto):
        return produto.disponibilidades.get(data=timezone.localdate()).quantidade_disponivel
