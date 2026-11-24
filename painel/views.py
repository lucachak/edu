"""Painel do funcionário (operador de cantina).

Toda consulta é filtrada por ``request.estabelecimento``, que o decorador
``funcionario_required`` define a partir dos vínculos ativos do usuário.
Assim um funcionário nunca enxerga ou altera dados de outra cantina.
"""

from collections import OrderedDict, defaultdict
from datetime import timedelta
from decimal import Decimal

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, ProtectedError, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from urllib.parse import urlencode
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.permissions import SESSION_ESTAB_FUNCIONARIO, funcionario_required
from pedidos import pagamentos
from pedidos.models import STATUS_VENDA, StatusPedido, item_pedido, pedido as Pedido
from usuarios.models import Vinculo
from pedidos.services import (
    PedidoErro,
    atualizar_status,
    buscar_por_token,
    confirmar_retirada,
    expirar_reservas_vencidas,
)
from produtos.forms import CardapioEspecialForm, ProdutoForm
from produtos.models import CardapioEspecial, Categoria, DisponibilidadeOnline, Produto, movimentacao

DIAS_SEMANA = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]

FILTROS_PEDIDOS = OrderedDict([
    ("ativos", ("Em andamento", [StatusPedido.CONFIRMADO, StatusPedido.EM_PREPARACAO])),
    ("prontos", ("Aguardando retirada", [StatusPedido.PRONTO])),
    ("pagamento", ("Aguardando pagamento", [StatusPedido.AGUARDANDO_PAGAMENTO])),
    ("finalizados", ("Retirados", [StatusPedido.RETIRADO])),
    ("cancelados", ("Cancelados", [StatusPedido.CANCELADO])),
])


def _registrar(produto, usuario, tipo, detalhe=""):
    movimentacao.objects.create(produto=produto, funcionario=usuario, tipo_movimentacao=tipo, detalhe=detalhe[:200])


# ---------------------------------------------------------------------------
# Pedidos
# ---------------------------------------------------------------------------
@funcionario_required
def pedidos(request):
    expirar_reservas_vencidas()
    estab = request.estabelecimento
    DisponibilidadeOnline.abrir_dia(estab)
    filtro = request.GET.get("filtro", "ativos")
    if filtro not in FILTROS_PEDIDOS:
        filtro = "ativos"
    base = Pedido.objects.filter(estabelecimento=estab)
    contagens = {
        chave: base.filter(status__in=status).count() for chave, (_, status) in FILTROS_PEDIDOS.items()
    }
    lista = (
        base.filter(status__in=FILTROS_PEDIDOS[filtro][1])
        .select_related("usuario", "pagamento")
        .prefetch_related("itens")
        .order_by("data_pedido" if filtro in ("ativos", "prontos", "pagamento") else "-data_pedido")[:100]
    )
    return render(request, "painel/pedidos.html", {
        "pedidos": lista,
        "filtro": filtro,
        "filtros": [(k, v[0], contagens[k]) for k, v in FILTROS_PEDIDOS.items()],
        "secao": "pedidos",
    })


@funcionario_required
@require_POST
def pedido_status(request, pk):
    p = get_object_or_404(Pedido, pk=pk, estabelecimento=request.estabelecimento)
    novo = request.POST.get("status")
    if novo not in StatusPedido.values:
        messages.error(request, "Status inválido.")
    else:
        try:
            atualizar_status(p, novo, request.user)
            messages.success(request, f"Pedido #{p.pk} agora está “{StatusPedido(novo).label}”.")
        except PedidoErro as exc:
            messages.error(request, str(exc))
    return redirect(request.POST.get("next") or "painel:pedidos")


@funcionario_required
@require_POST
def pedido_pagamento_balcao(request, pk):
    p = get_object_or_404(Pedido, pk=pk, estabelecimento=request.estabelecimento)
    try:
        p = pagamentos.confirmar_no_balcao(p, request.user)
        messages.success(request, f"Pagamento do pedido #{p.pk} confirmado. Token: {p.token_retirada}")
    except PedidoErro as exc:
        messages.error(request, str(exc))
    return redirect(request.POST.get("next") or "painel:pedidos")


# ---------------------------------------------------------------------------
# Verificar token
# ---------------------------------------------------------------------------
@funcionario_required
def token(request):
    codigo = (request.GET.get("token") or "").strip()
    encontrado = buscar_por_token(codigo, request.estabelecimento) if codigo else None
    return render(request, "painel/token.html", {
        "token": codigo,
        "pedido": encontrado,
        "buscou": bool(codigo),
        "secao": "token",
    })


@funcionario_required
@require_POST
def token_confirmar(request):
    codigo = request.POST.get("token", "")
    try:
        p = confirmar_retirada(codigo, request.estabelecimento, request.user)
        messages.success(request, f"Retirada do pedido #{p.pk} confirmada. Bom apetite, {p.usuario.get_short_name()}!")
    except PedidoErro as exc:
        messages.error(request, str(exc))
    return redirect(f"{reverse('painel:token')}?{urlencode({'token': codigo})}")


