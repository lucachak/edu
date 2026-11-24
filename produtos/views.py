from django.shortcuts import render
from django.utils import timezone

from core.permissions import cantina_required
from pedidos.carrinho import Carrinho

from .models import CardapioEspecial, Categoria, Produto


@cantina_required
def cardapio(request):
    estab = request.estabelecimento
    hoje = timezone.localdate()
    produtos = list(
        Produto.objects.ativos().filter(estabelecimento=estab).select_related("categoria")
    )
    carrinho = Carrinho(request, estab)
    for produto in produtos:
        produto.disponivel_hoje = 1
        produto.ofertado_hoje = True
        produto.no_carrinho = carrinho.quantidade_de(produto.pk)
    # Disponíveis primeiro; esgotados e não ofertados no fim.
    produtos.sort(key=lambda p: (p.categoria.ordem if p.categoria else 99, p.nome))
    categorias = Categoria.objects.filter(estabelecimento=estab, produtos__ativo=True).distinct()
    especiais = (
        CardapioEspecial.objects.filter(estabelecimento=estab, data=hoje, ativo=True)
        .prefetch_related("produtos")
    )
    return render(request, "produtos/cardapio.html", {
        "produtos": produtos,
        "categorias": categorias,
        "especiais": especiais,
        "secao": "cardapio",
    })
