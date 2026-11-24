from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from core.permissions import cliente_required
from pedidos.carrinho import CHAVE_SESSAO

from .models import estabelecimento as Estabelecimento, normalizar_codigo


@cliente_required
def escolher(request):
    """Tela principal de cantinas do cliente.

    Exibe apenas as cantinas salvas pelo usuário.
    Não lista todas as cantinas do sistema — o cliente encontra
    uma cantina digitando o código de acesso no campo de busca.
    """
    favoritos_qs = request.user.favoritos.filter(ativo=True)
    favoritos = set(favoritos_qs.values_list("pk", flat=True))
    atual = request.user.estabelecimento_atual
    if atual is not None and not atual.ativo:
        atual = None
    contexto = {
        "cantinas": list(favoritos_qs.order_by("nome")),
        "favoritos": favoritos,
        "atual": atual,
        "secao": "cantinas",
    }
    template = "estabelecimentos/escolher.html" if atual is None else "estabelecimentos/lista.html"
    return render(request, template, contexto)


@cliente_required
def buscar_por_codigo(request):
    """Busca uma cantina pelo código de acesso e exibe o resultado inline."""
    codigo = normalizar_codigo(request.GET.get("codigo", ""))
    cantina_encontrada = None
    erro = None

    if codigo:
        try:
            cantina_encontrada = Estabelecimento.objects.ativos().get(
                codigo_acesso__iexact=codigo
            )
        except Estabelecimento.DoesNotExist:
            erro = f'Nenhuma cantina encontrada com o código "{codigo}". Confira o código com a cantina.'
    elif "codigo" in request.GET:
        erro = "Digite o código da cantina."

    favoritos = set(request.user.favoritos.values_list("pk", flat=True))
    atual = request.user.estabelecimento_atual
    if atual is not None and not atual.ativo:
        atual = None

    contexto = {
        "codigo": codigo,
        "cantina_encontrada": cantina_encontrada,
        "erro": erro,
        "favoritos": favoritos,
        "atual": atual,
        "secao": "cantinas",
    }
    return render(request, "estabelecimentos/buscar.html", contexto)


@cliente_required
@require_POST
def selecionar(request, unique_id):
    cantina = get_object_or_404(Estabelecimento, unique_id=unique_id, ativo=True)
    # Conectar-se a uma cantina também a salva na conta do cliente.
    request.user.favoritos.add(cantina)
    if request.user.estabelecimento_atual_id != cantina.pk:
        request.user.estabelecimento_atual = cantina
        request.user.save(update_fields=["estabelecimento_atual"])
        request.session.pop(CHAVE_SESSAO, None)  # carrinho é por cantina
        messages.success(request, f"Agora você está comprando em {cantina.nome}.")
    return redirect("produtos:cardapio")


@cliente_required
@require_POST
def alternar_favorito(request, unique_id):
    cantina = get_object_or_404(Estabelecimento, unique_id=unique_id, ativo=True)
    if request.user.favoritos.filter(pk=cantina.pk).exists():
        request.user.favoritos.remove(cantina)
        messages.info(request, f"{cantina.nome} foi removida da sua conta.")
    else:
        request.user.favoritos.add(cantina)
        messages.success(request, f"{cantina.nome} foi salva na sua conta.")
    # Volta para a página que originou a ação (busca ou lista)
    next_url = request.GET.get("next") or request.POST.get("next") or ""
    if next_url.startswith("/"):
        return redirect(next_url)
    return redirect("estabelecimentos:escolher")


@cliente_required
def detalhes(request, unique_id):
    cantina = get_object_or_404(Estabelecimento, unique_id=unique_id, ativo=True)
    return render(request, "estabelecimentos/detalhes.html", {
        "cantina": cantina,
        "favorita": request.user.favoritos.filter(pk=cantina.pk).exists(),
        "atual": request.user.estabelecimento_atual_id == cantina.pk,
        "secao": "cantinas",
    })
