"""Integração com a API de Pedidos/Checkout do PagSeguro (PagBank).

Documentação oficial consultada em 04/11/2026:
- Ambientes: https://developer.pagbank.com.br/docs/ambientes-disponiveis
- Pedido com PIX: https://developer.pagbank.com.br/reference/criar-pedido-com-qr-code-pix-v2
- Consultar pedido: https://developer.pagbank.com.br/reference/consultar-pedido
- Checkout (página de pagamento): https://developer.pagbank.com.br/reference/criar-checkout
- Autenticidade dos webhooks: https://developer.pagbank.com.br/reference/confirmar-autenticidade-da-notificacao

Regras de segurança adotadas:
- O token fica só no servidor (variável de ambiente PAGSEGURO_TOKEN).
- O pedido só é confirmado depois que o backend consulta a API do
  PagSeguro e recebe o status PAID com o valor correto. Nem o retorno do
  navegador nem o corpo do webhook são aceitos sozinhos como prova.
- Webhooks têm a assinatura ``x-authenticity-token`` validada.
"""

import hashlib
import hmac
import logging
from datetime import timedelta

import requests
from django.conf import settings
from django.urls import reverse
from django.utils import timezone

logger = logging.getLogger("fastline.pagseguro")

URLS_BASE = {
    "sandbox": "https://sandbox.api.pagseguro.com",
    "producao": "https://api.pagseguro.com",
}

STATUS_PAGO = {"PAID"}
STATUS_RECUSADO = {"DECLINED", "CANCELED"}


class PagSeguroErro(Exception):
    """Falha de comunicação ou resposta de erro da API."""

    def __init__(self, mensagem, resposta=None):
        super().__init__(mensagem)
        self.resposta = resposta or {}


def configurado():
    return bool(settings.PAGSEGURO_TOKEN)


def ambiente():
    return "producao" if settings.PAGSEGURO_AMBIENTE == "producao" else "sandbox"


def url_base():
    return URLS_BASE[ambiente()]


