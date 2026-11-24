import json
import logging

from django.contrib import messages
from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from core.permissions import cantina_required, cliente_required
from estabelecimentos.models import estabelecimento as Estabelecimento
from produtos.models import Produto
from usuarios.forms import CpfForm

from . import pagamentos, pagseguro
from .carrinho import Carrinho
from .models import EventoPagamento, StatusPagamento, StatusPedido, pagamento as Pagamento, pedido as Pedido
from .services import PedidoErro, cancelar_pedido, criar_pedido

logger = logging.getLogger("fastline.pedidos")

SESSAO_METODO = "fastline_checkout_metodo"


def _quer_json(request):
    return request.headers.get("x-requested-with") == "fetch" or "application/json" in request.headers.get("accept", "")


def _resposta_carrinho(request, carrinho, mensagem="", erro=False, status=200):
    if _quer_json(request):
        resumo = carrinho.resumo()
        html = render_to_string("pedidos/_carrinho.html", {"carrinho": resumo}, request=request)
        return JsonResponse({
            "ok": not erro,
            "mensagem": mensagem,
            "quantidade": resumo["quantidade_total"],
            "html": html,
        }, status=status)
    if mensagem:
        (messages.error if erro else messages.success)(request, mensagem)
    return redirect(request.POST.get("next") or "produtos:cardapio")


def _produto_da_cantina(request, produto_id):
    return get_object_or_404(Produto, pk=produto_id, estabelecimento=request.estabelecimento, ativo=True)


def _ler_quantidade(request, padrao=1):
    try:
        return int(request.POST.get("quantidade", padrao))
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Carrinho
# ---------------------------------------------------------------------------
@cantina_required
@require_GET
def carrinho(request):
    resumo = Carrinho(request, request.estabelecimento).resumo()
    if _quer_json(request):
        return _resposta_carrinho(request, Carrinho(request, request.estabelecimento))
    return render(request, "pedidos/carrinho.html", {"carrinho": resumo, "secao": "cardapio"})


@cantina_required
@require_POST
def carrinho_adicionar(request, produto_id):
    produto = _produto_da_cantina(request, produto_id)
    quantidade = _ler_quantidade(request)
    cart = Carrinho(request, request.estabelecimento)
    if quantidade is None or quantidade < 1:
        return _resposta_carrinho(request, cart, "Quantidade inválida.", erro=True, status=400)
    cart.adicionar(produto, quantidade)
    return _resposta_carrinho(request, cart, f"{produto.nome} adicionado ao carrinho.")


@cantina_required
@require_POST
def carrinho_atualizar(request, produto_id):
    produto = _produto_da_cantina(request, produto_id)
    quantidade = _ler_quantidade(request, padrao=0)
    cart = Carrinho(request, request.estabelecimento)
    if quantidade is None or quantidade < 0:
        return _resposta_carrinho(request, cart, "Quantidade inválida.", erro=True, status=400)
    cart.definir(produto, quantidade)
    return _resposta_carrinho(request, cart)


@cantina_required
@require_POST
def carrinho_remover(request, produto_id):
    cart = Carrinho(request, request.estabelecimento)
    cart.remover(produto_id)
    return _resposta_carrinho(request, cart, "Item removido do carrinho.")


# ---------------------------------------------------------------------------
# Checkout: etapa 2 (forma de pagamento) e etapa 3 (confirmação)
# ---------------------------------------------------------------------------
@cantina_required
def checkout(request):
    cart = Carrinho(request, request.estabelecimento)
    resumo = cart.resumo()
    if not resumo["linhas"]:
        messages.info(request, "Seu carrinho está vazio.")
        return redirect("produtos:cardapio")
    modo = pagamentos.modo_pagamento()
    erro = ""
    if request.method == "POST":
        metodo = request.POST.get("metodo")
        if metodo not in pagamentos.METODOS_CLIENTE:
            erro = "Selecione uma forma de pagamento."
        else:
            request.session[SESSAO_METODO] = metodo
            return redirect("pedidos:checkout_confirmar")
    return render(request, "pedidos/checkout_pagamento.html", {
        "carrinho": resumo,
        "metodo": request.session.get(SESSAO_METODO, ""),
        "modo": modo,
        "erro": erro,
        "etapa": 2,
    })


