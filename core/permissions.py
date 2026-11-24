"""Verificações de permissão feitas no backend.

Todas as views protegidas usam estes decoradores. Esconder botões no
frontend é só conveniência; a regra de acesso fica aqui.
"""

from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect

from estabelecimentos.models import estabelecimento as Estabelecimento

SESSION_ESTAB_FUNCIONARIO = "fastline_estab_funcionario"


def cliente_required(view):
    @login_required
    @wraps(view)
    def _wrapped(request, *args, **kwargs):
        if not request.user.eh_cliente:
            raise PermissionDenied("Área exclusiva para clientes.")
        return view(request, *args, **kwargs)

    return _wrapped


def admin_required(view):
    @login_required
    @wraps(view)
    def _wrapped(request, *args, **kwargs):
        if not request.user.eh_admin:
            raise PermissionDenied("Área exclusiva para administradores.")
        return view(request, *args, **kwargs)

    return _wrapped


def estabelecimento_do_funcionario(request):
    """Retorna o estabelecimento em que o funcionário está trabalhando.

    Só considera estabelecimentos ativos com vínculo ativo. Se o funcionário
    tiver mais de um vínculo, a escolha fica na sessão, mas é sempre
    revalidada contra o banco.
    """
    usuario = request.user
    vinculados = usuario.estabelecimentos_vinculados()
    escolhido_id = request.session.get(SESSION_ESTAB_FUNCIONARIO)
    if escolhido_id:
        estab = vinculados.filter(pk=escolhido_id).first()
        if estab:
            return estab
    return vinculados.first()


def funcionario_required(view=None, *, gerenciar_produtos=False):
    """Exige funcionário com vínculo ativo; injeta ``request.estabelecimento``."""

    def decorator(func):
        @login_required
        @wraps(func)
        def _wrapped(request, *args, **kwargs):
            if not request.user.eh_funcionario:
                raise PermissionDenied("Área exclusiva para funcionários de cantina.")
            estab = estabelecimento_do_funcionario(request)
            if estab is None:
                raise PermissionDenied(
                    "Seu usuário não está vinculado a nenhum estabelecimento ativo. Procure o administrador."
                )
            vinculo = request.user.vinculo_com(estab)
            if gerenciar_produtos and not (vinculo and vinculo.pode_gerenciar_produtos):
                raise PermissionDenied("Seu vínculo não permite gerenciar produtos.")
            request.estabelecimento = estab
            request.vinculo = vinculo
            return func(request, *args, **kwargs)

        return _wrapped

    if view is not None:
        return decorator(view)
    return decorator


def cantina_do_cliente(request):
    """Cantina ativa selecionada pelo cliente (ou None)."""
    estab = request.user.estabelecimento_atual
    if estab is not None and not estab.ativo:
        return None
    return estab


def cantina_required(view):
    """Cliente precisa ter escolhido uma cantina ativa antes de comprar."""

    @cliente_required
    @wraps(view)
    def _wrapped(request, *args, **kwargs):
        estab = cantina_do_cliente(request)
        if estab is None:
            return redirect("estabelecimentos:escolher")
        request.estabelecimento = estab
        return view(request, *args, **kwargs)

    return _wrapped


def destino_inicial(usuario):
    """URL inicial conforme o papel do usuário."""
    if usuario.eh_admin:
        return "administracao:painel"
    if usuario.eh_funcionario:
        return "painel:pedidos"
    if usuario.estabelecimento_atual_id and Estabelecimento.objects.filter(
        pk=usuario.estabelecimento_atual_id, ativo=True
    ).exists():
        return "produtos:cardapio"
    return "estabelecimentos:escolher"
