"""Orquestra pagamentos: cria a cobrança e sincroniza o status no backend."""

import logging

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from . import pagseguro
from .models import EventoPagamento, StatusPagamento, StatusPedido, pagamento as Pagamento
from .services import PedidoErro, confirmar_pagamento

logger = logging.getLogger("fastline.pagamentos")

METODOS_CLIENTE = {
    "simulado": "Pagamento aprovado (simulação)",
    "pix": "PIX",
    "cartao_credito": "Cartão de crédito",
    "cartao_debito": "Cartão de débito",
}
TIPO_CHECKOUT = {"cartao_credito": "CREDIT_CARD", "cartao_debito": "DEBIT_CARD"}


def modo_pagamento():
    """'pagseguro' quando há token configurado; senão 'balcao' (se habilitado)."""
    if pagseguro.configurado():
        return "pagseguro"
    if settings.PAGAMENTO_BALCAO_HABILITADO:
        return "balcao"
    return "indisponivel"


def iniciar_pagamento(pedido, metodo, url_retorno):
    """Cria o registro de pagamento e, se configurado, a cobrança no PagSeguro.

    Retorna o objeto ``pagamento``. Em caso de erro da API o pagamento fica
    com status ``erro`` e a mensagem para o cliente; o pedido continua
    aguardando pagamento até a reserva expirar (o cliente pode tentar outra
    forma de pagamento).
    """
    if metodo not in METODOS_CLIENTE:
        raise PedidoErro("Forma de pagamento inválida.")
    if metodo == "simulado":
        pag, _ = Pagamento.objects.get_or_create(
            pedido=pedido,
            defaults={"metodo_pagamento": "simulado", "valor_pago": pedido.valor_total, "provedor": "simulador", "ambiente": "demo", "status": StatusPagamento.PENDENTE},
        )
        if pag.status != StatusPagamento.PAGO:
            pag.status = StatusPagamento.PAGO
            pag.pago_em = timezone.now()
            pag.status_provedor = "APPROVED_DEMO"
            pag.mensagem = "Pagamento aprovado automaticamente em modo de demonstração. Nenhuma cobrança real foi realizada."
            pag.save()
            EventoPagamento.objects.create(pagamento=pag, origem="simulacao", autenticado=True, status_provedor="APPROVED_DEMO", payload={"demo": True, "valor": str(pedido.valor_total)})
            confirmar_pagamento(pedido)
        return pag
    modo = modo_pagamento()
    if modo == "indisponivel":
        raise PedidoErro("Pagamentos indisponíveis no momento. Procure a cantina.")

    pag, _ = Pagamento.objects.get_or_create(
        pedido=pedido,
        defaults={
            "metodo_pagamento": metodo if modo == "pagseguro" else "balcao",
            "valor_pago": pedido.valor_total,
            "provedor": "pagseguro" if modo == "pagseguro" else "balcao",
            "ambiente": pagseguro.ambiente() if modo == "pagseguro" else "",
        },
    )
    if pag.status == StatusPagamento.PAGO:
        return pag
    pag.metodo_pagamento = metodo
    pag.valor_pago = pedido.valor_total
    pag.status = StatusPagamento.PENDENTE
    pag.mensagem = ""

    if modo == "balcao":
        pag.provedor = "balcao"
        pag.metodo_pagamento = "balcao"
        pag.mensagem = "Pagamento será confirmado por um funcionário no balcão."
        pag.save()
        return pag

    pag.provedor = "pagseguro"
    pag.ambiente = pagseguro.ambiente()
    try:
        if metodo == "pix":
            resposta = pagseguro.criar_pedido_pix(pag)
            pag.pagseguro_order_id = resposta.get("id", "")
            texto, png = pagseguro.extrair_pix(resposta)
            pag.pix_copia_e_cola = texto
            pag.pix_qrcode_url = png
            status, charge_id, _ = pagseguro.situacao_do_pedido(resposta)
            pag.pagseguro_charge_id = charge_id
            pag.status_provedor = status
        else:
            resposta = pagseguro.criar_checkout_cartao(pag, TIPO_CHECKOUT[metodo], url_retorno)
            pag.pagseguro_checkout_id = resposta.get("id", "")
            pag.link_pagamento = pagseguro.link_por_rel(resposta.get("links"), "PAY")
            pag.status_provedor = str(resposta.get("status", "")).upper()
        pag.resposta_bruta = resposta
        pag.save()
        EventoPagamento.objects.create(
            pagamento=pag, origem="criacao", autenticado=True,
            status_provedor=pag.status_provedor, payload=resposta,
        )
    except pagseguro.PagSeguroErro as exc:
        pag.status = StatusPagamento.ERRO
        pag.mensagem = str(exc)[:255]
        pag.resposta_bruta = exc.resposta
        pag.save()
        EventoPagamento.objects.create(pagamento=pag, origem="criacao", payload=exc.resposta)
    return pag