# ---------------------------------------------------------------------------
# Gerenciar itens e disponibilidade online
# ---------------------------------------------------------------------------
@funcionario_required
def itens(request):
    estab = request.estabelecimento
    hoje = timezone.localdate()
    pode_editar = bool(request.vinculo and request.vinculo.pode_gerenciar_produtos)
    form = ProdutoForm(estabelecimento=estab)
    if request.method == "POST":
        if not pode_editar:
            messages.error(request, "Seu vínculo não permite gerenciar produtos.")
            return redirect("painel:itens")
        form = ProdutoForm(request.POST, request.FILES, estabelecimento=estab)
        if form.is_valid():
            with transaction.atomic():
                produto = form.save()
                _registrar(produto, request.user, "adicionado")
            messages.success(request, f"“{produto.nome}” cadastrado.")
            return redirect("painel:itens")
        messages.error(request, "Corrija os campos destacados.")

    produtos = list(Produto.objects.filter(estabelecimento=estab).select_related("categoria").order_by("-ativo", "nome"))
    ativos = [p for p in produtos if p.ativo]
    return render(request, "painel/itens.html", {
        "produtos": produtos,
        "categorias": Categoria.objects.filter(estabelecimento=estab),
        "form": form,
        "pode_editar": pode_editar,
        "total": len(ativos),
        "disponiveis": len(ativos),
        "sem_estoque": 0,
        "hoje": hoje,
        "secao": "itens",
    })


@funcionario_required(gerenciar_produtos=True)
def produto_editar(request, pk):
    produto = get_object_or_404(Produto, pk=pk, estabelecimento=request.estabelecimento)
    form = ProdutoForm(request.POST or None, request.FILES or None, instance=produto, estabelecimento=request.estabelecimento)
    if request.method == "POST" and form.is_valid():
        form.save()
        _registrar(produto, request.user, "editado")
        messages.success(request, f"“{produto.nome}” atualizado.")
        return redirect("painel:itens")
    return render(request, "painel/produto_form.html", {"form": form, "produto": produto, "secao": "itens"})


@funcionario_required(gerenciar_produtos=True)
@require_POST
def produto_remover(request, pk):
    produto = get_object_or_404(Produto, pk=pk, estabelecimento=request.estabelecimento)
    nome = produto.nome
    try:
        with transaction.atomic():
            produto.delete()
        messages.success(request, f"“{nome}” removido.")
    except ProtectedError:
        # Produtos com pedidos não podem ser apagados (histórico); são desativados.
        produto.ativo = False
        produto.save(update_fields=["ativo", "atualizado_em"])
        _registrar(produto, request.user, "excluido", "Desativado (possui pedidos)")
        messages.info(request, f"“{nome}” tem pedidos registrados e foi desativado em vez de apagado.")
    return redirect("painel:itens")




# ---------------------------------------------------------------------------
# Cardápio especial / almoço do dia
# ---------------------------------------------------------------------------
@funcionario_required
def especiais(request):
    estab = request.estabelecimento
    pode_editar = bool(request.vinculo and request.vinculo.pode_gerenciar_produtos)
    form = CardapioEspecialForm(request.POST or None, request.FILES or None, estabelecimento=estab)
    if request.method == "POST":
        if not pode_editar:
            messages.error(request, "Seu vínculo não permite gerenciar o cardápio.")
            return redirect("painel:especiais")
        if form.is_valid():
            form.save()
            messages.success(request, "Cardápio especial publicado.")
            return redirect("painel:especiais")
    lista = CardapioEspecial.objects.filter(estabelecimento=estab).prefetch_related("produtos")[:30]
    return render(request, "painel/especiais.html", {
        "form": form, "especiais": lista, "pode_editar": pode_editar, "secao": "especiais",
    })


@funcionario_required(gerenciar_produtos=True)
@require_POST
def especial_remover(request, pk):
    obj = get_object_or_404(CardapioEspecial, pk=pk, estabelecimento=request.estabelecimento)
    obj.delete()
    messages.success(request, "Cardápio especial removido.")
    return redirect("painel:especiais")


# ---------------------------------------------------------------------------
# Registro de vendas e dashboard
# ---------------------------------------------------------------------------
def _resumo_vendas(estab, desde=None):
    vendas = Pedido.objects.filter(estabelecimento=estab, status__in=STATUS_VENDA)
    if desde:
        vendas = vendas.filter(confirmado_em__date__gte=desde)
    agregado = vendas.aggregate(receita=Sum("valor_total"), quantidade=Count("id"))
    receita = agregado["receita"] or Decimal("0.00")
    quantidade = agregado["quantidade"] or 0
    ticket = (receita / quantidade).quantize(Decimal("0.01")) if quantidade else Decimal("0.00")
    return vendas, receita, quantidade, ticket


