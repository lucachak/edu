from decimal import Decimal

from django import template
from django.utils.html import format_html
from django.utils.safestring import mark_safe

register = template.Library()

# Ícones em traço (estilo do protótipo), desenhados em SVG inline.
ICONES = {
    "book": '<path d="M4 5a2 2 0 0 1 2-2h13v16H6a2 2 0 0 0-2 2V5z"/><path d="M4 19a2 2 0 0 1 2-2h13"/>',
    "ticket": '<path d="M3 8V6a1 1 0 0 1 1-1h16a1 1 0 0 1 1 1v2a2 2 0 0 0 0 4v2a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1v-2a2 2 0 0 0 0-4z" transform="translate(0 2)"/><path d="M10 7v10" stroke-dasharray="2 2"/>',
    "store": '<path d="M4 10v10h16V10"/><path d="M3 10l2-6h14l2 6"/><path d="M3 10a3 3 0 0 0 6 0 3 3 0 0 0 6 0 3 3 0 0 0 6 0"/><path d="M10 20v-5h4v5"/>',
    "user": '<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>',
    "list": '<path d="M9 6h11M9 12h11M9 18h11"/><circle cx="4.5" cy="6" r="1"/><circle cx="4.5" cy="12" r="1"/><circle cx="4.5" cy="18" r="1"/>',
    "box": '<path d="M21 8l-9-5-9 5 9 5 9-5z"/><path d="M3 8v8l9 5 9-5V8"/><path d="M12 13v8"/>',
    "file": '<path d="M14 3H6a1 1 0 0 0-1 1v16a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V8z"/><path d="M14 3v5h5M8 13h8M8 17h8M8 9h3"/>',
    "chart": '<path d="M5 20V10M12 20V4M19 20v-7"/>',
    "dollar": '<path d="M12 2v20"/><path d="M17 6.5c0-1.9-2.2-3-5-3s-5 1.3-5 3.3c0 4.7 10 2.6 10 7.4 0 2-2.2 3.3-5 3.3s-5-1.2-5-3"/>',
    "cart": '<circle cx="9" cy="20" r="1.5"/><circle cx="18" cy="20" r="1.5"/><path d="M2 3h3l2.4 11.2a1 1 0 0 0 1 .8h9.7a1 1 0 0 0 1-.8L21 7H6"/>',
    "search": '<circle cx="11" cy="11" r="7"/><path d="M20 20l-4-4"/>',
    "check": '<path d="M5 12l5 5L20 7"/>',
    "x": '<path d="M6 6l12 12M18 6L6 18"/>',
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "minus": '<path d="M5 12h14"/>',
    "star": '<path d="M12 3l2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.4 2.9 1-6.1L3.2 9.5l6.1-.9z"/>',
    "pin": '<path d="M12 21s-7-6.2-7-11.5A7 7 0 0 1 19 9.5C19 14.8 12 21 12 21z"/><circle cx="12" cy="9.5" r="2.5"/>',
    "mail": '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M3 7l9 6 9-6"/>',
    "arrow-right": '<path d="M5 12h14M13 6l6 6-6 6"/>',
    "arrow-left": '<path d="M19 12H5M11 6l-6 6 6 6"/>',
    "chevron-right": '<path d="M9 6l6 6-6 6"/>',
    "chevron-down": '<path d="M6 9l6 6 6-6"/>',
    "clock": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    "trending": '<path d="M3 17l6-6 4 4 8-8"/><path d="M15 7h6v6"/>',
    "alert": '<path d="M12 3l10 18H2z"/><path d="M12 10v5M12 18h.01"/>',
    "info": '<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7.5h.01"/>',
    "edit": '<path d="M4 20h4L19 9l-4-4L4 16z"/><path d="M14 6l4 4"/>',
    "trash": '<path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3"/>',
    "logout": '<path d="M15 4h4a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1h-4M10 17l5-5-5-5M15 12H3"/>',
    "refresh": '<path d="M20 11a8 8 0 0 0-14.9-3.9L4 8M4 4v4h4"/><path d="M4 13a8 8 0 0 0 14.9 3.9L20 16M20 20v-4h-4"/>',
}


@register.simple_tag
def icone(nome, classe=""):
    caminho = ICONES.get(nome, ICONES["info"])
    return format_html(
        '<svg class="icone {}" viewBox="0 0 24 24" aria-hidden="true" focusable="false">{}</svg>',
        classe, mark_safe(caminho),
    )


@register.filter
def reais(valor):
    """Formata 1234.5 como R$ 1.234,50."""
    try:
        valor = Decimal(valor or 0).quantize(Decimal("0.01"))
    except Exception:
        return valor
    inteiro, _, centavos = f"{valor:.2f}".partition(".")
    negativo = inteiro.startswith("-")
    inteiro = inteiro.lstrip("-")
    grupos = []
    while inteiro:
        grupos.insert(0, inteiro[-3:])
        inteiro = inteiro[:-3]
    return f"{'-' if negativo else ''}R$ {'.'.join(grupos) or '0'},{centavos}"


@register.filter
def iniciais(texto):
    partes = [p for p in str(texto or "").split() if p]
    return "".join(p[0] for p in partes[:2]).upper() or "?"


@register.filter
def imagem_produto(produto):
    """URL da imagem enviada ou None."""
    try:
        return produto.imagem.url if produto.imagem else None
    except ValueError:
        return None


@register.simple_tag(takes_context=True)
def resumo_carrinho(context):
    """Resumo do carrinho da sessão (para a gaveta presente em todas as páginas)."""
    from pedidos.carrinho import Carrinho

    request = context.get("request")
    cantina = context.get("cantina_atual")
    if request is None or cantina is None:
        return None
    return Carrinho(request, cantina).resumo()