@cantina_required
def checkout_confirmar(request):
    cart = Carrinho(request, request.estabelecimento)
    resumo = cart.resumo()
    metodo = request.session.get(SESSAO_METODO)
    if not resumo["linhas"]:
        return redirect("produtos:cardapio")
    if metodo not in pagamentos.METODOS_CLIENTE:
        return redirect("pedidos:checkout")
    modo = pagamentos.modo_pagamento()
    precisa_cpf = modo == "pagseguro" and metodo == "pix" and not request.user.cpf
    cpf_form = CpfForm(request.POST or None) if precisa_cpf else None

    if request.method == "POST":
        if cpf_form is not None:
            if not cpf_form.is_valid():
                return render(request, "pedidos/checkout_confirmar.html", {
                    "carrinho": resumo, "metodo": metodo, "metodo_nome": pagamentos.METODOS_CLIENTE[metodo],
                    "modo": modo, "cpf_form": cpf_form, "etapa": 3,
                })
            # CPF usado apenas para esta cobrança real; não persistir no perfil.
            cpf_para_cobranca = cpf_form.cleaned_data["cpf"]
        try:
            novo = criar_pedido(request.user, request.estabelecimento, cart.itens, metodo_pagamento=metodo)
        except PedidoErro as exc:
            messages.error(request, str(exc))
            return redirect("produtos:cardapio")
        cart.limpar()
        request.session.pop(SESSAO_METODO, None)
        url_retorno = request.build_absolute_uri(reverse("pedidos:retorno", args=[novo.codigo]))
        pag = pagamentos.iniciar_pagamento(novo, metodo, url_retorno)
        if metodo == "simulado" and pag.status == StatusPagamento.PAGO:
            messages.success(request, "Pagamento simulado aprovado! Nenhum dinheiro real foi cobrado.")
            return redirect("pedidos:confirmado", codigo=novo.codigo)
        if pag.status == StatusPagamento.ERRO:
            messages.error(request, pag.mensagem)
        elif pag.link_pagamento:
            return redirect(pag.link_pagamento)
        return redirect("pedidos:pagamento", codigo=novo.codigo)

    return render(request, "pedidos/checkout_confirmar.html", {
        "carrinho": resumo,
        "metodo": metodo,
        "metodo_nome": pagamentos.METODOS_CLIENTE[metodo] if metodo == "simulado" or modo == "pagseguro" else "Pagamento no balcão",
        "modo": modo,
        "cpf_form": cpf_form,
        "etapa": 3,
    })


def _pedido_do_cliente(request, codigo):
    """Busca o pedido garantindo que pertence ao cliente logado."""
    return get_object_or_404(
        Pedido.objects.select_related("estabelecimento").prefetch_related("itens"),
        codigo=codigo, usuario=request.user,
    )


@cliente_required
def pagamento(request, codigo):
    p = _pedido_do_cliente(request, codigo)
    pag = Pagamento.objects.filter(pedido=p).first()
    if pag:
        pagamentos.sincronizar(pag)
        p.refresh_from_db()
    if p.status in (StatusPedido.CONFIRMADO, StatusPedido.EM_PREPARACAO, StatusPedido.PRONTO):
        return redirect("pedidos:confirmado", codigo=p.codigo)
    return render(request, "pedidos/pagamento.html", {
        "pedido": p, "pag": pag, "metodos": pagamentos.METODOS_CLIENTE, "etapa": 3,
    })


@cliente_required
@require_POST
def tentar_novamente(request, codigo):
    p = _pedido_do_cliente(request, codigo)
    metodo = request.POST.get("metodo")
    if p.status != StatusPedido.AGUARDANDO_PAGAMENTO or p.reserva_expirada:
        messages.error(request, "Este pedido não está mais aguardando pagamento.")
        return redirect("pedidos:pagamento", codigo=p.codigo)
    try:
        url_retorno = request.build_absolute_uri(reverse("pedidos:retorno", args=[p.codigo]))
        pag = pagamentos.iniciar_pagamento(p, metodo, url_retorno)
    except PedidoErro as exc:
        messages.error(request, str(exc))
        return redirect("pedidos:pagamento", codigo=p.codigo)
    if pag.status == StatusPagamento.ERRO:
        messages.error(request, pag.mensagem)
    elif pag.link_pagamento and metodo != "pix":
        return redirect(pag.link_pagamento)
    return redirect("pedidos:pagamento", codigo=p.codigo)


@cliente_required
def retorno(request, codigo):
    """Volta da página do PagBank. Não confia no retorno: consulta a API."""
    p = _pedido_do_cliente(request, codigo)
    pag = Pagamento.objects.filter(pedido=p).first()
    if pag:
        pagamentos.sincronizar(pag, origem="retorno")
    return redirect("pedidos:pagamento", codigo=p.codigo)


