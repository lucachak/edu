import shutil
import tempfile
from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from produtos.models import DisponibilidadeOnline, Produto, movimentacao

from .base import FastLineTestCase

MEDIA_TESTE = tempfile.mkdtemp()


def imagem_png():
    buffer = BytesIO()
    Image.new("RGB", (10, 10), "orange").save(buffer, "PNG")
    return SimpleUploadedFile("teste.png", buffer.getvalue(), content_type="image/png")


@override_settings(MEDIA_ROOT=MEDIA_TESTE)
class ProdutosTests(FastLineTestCase):
    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(MEDIA_TESTE, ignore_errors=True)
        super().tearDownClass()

    def test_funcionario_cadastra_produto_com_imagem_sem_cota_de_quantidade(self):
        self.entrar(self.func_a)
        resp = self.client.post(reverse("painel:itens"), {
            "nome": "Esfirra", "preco": "6.00", "nova_categoria": "Assados",
            "descricao": "De carne", "ativo": "on", "imagem": imagem_png(),
        })
        self.assertRedirects(resp, reverse("painel:itens"))
        produto = Produto.objects.get(nome="Esfirra")
        self.assertEqual(produto.estabelecimento, self.cantina_a)
        self.assertEqual(produto.categoria.nome, "Assados")
        self.assertTrue(produto.imagem.name)
        self.assertFalse(produto.disponibilidades.exists())
        self.assertTrue(movimentacao.objects.filter(produto=produto, tipo_movimentacao="adicionado").exists())

    def test_preco_invalido(self):
        self.entrar(self.func_a)
        resp = self.client.post(reverse("painel:itens"), {"nome": "X", "preco": "0", "categoria": self.cat_a.pk})
        self.assertIn("preco", resp.context["form"].errors)

    def test_produto_cadastrado_vai_para_estabelecimento_do_funcionario(self):
        """Mesmo que alguém tente mandar outra categoria/estabelecimento pelo formulário."""
        self.entrar(self.func_b)
        resp = self.client.post(reverse("painel:itens"), {
            "nome": "Invasor", "preco": "1.00", "categoria": self.cat_a.pk,
            "estabelecimento": self.cantina_a.pk,
        })
        self.assertEqual(resp.status_code, 200)  # categoria de outra cantina é inválida
        self.assertFalse(Produto.objects.filter(nome="Invasor").exists())

    def test_editar_produto(self):
        self.entrar(self.func_a)
        url = reverse("painel:produto_editar", args=[self.coxinha.pk])
        resp = self.client.post(url, {"nome": "Coxinha G", "preco": "5.50", "categoria": self.cat_a.pk, "ativo": "on"})
        self.assertRedirects(resp, reverse("painel:itens"))
        self.coxinha.refresh_from_db()
        self.assertEqual(str(self.coxinha.preco), "5.50")

    def test_remover_produto_sem_pedidos(self):
        self.entrar(self.func_a)
        self.client.post(reverse("painel:produto_remover", args=[self.suco.pk]))
        self.assertFalse(Produto.objects.filter(pk=self.suco.pk).exists())


class DisponibilidadeOnlineTests(FastLineTestCase):
    def test_reserva_atomica_nao_ultrapassa_cota(self):
        disp = self.coxinha.disponibilidades.get()
        self.assertTrue(DisponibilidadeOnline.reservar(disp.pk, 15))
        self.assertFalse(DisponibilidadeOnline.reservar(disp.pk, 6))
        self.assertTrue(DisponibilidadeOnline.reservar(disp.pk, 5))
        self.assertFalse(DisponibilidadeOnline.reservar(disp.pk, 1))
        disp.refresh_from_db()
        self.assertEqual(disp.quantidade_disponivel, 0)
        self.assertTrue(disp.esgotado)

    def test_liberar_devolve_unidades(self):
        disp = self.coxinha.disponibilidades.get()
        DisponibilidadeOnline.reservar(disp.pk, 4)
        DisponibilidadeOnline.liberar(disp.pk, 4)
        disp.refresh_from_db()
        self.assertEqual(disp.quantidade_comprometida, 0)

    def test_cardapio_nao_esconde_produto_por_cota_antiga(self):
        disp = self.coxinha.disponibilidades.get()
        DisponibilidadeOnline.reservar(disp.pk, 20)
        self.suco.disponibilidades.all().delete()
        self.entrar(self.cliente)
        resp = self.client.get(reverse("produtos:cardapio"))
        self.assertContains(resp, "Coxinha")
        self.assertContains(resp, "Suco")
        self.assertNotContains(resp, "Esgotado")
        self.assertNotContains(resp, "disponíveis hoje")

    def test_funcionario_nao_altera_produto_de_outra_cantina(self):
        self.entrar(self.func_b)
        self.assertEqual(self.client.get(reverse("painel:produto_editar", args=[self.coxinha.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse("painel:produto_remover", args=[self.coxinha.pk])).status_code, 404)

    def test_comando_abrir_dia_copia_cota(self):
        from datetime import timedelta

        from django.core.management import call_command

        ontem = timezone.localdate() - timedelta(days=1)
        DisponibilidadeOnline.objects.filter(produto=self.coxinha).update(data=ontem)
        call_command("abrir_dia", verbosity=0)
        self.assertEqual(self.disponivel(self.coxinha), 20)

    def test_cardapio_nao_depende_de_abertura_de_cota_diaria(self):
        from datetime import timedelta

        ontem = timezone.localdate() - timedelta(days=1)
        DisponibilidadeOnline.objects.filter(produto__estabelecimento=self.cantina_a).update(data=ontem)
        self.entrar(self.cliente)
        resp = self.client.get(reverse("produtos:cardapio"))
        self.assertContains(resp, "Coxinha")
        self.assertFalse(self.coxinha.disponibilidades.filter(data=timezone.localdate()).exists())
