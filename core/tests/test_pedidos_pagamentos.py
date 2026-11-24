import hashlib
import json
import re
from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.core.management import call_command
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from pedidos import pagamentos
from pedidos.models import (
    EventoPagamento,
    StatusPagamento,
    StatusPedido,
    gerar_token_retirada,
    pagamento as Pagamento,
    pedido as Pedido,
)
from pedidos.services import (
    PedidoErro,
    ProdutoIndisponivel,
    atualizar_status,
    confirmar_pagamento,
    confirmar_retirada,
    criar_pedido,
    expirar_reservas_vencidas,
)

from .base import FastLineTestCase

AJAX = {"HTTP_X_REQUESTED_WITH": "fetch"}
TOKEN_TESTE = "token-de-teste-nao-real"


class CarrinhoTests(FastLineTestCase):
    def setUp(self):
        self.entrar(self.cliente)

    def adicionar(self, produto, quantidade=1, **extra):
        return self.client.post(
            reverse("pedidos:carrinho_adicionar", args=[produto.pk]), {"quantidade": quantidade, **extra}, **AJAX,
        )

    def test_adicionar_atualizar_remover_e_totais(self):
        self.assertEqual(self.adicionar(self.coxinha, 2).status_code, 200)
        self.adicionar(self.suco, 3)
        resp = self.client.post(reverse("pedidos:carrinho_atualizar", args=[self.coxinha.pk]), {"quantidade": 4}, **AJAX)
        self.assertEqual(resp.status_code, 200)
        self.client.post(reverse("pedidos:carrinho_remover", args=[self.suco.pk]), **AJAX)
        resp = self.client.get(reverse("pedidos:carrinho"), **AJAX)
        dados = resp.json()
        self.assertEqual(self.client.session["fastline_carrinho"]["itens"], {str(self.coxinha.pk): 4})
        self.assertIn("20,00", json.dumps(dados, ensure_ascii=False))

    def test_preco_enviado_pelo_cliente_e_ignorado(self):
        self.adicionar(self.coxinha, 2, preco="0.01", valor_total="0.01")
        self.client.post(reverse("pedidos:checkout"), {"metodo": "pix"})
        self.client.post(reverse("pedidos:checkout_confirmar"), {"valor_total": "0.01"})
        p = Pedido.objects.get(usuario=self.cliente)
        self.assertEqual(p.valor_total, Decimal("10.00"))
        self.assertEqual(p.itens.get().preco_unitario, Decimal("5.00"))

    def test_nao_adiciona_acima_da_disponibilidade(self):
        resp = self.adicionar(self.suco, 11)
        self.assertEqual(resp.status_code, 409)
        self.assertNotIn(str(self.suco.pk), self.client.session.get("fastline_carrinho", {}).get("itens", {}))

    def test_nao_adiciona_produto_de_outra_cantina(self):
        self.assertEqual(self.adicionar(self.pao_b).status_code, 404)

    def test_quantidade_invalida(self):
        self.assertEqual(self.adicionar(self.coxinha, "abc").status_code, 400)
        self.assertEqual(self.adicionar(self.coxinha, -3).status_code, 400)


