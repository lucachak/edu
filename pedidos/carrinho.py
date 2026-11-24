"""Carrinho guardado na sessão do servidor.

O carrinho só guarda ``produto_id -> quantidade``. Preço, nome e
disponibilidade são sempre lidos do banco, então o cliente não consegue
manipular valores pelo navegador.
"""

from dataclasses import dataclass
from decimal import Decimal

from django.conf import settings
from django.utils import timezone

from produtos.models import Produto

CHAVE_SESSAO = "fastline_carrinho"


@dataclass
class LinhaCarrinho:
    produto: Produto
    quantidade: int
    disponivel: int

    @property
    def subtotal(self):
        return self.produto.preco * self.quantidade

    @property
    def excede_disponivel(self):
        return self.quantidade > self.disponivel


class Carrinho:
    def __init__(self, request, estabelecimento):
        self.request = request
        self.estabelecimento = estabelecimento
        dados = request.session.get(CHAVE_SESSAO) or {}
        if dados.get("estab") != getattr(estabelecimento, "pk", None):
            dados = {"estab": getattr(estabelecimento, "pk", None), "itens": {}}
        self.dados = dados

    # ---- persistência ---------------------------------------------------
    def _salvar(self):
        self.request.session[CHAVE_SESSAO] = self.dados
        self.request.session.modified = True

    @property
    def itens(self):
        return self.dados.setdefault("itens", {})

    def quantidade_de(self, produto_id):
        return int(self.itens.get(str(produto_id), 0))

    # ---- operações ------------------------------------------------------
    def definir(self, produto, quantidade):
        maximo = settings.FASTLINE_MAX_ITENS_POR_PRODUTO
        quantidade = max(0, min(int(quantidade), maximo))
        if quantidade == 0:
            self.itens.pop(str(produto.pk), None)
        else:
            self.itens[str(produto.pk)] = quantidade
        self._salvar()

    def adicionar(self, produto, quantidade=1):
        self.definir(produto, self.quantidade_de(produto.pk) + int(quantidade))

    def remover(self, produto_id):
        self.itens.pop(str(produto_id), None)
        self._salvar()

    def limpar(self):
        self.dados["itens"] = {}
        self._salvar()

    # ---- leitura --------------------------------------------------------
    def linhas(self):
        ids = [int(pid) for pid in self.itens.keys()]
        if not ids:
            return []
        produtos = Produto.objects.filter(
            pk__in=ids, estabelecimento=self.estabelecimento, ativo=True,
        ).select_related("categoria")
        linhas = []
        validos = set()
        for produto in produtos:
            validos.add(str(produto.pk))
            linhas.append(LinhaCarrinho(
                produto=produto,
                quantidade=self.quantidade_de(produto.pk),
                disponivel=999999,
            ))
        # Remove produtos que deixaram de existir ou de estar ativos.
        if set(self.itens.keys()) - validos:
            self.dados["itens"] = {k: v for k, v in self.itens.items() if k in validos}
            self._salvar()
        linhas.sort(key=lambda linha: linha.produto.nome)
        return linhas

    def resumo(self):
        linhas = self.linhas()
        subtotal = sum((linha.subtotal for linha in linhas), Decimal("0.00"))
        taxa = Decimal(settings.FASTLINE_TAXA_SERVICO) if linhas else Decimal("0.00")
        return {
            "linhas": linhas,
            "quantidade_total": sum(linha.quantidade for linha in linhas),
            "subtotal": subtotal,
            "taxa_servico": taxa,
            "total": subtotal + taxa,
            "tem_problema": any(linha.excede_disponivel for linha in linhas),
        }

    def __len__(self):
        return sum(int(q) for q in self.itens.values())