@funcionario_required
def vendas(request):
    vendas_qs, receita, quantidade, ticket = _resumo_vendas(request.estabelecimento)
    ultimos = vendas_qs.select_related("usuario").prefetch_related("itens").order_by("-confirmado_em")[:30]
    return render(request, "painel/vendas.html", {
        "receita": receita, "quantidade": quantidade, "ticket": ticket, "pedidos": ultimos, "secao": "vendas",
    })


@funcionario_required
def dashboard(request):
    estab = request.estabelecimento
    hoje = timezone.localdate()
    inicio = hoje - timedelta(days=6)
    _, receita, quantidade, ticket = _resumo_vendas(estab)
    ativos = Produto.objects.filter(estabelecimento=estab, ativo=True).count()

    # Receita dos últimos 7 dias por categoria (barras empilhadas em SVG/CSS).
    itens_semana = (
        item_pedido.objects.filter(
            pedido__estabelecimento=estab, pedido__status__in=STATUS_VENDA,
            pedido__confirmado_em__date__gte=inicio,
        ).select_related("pedido", "produto__categoria")
    )
    por_dia = OrderedDict(((inicio + timedelta(days=i)), defaultdict(Decimal)) for i in range(7))
    categorias = OrderedDict()
    for item in itens_semana:
        dia = timezone.localtime(item.pedido.confirmado_em).date()
        if dia not in por_dia:
            continue
        nome_cat = item.produto.categoria.nome if item.produto.categoria else "Outros"
        categorias.setdefault(nome_cat, len(categorias))
        por_dia[dia][nome_cat] += item.subtotal
    maximo = max([sum(v.values(), Decimal(0)) for v in por_dia.values()] + [Decimal(1)])
    colunas = []
    for dia, valores in por_dia.items():
        total_dia = sum(valores.values(), Decimal(0))
        colunas.append({
            "rotulo": DIAS_SEMANA[dia.weekday()],
            "data": dia,
            "total": total_dia,
            "segmentos": [
                {"categoria": cat, "indice": idx % 6, "valor": valores.get(cat, Decimal(0)),
                 "altura": float(valores.get(cat, Decimal(0)) / maximo * 100)}
                for cat, idx in categorias.items() if valores.get(cat)
            ],
        })
    return render(request, "painel/dashboard.html", {
        "cantina": estab,
        "link_codigo": request.build_absolute_uri(
            reverse("estabelecimentos:buscar") + "?" + urlencode({"codigo": estab.codigo_acesso})
        ),
        "receita": receita, "quantidade": quantidade, "ticket": ticket,
        "baixo_estoque": 0,
        "colunas": colunas,
        "legenda": [(cat, idx % 6) for cat, idx in categorias.items()],
        "maximo": maximo,
        "secao": "dashboard",
    })


@funcionario_required
@require_POST
def trocar_estabelecimento(request):
    estab_id = request.POST.get("estabelecimento")
    if request.user.estabelecimentos_vinculados().filter(pk=estab_id).exists():
        request.session[SESSION_ESTAB_FUNCIONARIO] = int(estab_id)
        messages.success(request, "Estabelecimento alterado.")
    else:
        messages.error(request, "Você não tem vínculo com esse estabelecimento.")
    return redirect("painel:pedidos")


@funcionario_required
@require_POST
def regenerar_codigo_cantina(request):
    """Gerente troca o código que os clientes usam para se conectar à cantina."""
    if not (request.user.is_superuser or (request.vinculo and request.vinculo.funcao == "gerente")):
        messages.error(request, "Somente o gerente da cantina pode gerar um novo código.")
        return redirect("painel:dashboard")
    codigo = request.estabelecimento.regenerar_codigo_acesso()
    messages.success(request, f"Novo código da cantina: {codigo}. O código antigo deixou de funcionar.")
    return redirect("painel:dashboard")


@funcionario_required
def funcionarios_pendentes(request):
    if not (request.user.is_superuser or (request.vinculo and request.vinculo.funcao == "gerente")):
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied("Somente o gerente da cantina pode aprovar funcionários.")
    pendentes = Vinculo.objects.filter(estabelecimento=request.estabelecimento, ativo=False).select_related("usuario").order_by("criado_em")
    return render(request, "painel/funcionarios.html", {"pendentes": pendentes, "secao": "funcionarios"})


@funcionario_required
@require_POST
def aprovar_funcionario(request, pk):
    if not (request.user.is_superuser or (request.vinculo and request.vinculo.funcao == "gerente")):
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied("Somente o gerente da cantina pode aprovar funcionários.")
    vinculo = get_object_or_404(Vinculo, pk=pk, estabelecimento=request.estabelecimento, ativo=False)
    vinculo.ativo = True
    vinculo.pode_gerenciar_produtos = True
    vinculo.save(update_fields=["ativo", "pode_gerenciar_produtos"])
    messages.success(request, f"Acesso de {vinculo.usuario.nome} aprovado.")
    return redirect("painel:funcionarios")