class CheckoutTests(FastLineTestCase):
    def test_fluxo_balcao_completo(self):
        """Sem PagSeguro: pedido fica aguardando até o funcionário confirmar no balcão."""
        self.entrar(self.cliente)
        self.client.post(reverse("pedidos:carrinho_adicionar", args=[self.coxinha.pk]), {"quantidade": 3})
        self.client.post(reverse("pedidos:checkout"), {"metodo": "pix"})
        resp = self.client.post(reverse("pedidos:checkout_confirmar"))
        p = Pedido.objects.get(usuario=self.cliente)
        self.assertRedirects(resp, reverse("pedidos:pagamento", args=[p.codigo]))
        self.assertEqual(p.status, StatusPedido.AGUARDANDO_PAGAMENTO)
        self.assertEqual(p.pagamento.provedor, "balcao")
        self.assertEqual(self.disponivel(self.coxinha), 17)
        self.assertEqual(self.client.session["fastline_carrinho"]["itens"], {})

        self.entrar(self.func_a)
        self.client.post(reverse("painel:pedido_pagamento_balcao", args=[p.pk]))
        p.refresh_from_db()
        self.assertEqual(p.status, StatusPedido.CONFIRMADO)
        self.assertRegex(p.token_retirada, r"^[A-Z]{2}\d{4}-\d{2}$")
        self.assertEqual(p.pagamento.status, StatusPagamento.PAGO)
        self.assertEqual(p.pagamento.confirmado_por, self.func_a)

    def test_checkout_rejeita_quando_esgotou_e_desfaz_tudo(self):
        criar_pedido(self.outro_cliente, self.cantina_a, {self.suco.pk: 10})
        with self.assertRaises(ProdutoIndisponivel):
            criar_pedido(self.cliente, self.cantina_a, {self.coxinha.pk: 2, self.suco.pk: 1})
        self.assertEqual(Pedido.objects.filter(usuario=self.cliente).count(), 0)
        self.assertEqual(self.disponivel(self.coxinha), 20)  # rollback da reserva da coxinha

    def test_ultima_unidade_so_vende_uma_vez(self):
        criar_pedido(self.outro_cliente, self.cantina_a, {self.suco.pk: 9})
        criar_pedido(self.cliente, self.cantina_a, {self.suco.pk: 1})
        with self.assertRaises(ProdutoIndisponivel):
            criar_pedido(self.outro_cliente, self.cantina_a, {self.suco.pk: 1})
        self.assertEqual(self.disponivel(self.suco), 0)

    def test_produto_de_outra_cantina_no_pedido(self):
        with self.assertRaises(PedidoErro):
            criar_pedido(self.cliente, self.cantina_a, {self.pao_b.pk: 1})

    @override_settings(FASTLINE_TAXA_SERVICO="1.50")
    def test_calculo_de_valores(self):
        p = criar_pedido(self.cliente, self.cantina_a, {self.coxinha.pk: 3, self.suco.pk: 2})
        self.assertEqual(p.subtotal, Decimal("20.00"))
        self.assertEqual(p.taxa_servico, Decimal("1.50"))
        self.assertEqual(p.valor_total, Decimal("21.50"))
        self.assertEqual({i.nome_produto: i.preco_unitario for i in p.itens.all()},
                         {"Coxinha": Decimal("5.00"), "Suco": Decimal("2.50")})

    def test_preco_do_item_fica_congelado(self):
        p = criar_pedido(self.cliente, self.cantina_a, {self.coxinha.pk: 1})
        self.coxinha.preco = Decimal("9.99")
        self.coxinha.save()
        self.assertEqual(p.itens.get().preco_unitario, Decimal("5.00"))

    def test_reserva_expirada_libera_unidades(self):
        p = criar_pedido(self.cliente, self.cantina_a, {self.coxinha.pk: 5})
        self.assertEqual(self.disponivel(self.coxinha), 15)
        Pedido.objects.filter(pk=p.pk).update(reserva_expira_em=timezone.now() - timedelta(minutes=1))
        call_command("expirar_reservas", verbosity=0)
        p.refresh_from_db()
        self.assertEqual(p.status, StatusPedido.CANCELADO)
        self.assertEqual(self.disponivel(self.coxinha), 20)
        self.assertEqual(expirar_reservas_vencidas(), 0)  # idempotente

    def test_cliente_cancela_antes_de_pagar(self):
        p = criar_pedido(self.cliente, self.cantina_a, {self.coxinha.pk: 2})
        self.entrar(self.cliente)
        self.client.post(reverse("pedidos:cancelar", args=[p.codigo]))
        p.refresh_from_db()
        self.assertEqual(p.status, StatusPedido.CANCELADO)
        self.assertEqual(self.disponivel(self.coxinha), 20)

    def test_cliente_nao_cancela_pedido_pago(self):
        p = confirmar_pagamento(criar_pedido(self.cliente, self.cantina_a, {self.coxinha.pk: 2}))
        self.entrar(self.cliente)
        self.client.post(reverse("pedidos:cancelar", args=[p.codigo]))
        p.refresh_from_db()
        self.assertEqual(p.status, StatusPedido.CONFIRMADO)

    def test_cliente_nao_altera_status(self):
        p = confirmar_pagamento(criar_pedido(self.cliente, self.cantina_a, {self.coxinha.pk: 1}))
        self.entrar(self.cliente)
        resp = self.client.post(reverse("painel:pedido_status", args=[p.pk]), {"status": StatusPedido.RETIRADO})
        self.assertEqual(resp.status_code, 403)
        p.refresh_from_db()
        self.assertEqual(p.status, StatusPedido.CONFIRMADO)

    def test_outro_cliente_nao_ve_pedido(self):
        p = criar_pedido(self.cliente, self.cantina_a, {self.coxinha.pk: 1})
        self.entrar(self.outro_cliente)
        for nome in ("pedidos:pagamento", "pedidos:status", "pedidos:confirmado"):
            self.assertEqual(self.client.get(reverse(nome, args=[p.codigo])).status_code, 404, nome)
        self.assertEqual(self.client.post(reverse("pedidos:cancelar", args=[p.codigo])).status_code, 404)
        self.assertNotContains(self.client.get(reverse("pedidos:tickets")), str(p.codigo)[:8])


