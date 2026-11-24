"""Painel do administrador da plataforma.

Somente administradores (permissão "admin" ou superusuário) acessam estas
views. É aqui que estabelecimentos são criados: o cadastro público só cria
clientes.
"""

from decimal import Decimal

from django.contrib import messages
from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from core.permissions import admin_required
from estabelecimentos.forms import EstabelecimentoForm
from estabelecimentos.models import estabelecimento as Estabelecimento
from pedidos.models import STATUS_VENDA, StatusPedido, pedido as Pedido
from produtos.models import Produto
from usuarios.forms import UsuarioAdminForm, VinculoForm
from usuarios.models import Permissao, Usuario, Vinculo


@admin_required
def painel(request):
    vendas = Pedido.objects.filter(status__in=STATUS_VENDA)
    receita = vendas.aggregate(total=Sum("valor_total"))["total"] or Decimal("0.00")
    # Agregações separadas evitam somas duplicadas por causa dos JOINs.
    vendas_por_estab = {
        linha["estabelecimento"]: linha
        for linha in vendas.values("estabelecimento").annotate(n=Count("id"), total=Sum("valor_total"))
    }
    por_estab = list(
        Estabelecimento.objects.annotate(
            n_funcionarios=Count("vinculos", filter=Q(vinculos__ativo=True), distinct=True),
        ).order_by("-ativo", "nome")
    )
    for estab in por_estab:
        dados = vendas_por_estab.get(estab.pk, {})
        estab.n_pedidos = dados.get("n", 0)
        estab.receita = dados.get("total") or Decimal("0.00")
    return render(request, "administracao/painel.html", {
        "receita": receita,
        "n_pedidos": vendas.count(),
        "n_aguardando": Pedido.objects.filter(status=StatusPedido.AGUARDANDO_PAGAMENTO).count(),
        "n_clientes": Usuario.objects.filter(permissao=Permissao.CLIENTE).count(),
        "n_funcionarios": Usuario.objects.filter(permissao=Permissao.FUNCIONARIO).count(),
        "n_estabelecimentos": Estabelecimento.objects.filter(ativo=True).count(),
        "n_produtos": Produto.objects.filter(ativo=True).count(),
        "estabelecimentos": por_estab,
        "secao": "admin_painel",
    })


# ---------------------------------------------------------------------------
# Estabelecimentos
# ---------------------------------------------------------------------------
@admin_required
def estabelecimentos(request):
    lista = Estabelecimento.objects.annotate(
        n_produtos=Count("produtos", distinct=True),
        n_funcionarios=Count("vinculos", filter=Q(vinculos__ativo=True), distinct=True),
    ).order_by("-ativo", "nome")
    return render(request, "administracao/estabelecimentos.html", {"estabelecimentos": lista, "secao": "admin_estab"})


@admin_required
def estabelecimento_form(request, unique_id=None):
    obj = get_object_or_404(Estabelecimento, unique_id=unique_id) if unique_id else None
    form = EstabelecimentoForm(request.POST or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        salvo = form.save()
        messages.success(request, f"Estabelecimento “{salvo.nome}” {'atualizado' if obj else 'cadastrado'}.")
        return redirect("administracao:estabelecimentos")
    return render(request, "administracao/estabelecimento_form.html", {
        "form": form, "objeto": obj, "secao": "admin_estab",
    })


@admin_required
@require_POST
def estabelecimento_ativo(request, unique_id):
    obj = get_object_or_404(Estabelecimento, unique_id=unique_id)
    obj.ativo = not obj.ativo
    obj.save(update_fields=["ativo", "atualizado_em"])
    if obj.ativo:
        messages.success(request, f"“{obj.nome}” reativado.")
    else:
        messages.info(request, f"“{obj.nome}” desativado: não aparece mais para clientes e não recebe pedidos.")
    return redirect("administracao:estabelecimentos")


# ---------------------------------------------------------------------------
# Usuários, permissões e vínculos
# ---------------------------------------------------------------------------
@admin_required
def usuarios(request):
    busca = request.GET.get("q", "").strip()
    papel = request.GET.get("papel", "")
    lista = Usuario.objects.all().order_by("nome")
    if busca:
        lista = lista.filter(Q(nome__icontains=busca) | Q(email__icontains=busca))
    if papel in Permissao.values:
        lista = lista.filter(permissao=papel)
    return render(request, "administracao/usuarios.html", {
        "usuarios": lista.prefetch_related("vinculos__estabelecimento")[:200],
        "busca": busca, "papel": papel, "papeis": Permissao.choices, "secao": "admin_usuarios",
    })


@admin_required
def usuario_form(request, pk=None):
    obj = get_object_or_404(Usuario, pk=pk) if pk else None
    form = UsuarioAdminForm(request.POST or None, instance=obj, editor=request.user)
    if request.method == "POST" and form.is_valid():
        salvo = form.save()
        messages.success(request, f"Usuário “{salvo.nome}” salvo.")
        return redirect("administracao:usuario_editar", pk=salvo.pk)
    vinculo_form = VinculoForm(usuario=obj) if obj else None
    return render(request, "administracao/usuario_form.html", {
        "form": form, "objeto": obj, "vinculo_form": vinculo_form,
        "vinculos": obj.vinculos.select_related("estabelecimento") if obj else [],
        "secao": "admin_usuarios",
    })


@admin_required
@require_POST
def vinculo_adicionar(request, pk):
    usuario = get_object_or_404(Usuario, pk=pk)
    form = VinculoForm(request.POST, usuario=usuario)
    if form.is_valid():
        vinculo = form.save(commit=False)
        vinculo.usuario = usuario
        vinculo.save()
        if usuario.permissao == Permissao.CLIENTE:
            usuario.permissao = Permissao.FUNCIONARIO
            usuario.save(update_fields=["permissao"])
            messages.info(request, "O usuário passou a ter a permissão de Funcionário.")
        messages.success(request, f"Vínculo com “{vinculo.estabelecimento}” criado.")
    else:
        for erros in form.errors.values():
            for erro in erros:
                messages.error(request, erro)
    return redirect("administracao:usuario_editar", pk=usuario.pk)


@admin_required
@require_POST
def vinculo_alternar(request, pk):
    vinculo = get_object_or_404(Vinculo, pk=pk)
    vinculo.ativo = not vinculo.ativo
    vinculo.save(update_fields=["ativo"])
    messages.success(request, f"Vínculo com “{vinculo.estabelecimento}” {'ativado' if vinculo.ativo else 'desativado'}.")
    return redirect("administracao:usuario_editar", pk=vinculo.usuario_id)


@admin_required
@require_POST
def vinculo_remover(request, pk):
    vinculo = get_object_or_404(Vinculo, pk=pk)
    usuario_id = vinculo.usuario_id
    vinculo.delete()
    messages.success(request, "Vínculo removido.")
    return redirect("administracao:usuario_editar", pk=usuario_id)
