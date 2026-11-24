from django.conf import settings
from django.urls import reverse

from .permissions import estabelecimento_do_funcionario


def _nav_cliente():
    return [
        ("cardapio", "Cardápio", reverse("produtos:cardapio"), "book"),
        ("tickets", "Meus tickets", reverse("pedidos:tickets"), "ticket"),
        ("cantinas", "Cantinas", reverse("estabelecimentos:escolher"), "store"),
        ("perfil", "Minha conta", reverse("usuarios:perfil"), "user"),
    ]


def _nav_funcionario():
    return [
        ("pedidos", "Pedidos", reverse("painel:pedidos"), "list"),
        ("itens", "Gerenciar Itens", reverse("painel:itens"), "box"),
        ("especiais", "Cardápio do Dia", reverse("painel:especiais"), "book"),
        ("vendas", "Registro de Vendas", reverse("painel:vendas"), "file"),
        ("dashboard", "Dashboard", reverse("painel:dashboard"), "chart"),
        ("token", "Verificar Token", reverse("painel:token"), "dollar"),
    ]


def _nav_admin():
    return [
        ("admin_painel", "Visão geral", reverse("administracao:painel"), "chart"),
        ("admin_estab", "Estabelecimentos", reverse("administracao:estabelecimentos"), "store"),
        ("admin_usuarios", "Usuários", reverse("administracao:usuarios"), "user"),
        ("perfil", "Minha conta", reverse("usuarios:perfil"), "user"),
    ]


def fastline(request):
    usuario = getattr(request, "user", None)
    if usuario is None or not usuario.is_authenticated:
        return {}
    contexto = {"papel": "cliente", "reserva_minutos": settings.FASTLINE_RESERVA_MINUTOS}
    if usuario.eh_admin:
        nav = _nav_admin()
        contexto.update(
            papel="admin", nav=nav, area_nome="Administração",
            nav_mobile=[("admin_painel", "Geral", nav[0][2], "chart"), ("admin_estab", "Cantinas", nav[1][2], "store"),
                        ("admin_usuarios", "Usuários", nav[2][2], "user")],
        )
    elif usuario.eh_funcionario:
        estab = getattr(request, "estabelecimento", None) or estabelecimento_do_funcionario(request)
        pode_aprovar = bool(usuario.vinculo_com(estab) and usuario.vinculo_com(estab).funcao == "gerente")
        nav_mobile = [
            ("pedidos", "Pedidos", reverse("painel:pedidos"), "list"),
            ("itens", "Itens", reverse("painel:itens"), "box"),
            ("token", "Token", reverse("painel:token"), "dollar"),
            ("dashboard", "Painel", reverse("painel:dashboard"), "chart"),
        ]
        if pode_aprovar:
            nav_mobile.append(("funcionarios", "Equipe", reverse("painel:funcionarios"), "user"))
        nav_mobile.append(("vincular_cantina", "Adicionar cantina", reverse("usuarios:vincular_cantina"), "store"))
        contexto.update(
            papel="funcionario", nav=_nav_funcionario(), area_nome="Operador de cantina",
            nav_mobile=nav_mobile,
            estab_funcionario=estab,
            estabs_vinculados=list(usuario.estabelecimentos_vinculados()),
            pode_aprovar_funcionarios=pode_aprovar,
        )
    else:
        from pedidos.carrinho import Carrinho

        cantina = usuario.estabelecimento_atual if usuario.estabelecimento_atual_id else None
        if cantina is not None and not cantina.ativo:
            cantina = None
        contexto.update(
            papel="cliente", nav=_nav_cliente(), area_nome="Área do cliente",
            cantina_atual=cantina,
            carrinho_qtd=len(Carrinho(request, cantina)) if cantina else 0,
            tickets_ativos=usuario.pedidos.filter(
                status__in=["confirmado", "em_preparacao", "pronto"]
            ).count(),
        )
    return contexto