class TokenERetiradaTests(FastLineTestCase):
    def pedido_pago(self):
        return confirmar_pagamento(criar_pedido(self.cliente, self.cantina_a, {self.coxinha.pk: 1}))

    def test_token_formato_e_aleatoriedade(self):
        tokens = {gerar_token_retirada() for _ in range(500)}
        self.assertGreater(len(tokens), 495)
        for t in tokens:
            self.assertRegex(t, r"^[A-HJ-NP-Z]{2}\d{4}-\d{2}$")

    def test_token_unico_e_confirmacao_idempotente(self):
        a, b = self.pedido_pago(), self.pedido_pago()
        self.assertNotEqual(a.token_retirada, b.token_retirada)
        self.assertEqual(confirmar_pagamento(a).token_retirada, a.token_retirada)

    def test_pedido_nao_pago_nao_tem_token(self):
        p = criar_pedido(self.cliente, self.cantina_a, {self.coxinha.pk: 1})
        self.assertFalse(p.token_retirada)

    def test_funcionario_confirma_retirada_uma_unica_vez(self):
        p = self.pedido_pago()
        self.entrar(self.func_a)
        resp = self.client.get(reverse("painel:token"), {"token": p.token_retirada.lower().replace("-", "")})
        self.assertContains(resp, "Coxinha")
        self.client.post(reverse("painel:token_confirmar"), {"token": p.token_retirada})
        p.refresh_from_db()
        self.assertEqual(p.status, StatusPedido.RETIRADO)
        self.assertEqual(p.retirada.confirmado_por, self.func_a)
        self.assertIsNotNone(p.retirada.data_retirada)
        with self.assertRaisesRegex(PedidoErro, "já foi utilizado"):
            confirmar_retirada(p.token_retirada, self.cantina_a, self.func_a)

    def test_funcionario_de_outra_cantina_nao_usa_token(self):
        p = self.pedido_pago()
        self.entrar(self.func_b)
        self.assertContains(self.client.get(reverse("painel:token"), {"token": p.token_retirada}), "Nenhum pedido com o token")
        self.client.post(reverse("painel:token_confirmar"), {"token": p.token_retirada})
        p.refresh_from_db()
        self.assertEqual(p.status, StatusPedido.CONFIRMADO)

    def test_token_invalido(self):
        with self.assertRaises(PedidoErro):
            confirmar_retirada("ZZ0000-00", self.cantina_a, self.func_a)

    def test_transicoes_do_funcionario(self):
        p = self.pedido_pago()
        atualizar_status(p, StatusPedido.EM_PREPARACAO, self.func_a)
        atualizar_status(p, StatusPedido.PRONTO, self.func_a)
        with self.assertRaises(PedidoErro):
            atualizar_status(p, StatusPedido.CONFIRMADO, self.func_a)
        with self.assertRaises(PedidoErro):  # retirada só com token
            atualizar_status(p, StatusPedido.RETIRADO, self.func_a)

    def test_funcionario_de_outra_cantina_nao_muda_status(self):
        p = self.pedido_pago()
        self.entrar(self.func_b)
        resp = self.client.post(reverse("painel:pedido_status", args=[p.pk]), {"status": StatusPedido.PRONTO})
        self.assertEqual(resp.status_code, 404)

    def test_cancelamento_pelo_funcionario_devolve_unidades(self):
        p = self.pedido_pago()
        atualizar_status(p, StatusPedido.CANCELADO, self.func_a)
        self.assertEqual(self.disponivel(self.coxinha), 20)


def resposta_http(status_code, dados):
    r = mock.Mock(status_code=status_code)
    r.json.return_value = dados
    r.text = json.dumps(dados)
    return r


