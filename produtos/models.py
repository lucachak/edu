from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import F
from django.utils import timezone


def validar_tamanho_imagem(arquivo):
    limite = getattr(settings, "FASTLINE_IMAGEM_MAX_BYTES", 3 * 1024 * 1024)
    if arquivo and arquivo.size > limite:
        raise ValidationError(f"A imagem deve ter no máximo {limite // (1024 * 1024)} MB.")


class Categoria(models.Model):
    estabelecimento = models.ForeignKey(
        "estabelecimentos.estabelecimento", on_delete=models.CASCADE, related_name="categorias",
    )
    nome = models.CharField(max_length=60)
    ordem = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["ordem", "nome"]
        constraints = [
            models.UniqueConstraint(fields=["estabelecimento", "nome"], name="categoria_unica_por_estabelecimento"),
        ]

    def __str__(self):
        return self.nome


class ProdutoQuerySet(models.QuerySet):
    def ativos(self):
        return self.filter(ativo=True)


class Produto(models.Model):
    nome = models.CharField(max_length=100)
    descricao = models.TextField("descrição", blank=True)
    preco = models.DecimalField("preço", max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    categoria = models.ForeignKey(
        Categoria, on_delete=models.PROTECT, related_name="produtos", null=True, blank=True,
    )
    estabelecimento = models.ForeignKey(
        "estabelecimentos.estabelecimento", on_delete=models.CASCADE, related_name="produtos",
    )
    imagem = models.ImageField(upload_to="produtos/%Y/%m/", blank=True, validators=[validar_tamanho_imagem])
    ativo = models.BooleanField(
        default=True, help_text="Produtos inativos não aparecem no cardápio.",
    )
    criado_em = models.DateTimeField(auto_now_add=True, null=True)
    atualizado_em = models.DateTimeField(auto_now=True, null=True)

    objects = ProdutoQuerySet.as_manager()

    class Meta:
        ordering = ["categoria__ordem", "nome"]

    def __str__(self):
        return self.nome

    def clean(self):
        if self.categoria_id and self.estabelecimento_id and self.categoria.estabelecimento_id != self.estabelecimento_id:
            raise ValidationError({"categoria": "A categoria pertence a outro estabelecimento."})

    def disponibilidade_do_dia(self, data=None):
        data = data or timezone.localdate()
        return self.disponibilidades.filter(data=data).first()


class DisponibilidadeOnline(models.Model):
    """Quantidade de um produto oferecida para pedidos antecipados num dia.

    Não é o estoque físico da cantina: é a cota que a cantina libera para
    pedidos online. ``quantidade_comprometida`` soma as unidades reservadas
    por pedidos aguardando pagamento e as já vendidas. A cota só é alterada
    com UPDATE condicional (ver ``reservar``), o que impede vender a mesma
    última unidade para dois clientes ao mesmo tempo.
    """

    produto = models.ForeignKey(Produto, on_delete=models.CASCADE, related_name="disponibilidades")
    data = models.DateField(default=timezone.localdate)
    quantidade_ofertada = models.PositiveIntegerField(default=0)
    quantidade_comprometida = models.PositiveIntegerField(default=0, editable=False)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "disponibilidade online"
        verbose_name_plural = "disponibilidades online"
        constraints = [
            models.UniqueConstraint(fields=["produto", "data"], name="disponibilidade_unica_por_dia"),
            models.CheckConstraint(
                condition=models.Q(quantidade_comprometida__lte=F("quantidade_ofertada")),
                name="comprometida_nao_excede_ofertada",
            ),
        ]

    def __str__(self):
        return f"{self.produto} em {self.data:%d/%m/%Y}: {self.quantidade_disponivel} disponíveis"

    @property
    def quantidade_disponivel(self):
        return max(self.quantidade_ofertada - self.quantidade_comprometida, 0)

    @property
    def esgotado(self):
        return self.quantidade_disponivel <= 0

    @classmethod
    def reservar(cls, pk, quantidade):
        """Compromete ``quantidade`` unidades de forma atômica.

        Retorna True se conseguiu. Deve ser chamado dentro de uma transação.
        """
        if quantidade <= 0:
            return False
        atualizados = cls.objects.filter(
            pk=pk, quantidade_comprometida__lte=F("quantidade_ofertada") - quantidade,
        ).update(quantidade_comprometida=F("quantidade_comprometida") + quantidade)
        return atualizados == 1

    @classmethod
    def liberar(cls, pk, quantidade):
        """Devolve unidades à cota (cancelamento ou expiração)."""
        if quantidade <= 0:
            return
        cls.objects.filter(pk=pk, quantidade_comprometida__gte=quantidade).update(
            quantidade_comprometida=F("quantidade_comprometida") - quantidade,
        )

    @classmethod
    def abrir_dia(cls, estabelecimento=None, quantidade=None, data=None):
        """Cria a cota do dia para produtos ativos que ainda não têm.

        Copia a quantidade ofertada do último dia registrado de cada produto
        (ou usa ``quantidade``). Produtos sem histórico começam com 0, ou
        seja, indisponíveis até o funcionário liberar. Retorna quantos criou.
        Chamado ao abrir o cardápio/painel e pelo comando ``abrir_dia``.
        """
        data = data or timezone.localdate()
        produtos = Produto.objects.filter(ativo=True, estabelecimento__ativo=True).exclude(disponibilidades__data=data)
        if estabelecimento is not None:
            produtos = produtos.filter(estabelecimento=estabelecimento)
        criados = 0
        for produto in produtos:
            qtd = quantidade
            if qtd is None:
                anterior = produto.disponibilidades.filter(data__lt=data).order_by("-data").first()
                if anterior is None:
                    continue
                qtd = anterior.quantidade_ofertada
            _, novo = cls.objects.get_or_create(produto=produto, data=data, defaults={"quantidade_ofertada": qtd})
            criados += novo
        return criados

    def definir_ofertada(self, nova_quantidade):
        """Ajusta a cota sem permitir ficar abaixo do que já foi comprometido."""
        if nova_quantidade < self.quantidade_comprometida:
            raise ValidationError(
                f"Já existem {self.quantidade_comprometida} unidades reservadas ou vendidas; "
                "a quantidade ofertada não pode ser menor que isso."
            )
        self.quantidade_ofertada = nova_quantidade


class CardapioEspecial(models.Model):
    """Almoço do dia ou cardápio especial publicado pela cantina."""

    estabelecimento = models.ForeignKey(
        "estabelecimentos.estabelecimento", on_delete=models.CASCADE, related_name="cardapios_especiais",
    )
    titulo = models.CharField("título", max_length=100)
    descricao = models.TextField("descrição", blank=True)
    data = models.DateField(default=timezone.localdate)
    imagem = models.ImageField(upload_to="cardapios/%Y/%m/", blank=True, validators=[validar_tamanho_imagem])
    preco = models.DecimalField("preço (R$)", max_digits=8, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(0)])
    produtos = models.ManyToManyField(Produto, blank=True, related_name="cardapios_especiais")
    ativo = models.BooleanField(default=True)

    class Meta:
        ordering = ["-data", "titulo"]
        verbose_name = "cardápio especial"
        verbose_name_plural = "cardápios especiais"

    def __str__(self):
        return f"{self.titulo} ({self.data:%d/%m})"


class movimentacao(models.Model):
    """Histórico de alterações em produtos (modelo original, ampliado)."""

    TIPOS = [
        ("adicionado", "Adicionado"),
        ("excluido", "Excluído"),
        ("editado", "Editado"),
        ("disponibilidade", "Disponibilidade alterada"),
    ]

    produto = models.ForeignKey(Produto, on_delete=models.CASCADE)
    funcionario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
    )
    data_movimentacao = models.DateTimeField(auto_now_add=True)
    tipo_movimentacao = models.CharField(max_length=20, choices=TIPOS)
    detalhe = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["-data_movimentacao"]
        verbose_name = "movimentação"
        verbose_name_plural = "movimentações"

    def __str__(self):
        return f"{self.tipo_movimentacao} - {self.produto.nome}"