def sincronizar(pag, origem="consulta"):
    """Consulta o PagSeguro e aplica o status ao pedido.

    É a única forma de um pagamento PagSeguro confirmar um pedido.
    """
    if pag.provedor != "pagseguro" or pag.status == StatusPagamento.PAGO or not pagseguro.configurado():
        return pag
    try:
        order_id = pag.pagseguro_order_id
        if not order_id and pag.pagseguro_checkout_id:
            checkout = pagseguro.consultar_checkout(pag.pagseguro_checkout_id)
            ids = pagseguro.pedidos_do_checkout(checkout)
            if not ids:
                pag.status_provedor = str(checkout.get("status", "")).upper() or pag.status_provedor
                pag.save(update_fields=["status_provedor", "atualizado_em"])
                return pag
            order_id = ids[-1]
            pag.pagseguro_order_id = order_id
        if not order_id:
            return pag
        resposta = pagseguro.consultar_pedido(order_id)
    except pagseguro.PagSeguroErro as exc:
        logger.warning("Falha ao consultar pagamento %s: %s", pag.pk, exc)
        return pag

    status, charge_id, pago_centavos = pagseguro.situacao_do_pedido(resposta)
    EventoPagamento.objects.create(
        pagamento=pag, origem=origem, autenticado=True, status_provedor=status, payload=resposta,
    )
    pag.status_provedor = status
    pag.pagseguro_charge_id = charge_id or pag.pagseguro_charge_id
    pag.resposta_bruta = resposta

    esperado = int((pag.pedido.valor_total * 100).quantize(1))
    if status in pagseguro.STATUS_PAGO:
        if pago_centavos and pago_centavos < esperado:
            pag.status = StatusPagamento.ERRO
            pag.mensagem = "Valor pago diferente do valor do pedido. Verificação manual necessária."
            pag.save()
            logger.error("Pagamento %s com valor divergente (%s != %s)", pag.pk, pago_centavos, esperado)
            return pag
        pag.save()
        try:
            confirmar_pagamento(pag.pedido)
        except PedidoErro as exc:
            logger.warning("Pagamento %s aprovado mas pedido não confirmado: %s", pag.pk, exc)
        pag.refresh_from_db()
        return pag
    if status in pagseguro.STATUS_RECUSADO:
        pag.status = StatusPagamento.RECUSADO
        pag.mensagem = "Pagamento recusado ou cancelado pelo PagSeguro."
    pag.save()
    return pag


def confirmar_no_balcao(pedido, funcionario):
    """Funcionário confirma que recebeu o pagamento no balcão (modo sem PagSeguro)."""
    with transaction.atomic():
        pag = Pagamento.objects.select_for_update().filter(pedido=pedido).first()
        if pag is None:
            pag = Pagamento.objects.create(
                pedido=pedido, metodo_pagamento="balcao", valor_pago=pedido.valor_total, provedor="balcao",
            )
        if pag.provedor != "balcao":
            raise PedidoErro("Este pedido é pago pelo PagSeguro; a confirmação vem automaticamente da API.")
        if pedido.status != StatusPedido.AGUARDANDO_PAGAMENTO:
            raise PedidoErro("Este pedido não está aguardando pagamento.")
    return confirmar_pagamento(pedido, por=funcionario)