@cliente_required
@require_GET
def status_pedido(request, codigo):
    """Consultado pelo JavaScript enquanto o cliente aguarda o pagamento."""
    p = _pedido_do_cliente(request, codigo)
    pag = Pagamento.objects.filter(pedido=p).first()
    if pag and p.status == StatusPedido.AGUARDANDO_PAGAMENTO:
        pagamentos.sincronizar(pag)
        p.refresh_from_db()
    return JsonResponse({
        "status": p.status,
        "status_nome": p.get_status_display(),
        "confirmado": p.status in (StatusPedido.CONFIRMADO, StatusPedido.EM_PREPARACAO, StatusPedido.PRONTO),
        "url": reverse("pedidos:confirmado", args=[p.codigo]),
    })


@cliente_required
def confirmado(request, codigo):
    p = _pedido_do_cliente(request, codigo)
    if not p.token_retirada:
        return redirect("pedidos:pagamento", codigo=p.codigo)
    return render(request, "pedidos/confirmado.html", {"pedido": p, "pag": getattr(p, "pagamento", None)})


@cliente_required
@require_POST
def cancelar(request, codigo):
    """O cliente só pode desistir de um pedido que ainda não foi pago."""
    p = _pedido_do_cliente(request, codigo)
    if p.status != StatusPedido.AGUARDANDO_PAGAMENTO:
        messages.error(request, "Só é possível cancelar pedidos que ainda aguardam pagamento.")
    else:
        try:
            cancelar_pedido(p, motivo="Cancelado pelo cliente antes do pagamento.")
            messages.success(request, "Pedido cancelado. As unidades voltaram para o cardápio.")
        except PedidoErro as exc:
            messages.error(request, str(exc))
    return redirect("pedidos:tickets")


@cliente_required
def tickets(request):
    pedidos_base = Pedido.objects.filter(usuario=request.user)
    estabelecimentos = Estabelecimento.objects.filter(
        pedidos__usuario=request.user
    ).distinct().order_by("nome")
    cantina_id = request.GET.get("cantina", "").strip()
    if cantina_id.isdigit():
        pedidos_base = pedidos_base.filter(estabelecimento_id=int(cantina_id))
    pedidos = pedidos_base.select_related("estabelecimento", "pagamento").prefetch_related("itens")
    return render(request, "pedidos/tickets.html", {
        "pedidos": pedidos,
        "estabelecimentos_ticket": estabelecimentos,
        "cantina_filtro": cantina_id,
        "secao": "tickets",
    })


# ---------------------------------------------------------------------------
# Webhook do PagSeguro
# ---------------------------------------------------------------------------
@csrf_exempt
@require_POST
def webhook_pagseguro(request):
    corpo = request.body
    try:
        dados = json.loads(corpo.decode("utf-8") or "{}")
    except (UnicodeDecodeError, json.JSONDecodeError):
        return HttpResponseBadRequest("JSON inválido")

    autentico = pagseguro.assinatura_valida(corpo, request.headers.get("x-authenticity-token", ""))
    if not autentico:
        EventoPagamento.objects.create(origem="webhook", autenticado=False, payload=dados if isinstance(dados, dict) else {})
        logger.warning("Webhook do PagSeguro com assinatura inválida descartado")
        return HttpResponse("assinatura inválida", status=401)

    referencia = str(dados.get("reference_id", "")) if isinstance(dados, dict) else ""
    produto_id = request.headers.get("x-product-id", "") or (dados.get("id", "") if isinstance(dados, dict) else "")
    pag = None
    if referencia:
        pag = Pagamento.objects.filter(referencia__iexact=referencia).first() if _uuid_valido(referencia) else None
    if pag is None and produto_id:
        pag = (
            Pagamento.objects.filter(pagseguro_order_id=produto_id).first()
            or Pagamento.objects.filter(pagseguro_checkout_id=produto_id).first()
        )
    EventoPagamento.objects.create(
        pagamento=pag, origem="webhook", autenticado=True,
        status_provedor=str((dados.get("charges") or [{}])[0].get("status", "")) if isinstance(dados, dict) and dados.get("charges") else "",
        payload=dados if isinstance(dados, dict) else {},
    )
    if pag is None:
        return HttpResponse("ok (pagamento desconhecido)")
    if not pag.pagseguro_order_id and str(produto_id).startswith("ORDE_"):
        pag.pagseguro_order_id = produto_id
        pag.save(update_fields=["pagseguro_order_id", "atualizado_em"])
    # Não confia no corpo da notificação: consulta a API antes de confirmar.
    pagamentos.sincronizar(pag, origem="webhook")
    return HttpResponse("ok")


def _uuid_valido(valor):
    import uuid

    try:
        uuid.UUID(str(valor))
        return True
    except ValueError:
        return False
