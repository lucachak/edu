"""Código da cantina: o cliente digita o código para se conectar."""

from django.urls import reverse

from estabelecimentos.forms import EstabelecimentoForm
from estabelecimentos.models import ALFABETO_CODIGO, estabelecimento as Estabelecimento
from usuarios.models import Vinculo

from .base import FastLineTestCase


class CodigoCantinaTests(FastLineTestCase):
    def test_toda_cantina_nova_ganha_codigo_unico(self):
        a, b = self.cantina_a, self.cantina_b
        self.assertEqual(len(a.codigo_acesso), 6)
        self.assertTrue(set(a.codigo_acesso) <= set(ALFABETO_CODIGO))
        self.assertNotEqual(a.codigo_acesso, b.codigo_acesso)

    def test_codigo_digitado_e_normalizado(self):
        c = Estabelecimento.objects.create(nome="C", endereco="R", codigo_acesso="senai-01")
        self.assertEqual(c.codigo_acesso, "SENAI01")

    def test_cliente_encontra_cantina_pelo_codigo_ignorando_maiusculas_e_hifen(self):
        Estabelecimento.objects.filter(pk=self.cantina_b.pk).update(codigo_acesso="ABCD23")
        self.entrar(self.cliente)
        resp = self.client.get(reverse("estabelecimentos:buscar"), {"codigo": " abcd-23 "})
        self.assertEqual(resp.context["cantina_encontrada"], self.cantina_b)

    def test_codigo_errado_mostra_erro(self):
        self.entrar(self.cliente)
        resp = self.client.get(reverse("estabelecimentos:buscar"), {"codigo": "NAOEXISTE"})
        self.assertIsNone(resp.context["cantina_encontrada"])
        self.assertContains(resp, "Nenhuma cantina encontrada")

    def test_cantina_desativada_nao_e_encontrada(self):
        Estabelecimento.objects.filter(pk=self.cantina_b.pk).update(ativo=False)
        self.entrar(self.cliente)
        resp = self.client.get(reverse("estabelecimentos:buscar"), {"codigo": self.cantina_b.codigo_acesso})
        self.assertIsNone(resp.context["cantina_encontrada"])

    def test_conectar_salva_cantina_e_seleciona(self):
        self.entrar(self.cliente)
        resp = self.client.post(reverse("estabelecimentos:selecionar", args=[self.cantina_b.unique_id]))
        self.assertRedirects(resp, reverse("produtos:cardapio"), fetch_redirect_response=False)
        self.cliente.refresh_from_db()
        self.assertEqual(self.cliente.estabelecimento_atual, self.cantina_b)
        self.assertTrue(self.cliente.favoritos.filter(pk=self.cantina_b.pk).exists())

    def test_formulario_rejeita_codigo_repetido(self):
        form = EstabelecimentoForm(data={
            "nome": "Nova", "endereco": "Rua", "codigo_acesso": self.cantina_a.codigo_acesso.lower(), "ativo": True,
        })
        self.assertFalse(form.is_valid())
        self.assertIn("codigo_acesso", form.errors)

    def test_formulario_gera_codigo_quando_vazio(self):
        form = EstabelecimentoForm(data={"nome": "Nova", "endereco": "Rua", "codigo_acesso": "", "ativo": True})
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(len(form.save().codigo_acesso), 6)

    def test_funcionario_ve_codigo_no_dashboard(self):
        self.entrar(self.func_a)
        resp = self.client.get(reverse("painel:dashboard"))
        self.assertContains(resp, self.cantina_a.codigo_acesso)

    def test_so_gerente_gera_novo_codigo(self):
        antigo = self.cantina_a.codigo_acesso
        self.entrar(self.func_a)
        self.client.post(reverse("painel:regenerar_codigo"))
        self.cantina_a.refresh_from_db()
        self.assertEqual(self.cantina_a.codigo_acesso, antigo)

        Vinculo.objects.filter(usuario=self.func_a).update(funcao="gerente")
        self.client.post(reverse("painel:regenerar_codigo"))
        self.cantina_a.refresh_from_db()
        self.assertNotEqual(self.cantina_a.codigo_acesso, antigo)