def _cabecalhos():
    return {
        "Authorization": f"Bearer {settings.PAGSEGURO_TOKEN}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _requisicao(metodo, caminho, json=None):
    if not configurado():
        raise PagSeguroErro("Integração com PagSeguro não configurada (defina PAGSEGURO_TOKEN no .env).")
    url = f"{url_base()}{caminho}"
    try:
        resposta = requests.request(
            metodo, url, json=json, headers=_cabecalhos(), timeout=settings.PAGSEGURO_TIMEOUT,
        )
    except requests.RequestException as exc:
        logger.warning("Falha de rede com o PagSeguro: %s", exc)
        raise PagSeguroErro("Não foi possível falar com o PagSeguro. Tente novamente em instantes.") from exc
    try:
        dados = resposta.json()
    except ValueError:
        dados = {"conteudo": resposta.text[:500]}
    if resposta.status_code >= 400:
        logger.warning("PagSeguro respondeu %s em %s: %s", resposta.status_code, caminho, dados)
        raise PagSeguroErro(_mensagem_de_erro(dados), dados)
    return dados


def _mensagem_de_erro(dados):
    erros = dados.get("error_messages") if isinstance(dados, dict) else None
    if erros:
        partes = [e.get("description") or e.get("message") or e.get("code", "") for e in erros]
        return "PagSeguro recusou a solicitação: " + "; ".join(p for p in partes if p)
    return "PagSeguro recusou a solicitação."


def _centavos(valor):
    return int((valor * 100).quantize(1))


def _url_publica(nome_rota, *args):
    base = settings.PAGSEGURO_URL_PUBLICA
    if not base:
        return None
    return f"{base}{reverse(nome_rota, args=args)}"


def _cliente(usuario):
    cliente = {"name": usuario.nome[:120], "email": usuario.email}
    if usuario.cpf:
        cliente["tax_id"] = usuario.cpf
    telefone = "".join(c for c in (usuario.telefone or "") if c.isdigit())
    if len(telefone) in (10, 11):
        cliente["phones"] = [{
            "country": "55", "area": telefone[:2], "number": telefone[2:], "type": "MOBILE",
        }]
    return cliente


def _itens(pedido):
    return [
        {
            "reference_id": str(item.produto_id),
            "name": item.nome_produto[:64] or "Produto",
            "quantity": item.quantidade,
            "unit_amount": _centavos(item.preco_unitario),
        }
        for item in pedido.itens.all()
    ]


def _expiracao(pedido):
    limite = pedido.reserva_expira_em or (timezone.now() + timedelta(minutes=settings.FASTLINE_RESERVA_MINUTOS))
    return timezone.localtime(limite).replace(microsecond=0).isoformat()


# ---------------------------------------------------------------------------
# Criação de cobranças
# ---------------------------------------------------------------------------
def criar_pedido_pix(pagamento):
    """POST /orders com cobrança PIX. Retorna o JSON da API."""
    pedido = pagamento.pedido
    corpo = {
        "reference_id": str(pagamento.referencia),
        "customer": _cliente(pedido.usuario),
        "items": _itens(pedido),
        "charges": [{
            "reference_id": str(pagamento.referencia),
            "description": f"FastLine pedido {pedido.pk}"[:64],
            "amount": {"value": _centavos(pedido.valor_total), "currency": "BRL"},
            "payment_method": {"type": "PIX", "pix": {"expiration_date": _expiracao(pedido)}},
        }],
    }
    webhook = _url_publica("pedidos:webhook_pagseguro")
    if webhook:
        corpo["notification_urls"] = [webhook]  # a API aceita uma URL por enquanto
    return _requisicao("POST", "/orders", json=corpo)


def criar_checkout_cartao(pagamento, tipo, url_retorno):
    """POST /checkouts (página de pagamento do PagBank) para cartão.

    ``tipo`` é CREDIT_CARD ou DEBIT_CARD. Os dados do cartão são digitados na
    página do PagBank e nunca passam pelo servidor do FastLine.
    """
    pedido = pagamento.pedido
    usuario = pedido.usuario
    corpo = {
        "reference_id": str(pagamento.referencia),
        "expiration_date": _expiracao(pedido),
        "items": _itens(pedido),
        "payment_methods": [{"type": tipo}],
        "redirect_url": url_retorno,
        "return_url": url_retorno,
    }
    if usuario.cpf:
        corpo["customer"] = _cliente(usuario)
        corpo["customer_modifiable"] = False
    else:
        corpo["customer_modifiable"] = True
    if pedido.taxa_servico:
        corpo["additional_amount"] = _centavos(pedido.taxa_servico)
    webhook = _url_publica("pedidos:webhook_pagseguro")
    if webhook:
        corpo["notification_urls"] = [webhook]
        corpo["payment_notification_urls"] = [webhook]
    return _requisicao("POST", "/checkouts", json=corpo)


def consultar_pedido(order_id):
    return _requisicao("GET", f"/orders/{order_id}")


def consultar_checkout(checkout_id):
    return _requisicao("GET", f"/checkouts/{checkout_id}")


# ---------------------------------------------------------------------------
# Leitura das respostas
# ---------------------------------------------------------------------------
def link_por_rel(links, rel):
    for link in links or []:
        if str(link.get("rel", "")).upper() == rel:
            return link.get("href", "")
    return ""


def extrair_pix(resposta):
    """Retorna (copia_e_cola, url_png) aceitando o formato atual e o legado."""
    for charge in resposta.get("charges") or []:
        texto = (charge.get("qr_code") or {}).get("text", "")
        png = link_por_rel(charge.get("links"), "QRCODE.PNG")
        if texto or png:
            return texto, png
    for qr in resposta.get("qr_codes") or []:  # formato antigo (depreciado)
        return qr.get("text", ""), link_por_rel(qr.get("links"), "QRCODE.PNG")
    return "", ""


def situacao_do_pedido(resposta):
    """Resume um pedido do PagSeguro: (status, charge_id, valor_pago_centavos)."""
    charges = resposta.get("charges") or []
    for charge in charges:
        status = str(charge.get("status", "")).upper()
        if status in STATUS_PAGO:
            resumo = (charge.get("amount") or {}).get("summary") or {}
            pago = resumo.get("paid") or (charge.get("amount") or {}).get("value") or 0
            return status, charge.get("id", ""), int(pago)
    if charges:
        ultima = charges[-1]
        return str(ultima.get("status", "")).upper(), ultima.get("id", ""), 0
    return "WAITING", "", 0


def pedidos_do_checkout(resposta):
    """IDs de pedidos (ORDE_...) associados a um checkout."""
    ids = []
    for chave in ("orders", "order"):
        valor = resposta.get(chave)
        if isinstance(valor, dict):
            valor = [valor]
        for item in valor or []:
            if isinstance(item, dict) and item.get("id"):
                ids.append(item["id"])
            elif isinstance(item, str):
                ids.append(item)
    return ids


# ---------------------------------------------------------------------------
# Webhook
# ---------------------------------------------------------------------------
def assinatura_valida(corpo_bruto: bytes, assinatura: str) -> bool:
    """Confere ``x-authenticity-token`` = SHA-256 de ``{token}-{payload}``."""
    if not configurado() or not assinatura:
        return False
    texto = settings.PAGSEGURO_TOKEN.encode() + b"-" + corpo_bruto
    esperado = hashlib.sha256(texto).hexdigest()
    return hmac.compare_digest(esperado, assinatura.strip().lower())