def pedido_pagbank(status, valor, order_id="ORDE_TESTE", pix=True):
    charge = {"id": "CHAR_TESTE", "status": status, "amount": {"value": valor, "summary": {"paid": valor if status == "PAID" else 0}}}
    dados = {"id": order_id, "charges": [charge] if status != "WAITING" else []}
    if pix:
        dados["qr_codes"] = [{"text": "00020101021226830014br.gov.bcb.pix", "links": [{"rel": "QRCODE.PNG", "href": "https://sandbox.api.pagseguro.com/qrcode.png"}]}]
    return dados


@override_settings(PAGSEGURO_TOKEN=TOKEN_TESTE, PAGSEGURO_AMBIENTE="sandbox")
class PagSeguroTests(FastLineTestCase):
    def novo_pagamento_pix(self):
        p = criar_pedido(self.cliente, self.cantina_a, {self.coxinha.pk: 2})
        with mock.patch("pedidos.pagseguro.requests.request", return_value=resposta_http(201, pedido_pagbank("WAITING", 1000))) as req:
            pag = pagamentos.iniciar_pagamento(p, "pix", "https://exemplo.test/retorno")
        return p, pag, req

    def test_modo_pagseguro_quando_ha_token(self):
        self.assertEqual(pagamentos.modo_pagamento(), "pagseguro")

    def test_cria_cobranca_pix_no_sandbox(self):
        p, pag, req = self.novo_pagamento_pix()
        metodo, url = req.call_args.args
        corpo = req.call_args.kwargs["json"]
        self.assertEqual(metodo, "POST")
        self.assertEqual(url, "https://sandbox.api.pagseguro.com/orders")
        self.assertEqual(req.call_args.kwargs["headers"]["Authorization"], f"Bearer {TOKEN_TESTE}")
        self.assertEqual(corpo["reference_id"], str(pag.referencia))
        self.assertEqual(sum(i["unit_amount"] * i["quantity"] for i in corpo["items"]), 1000)
        self.assertEqual(corpo["customer"]["tax_id"], "52998224725")
        self.assertEqual(pag.pagseguro_order_id, "ORDE_TESTE")
        self.assertTrue(pag.pix_copia_e_cola)
        self.assertEqual(pag.status, StatusPagamento.PENDENTE)
        p.refresh_from_db()
        self.assertEqual(p.status, StatusPedido.AGUARDANDO_PAGAMENTO)
        self.assertFalse(p.token_retirada)

    def test_sincronizar_pago_confirma_e_gera_token(self):
        p, pag, _ = self.novo_pagamento_pix()
        with mock.patch("pedidos.pagseguro.requests.request", return_value=resposta_http(200, pedido_pagbank("PAID", 1000))):
            pagamentos.sincronizar(pag)
        p.refresh_from_db()
        pag.refresh_from_db()
        self.assertEqual(pag.status, StatusPagamento.PAGO)
        self.assertEqual(p.status, StatusPedido.CONFIRMADO)
        self.assertTrue(p.token_retirada)

    def test_valor_pago_menor_nao_confirma(self):
        p, pag, _ = self.novo_pagamento_pix()
        with mock.patch("pedidos.pagseguro.requests.request", return_value=resposta_http(200, pedido_pagbank("PAID", 100))):
            pagamentos.sincronizar(pag)
        p.refresh_from_db()
        self.assertEqual(p.status, StatusPedido.AGUARDANDO_PAGAMENTO)
        self.assertEqual(pag.status, StatusPagamento.ERRO)

    def test_pagamento_recusado(self):
        p, pag, _ = self.novo_pagamento_pix()
        with mock.patch("pedidos.pagseguro.requests.request", return_value=resposta_http(200, pedido_pagbank("DECLINED", 1000))):
            pagamentos.sincronizar(pag)
        self.assertEqual(pag.status, StatusPagamento.RECUSADO)
        p.refresh_from_db()
        self.assertEqual(p.status, StatusPedido.AGUARDANDO_PAGAMENTO)

    def test_erro_da_api_e_registrado(self):
        p = criar_pedido(self.cliente, self.cantina_a, {self.coxinha.pk: 1})
        erro = {"error_messages": [{"code": "40002", "description": "invalid_parameter"}]}
        with mock.patch("pedidos.pagseguro.requests.request", return_value=resposta_http(400, erro)):
            pag = pagamentos.iniciar_pagamento(p, "pix", "")
        self.assertEqual(pag.status, StatusPagamento.ERRO)
        self.assertIn("invalid_parameter", pag.mensagem)

    def test_checkout_de_cartao_redireciona_para_pagbank(self):
        p = criar_pedido(self.cliente, self.cantina_a, {self.coxinha.pk: 1})
        resposta = {"id": "CHEC_TESTE", "status": "ACTIVE", "links": [{"rel": "PAY", "href": "https://sandbox.pagseguro.uol.com.br/checkout/x"}]}
        with mock.patch("pedidos.pagseguro.requests.request", return_value=resposta_http(201, resposta)) as req:
            pag = pagamentos.iniciar_pagamento(p, "cartao_credito", "https://exemplo.test/retorno")
        self.assertTrue(req.call_args.args[1].endswith("/checkouts"))
        self.assertEqual(req.call_args.kwargs["json"]["payment_methods"], [{"type": "CREDIT_CARD"}])
        self.assertEqual(pag.link_pagamento, "https://sandbox.pagseguro.uol.com.br/checkout/x")

    def test_funcionario_nao_confirma_no_balcao_pedido_pagseguro(self):
        p, pag, _ = self.novo_pagamento_pix()
        with self.assertRaises(PedidoErro):
            pagamentos.confirmar_no_balcao(p, self.func_a)

    def webhook(self, dados, assinatura=None):
        corpo = json.dumps(dados).encode()
        if assinatura is None:
            assinatura = hashlib.sha256(TOKEN_TESTE.encode() + b"-" + corpo).hexdigest()
        return self.client.post(
            reverse("pedidos:webhook_pagseguro"), corpo, content_type="application/json",
            HTTP_X_AUTHENTICITY_TOKEN=assinatura,
        )

    def test_webhook_com_assinatura_invalida_e_descartado(self):
        p, pag, _ = self.novo_pagamento_pix()
        with mock.patch("pedidos.pagseguro.requests.request") as req:
            resp = self.webhook(pedido_pagbank("PAID", 1000) | {"reference_id": str(pag.referencia)}, assinatura="0" * 64)
        self.assertEqual(resp.status_code, 401)
        req.assert_not_called()
        p.refresh_from_db()
        self.assertEqual(p.status, StatusPedido.AGUARDANDO_PAGAMENTO)
        self.assertTrue(EventoPagamento.objects.filter(origem="webhook", autenticado=False).exists())

    def test_webhook_valido_consulta_api_antes_de_confirmar(self):
        p, pag, _ = self.novo_pagamento_pix()
        corpo = pedido_pagbank("PAID", 1000) | {"reference_id": str(pag.referencia)}
        # A notificação diz PAID, mas a API ainda diz WAITING: não confirma.
        with mock.patch("pedidos.pagseguro.requests.request", return_value=resposta_http(200, pedido_pagbank("WAITING", 1000))):
            self.assertEqual(self.webhook(corpo).status_code, 200)
        p.refresh_from_db()
        self.assertEqual(p.status, StatusPedido.AGUARDANDO_PAGAMENTO)
        with mock.patch("pedidos.pagseguro.requests.request", return_value=resposta_http(200, pedido_pagbank("PAID", 1000))) as req:
            self.webhook(corpo)
        self.assertEqual(req.call_args.args, ("GET", "https://sandbox.api.pagseguro.com/orders/ORDE_TESTE"))
        p.refresh_from_db()
        self.assertEqual(p.status, StatusPedido.CONFIRMADO)

    def test_pagamento_apos_expiracao_reativa_se_houver_unidades(self):
        p, pag, _ = self.novo_pagamento_pix()
        Pedido.objects.filter(pk=p.pk).update(reserva_expira_em=timezone.now() - timedelta(minutes=1))
        expirar_reservas_vencidas()
        with mock.patch("pedidos.pagseguro.requests.request", return_value=resposta_http(200, pedido_pagbank("PAID", 1000))):
            pagamentos.sincronizar(Pagamento.objects.get(pk=pag.pk))
        p.refresh_from_db()
        self.assertEqual(p.status, StatusPedido.CONFIRMADO)
        self.assertEqual(self.disponivel(self.coxinha), 18)

    def test_status_json_do_pedido(self):
        p, pag, _ = self.novo_pagamento_pix()
        self.entrar(self.cliente)
        with mock.patch("pedidos.pagseguro.requests.request", return_value=resposta_http(200, pedido_pagbank("PAID", 1000))):
            dados = self.client.get(reverse("pedidos:status", args=[p.codigo])).json()
        self.assertTrue(dados["confirmado"])
        self.assertTrue(re.match(r"/pedido/.+/confirmado/", dados["url"]))
