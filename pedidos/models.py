import secrets
import uuid
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone

LETRAS_TOKEN = "ABCDEFGHJKLMNPQRSTUVWXYZ"  # sem I e O, para não confundir com 1 e 0
DIGITOS = "0123456789"


def gerar_token_retirada():
    """Gera um código como ``SR0459-16`` usando o gerador criptográfico.

    2 letras + 6 dígitos ≈ 576 milhões de combinações. Além disso o token só
    é aceito por funcionários do estabelecimento do pedido e uma única vez.
    """
    letras = "".join(secrets.choice(LETRAS_TOKEN) for _ in range(2))
    numeros = "".join(secrets.choice(DIGITOS) for _ in range(6))
    return f"{letras}{numeros[:4]}-{numeros[4:]}"


def normalizar_token(texto):
    texto = (texto or "").strip().upper().replace(" ", "").replace("_", "")
    if len(texto) == 8 and "-" not in texto:
        texto = f"{texto[:6]}-{texto[6:]}"
    return texto


class StatusPedido(models.TextChoices):
    AGUARDANDO_PAGAMENTO = "aguardando_pagamento", "Aguardando pagamento"
    CONFIRMADO = "confirmado", "Confirmado"
    EM_PREPARACAO = "em_preparacao", "Em preparação"
    PRONTO = "pronto", "Pronto para retirada"
    RETIRADO = "retirado", "Retirado"
    CANCELADO = "cancelado", "Cancelado"


# Transições que um funcionário pode fazer manualmente no painel.
TRANSICOES_FUNCIONARIO = {
    StatusPedido.CONFIRMADO: [StatusPedido.EM_PREPARACAO, StatusPedido.PRONTO, StatusPedido.CANCELADO],
    StatusPedido.EM_PREPARACAO: [StatusPedido.PRONTO, StatusPedido.CANCELADO],
    StatusPedido.PRONTO: [StatusPedido.EM_PREPARACAO, StatusPedido.CANCELADO],
    StatusPedido.AGUARDANDO_PAGAMENTO: [StatusPedido.CANCELADO],
}

STATUS_ATIVOS = [
    StatusPedido.CONFIRMADO, StatusPedido.EM_PREPARACAO, StatusPedido.PRONTO,
]
STATUS_COM_TOKEN = STATUS_ATIVOS + [StatusPedido.RETIRADO]
STATUS_VENDA = STATUS_ATIVOS + [StatusPedido.RETIRADO]


class pedido(models.Model):
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="pedidos")
    estabelecimento = models.ForeignKey(
        "estabelecimentos.estabelecimento", on_delete=models.PROTECT, related_name="pedidos",
    )
    codigo = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    taxa_servico = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    valor_total = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    data_pedido = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True, null=True)
    status = models.CharField(
        max_length=30, choices=StatusPedido.choices, default=StatusPedido.AGUARDANDO_PAGAMENTO,
    )
    metodo_pagamento = models.CharField(max_length=20, blank=True)
    data_disponibilidade = models.DateField(
        "dia da retirada", default=timezone.localdate,
        help_text="Dia da cota de disponibilidade usada pelo pedido.",
    )
    reserva_expira_em = models.DateTimeField(null=True, blank=True)
    token_retirada = models.CharField(max_length=12, unique=True, null=True, blank=True, editable=False)
    token_expira_em = models.DateTimeField(null=True, blank=True)
    confirmado_em = models.DateTimeField(null=True, blank=True)
    cancelado_em = models.DateTimeField(null=True, blank=True)
    motivo_cancelamento = models.CharField(max_length=200, blank=True)
    reserva_liberada = models.BooleanField(default=False, editable=False)

    class Meta:
        ordering = ["-data_pedido"]
        verbose_name = "pedido"
        verbose_name_plural = "pedidos"
        indexes = [
            models.Index(fields=["estabelecimento", "status"]),
            models.Index(fields=["status", "reserva_expira_em"]),
        ]

    def __str__(self):
        return f"Pedido {self.id} - {self.usuario}"

    @property
    def numero(self):
        return f"#{self.id}"

    @property
    def aguardando_pagamento(self):
        return self.status == StatusPedido.AGUARDANDO_PAGAMENTO

    @property
    def reserva_expirada(self):
        return (
            self.aguardando_pagamento
            and self.reserva_expira_em is not None
            and self.reserva_expira_em <= timezone.now()
        )

    @property
    def token_expirado(self):
        return bool(self.token_expira_em and self.token_expira_em <= timezone.now())

    @property
    def pode_ser_retirado(self):
        return self.status in STATUS_ATIVOS and bool(self.token_retirada) and not self.token_expirado

    def transicoes_permitidas(self):
        return TRANSICOES_FUNCIONARIO.get(self.status, [])

    def recalcular_totais(self):
        subtotal = sum((item.subtotal for item in self.itens.all()), Decimal("0.00"))
        self.subtotal = subtotal
        self.valor_total = subtotal + (self.taxa_servico or Decimal("0.00"))


class item_pedido(models.Model):
    pedido = models.ForeignKey(pedido, on_delete=models.CASCADE, related_name="itens")
    produto = models.ForeignKey("produtos.Produto", on_delete=models.PROTECT, related_name="itens_pedido")
    nome_produto = models.CharField(max_length=100, blank=True)
    quantidade = models.PositiveIntegerField()
    preco_unitario = models.DecimalField(max_digits=10, decimal_places=2)
    disponibilidade = models.ForeignKey(
        "produtos.DisponibilidadeOnline", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="itens_pedido",
    )

    class Meta:
        verbose_name = "item do pedido"
        verbose_name_plural = "itens do pedido"

    def __str__(self):
        return f"{self.quantidade}x {self.nome_produto or self.produto} - Pedido {self.pedido_id}"

    @property
    def subtotal(self):
        return self.quantidade * self.preco_unitario


class StatusPagamento(models.TextChoices):
    PENDENTE = "pendente", "Pendente"
    PAGO = "pago", "Pago"
    RECUSADO = "recusado", "Recusado"
    CANCELADO = "cancelado", "Cancelado"
    ERRO = "erro", "Erro na integração"


class pagamento(models.Model):
    METODOS = [
        ("pix", "PIX"),
        ("cartao", "Cartão"),
        ("cartao_credito", "Cartão de crédito"),
        ("cartao_debito", "Cartão de débito"),
        ("dinheiro", "Dinheiro"),
        ("balcao", "Pagamento no balcão"),
        ("simulado", "Pagamento simulado (demonstração)"),
    ]
    PROVEDORES = [("pagseguro", "PagSeguro"), ("balcao", "Balcão (confirmado por funcionário)"), ("simulador", "Simulador (demonstração)")]

    pedido = models.OneToOneField(pedido, on_delete=models.CASCADE, related_name="pagamento")
    metodo_pagamento = models.CharField(max_length=20, choices=METODOS)
    valor_pago = models.DecimalField("valor", max_digits=10, decimal_places=2)
    data_pagamento = models.DateTimeField("criado em", auto_now_add=True)

    provedor = models.CharField(max_length=20, choices=PROVEDORES, default="pagseguro")
    status = models.CharField(max_length=20, choices=StatusPagamento.choices, default=StatusPagamento.PENDENTE)
    ambiente = models.CharField(max_length=20, blank=True)
    referencia = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    pagseguro_order_id = models.CharField(max_length=64, blank=True, db_index=True)
    pagseguro_checkout_id = models.CharField(max_length=64, blank=True, db_index=True)
    pagseguro_charge_id = models.CharField(max_length=64, blank=True)
    status_provedor = models.CharField(max_length=30, blank=True)
    pix_copia_e_cola = models.TextField(blank=True)
    pix_qrcode_url = models.URLField(max_length=500, blank=True)
    link_pagamento = models.URLField(max_length=500, blank=True)
    mensagem = models.CharField(max_length=255, blank=True)
    resposta_bruta = models.JSONField(default=dict, blank=True)
    pago_em = models.DateTimeField(null=True, blank=True)
    confirmado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )
    atualizado_em = models.DateTimeField(auto_now=True, null=True)

    class Meta:
        verbose_name = "pagamento"
        verbose_name_plural = "pagamentos"

    def __str__(self):
        return f"Pagamento - Pedido {self.pedido_id}"


class EventoPagamento(models.Model):
    """Registro de cada notificação/consulta recebida do PagSeguro (auditoria)."""

    pagamento = models.ForeignKey(pagamento, on_delete=models.CASCADE, related_name="eventos", null=True, blank=True)
    origem = models.CharField(max_length=30)  # webhook, consulta, criacao
    autenticado = models.BooleanField(default=False)
    status_provedor = models.CharField(max_length=30, blank=True)
    payload = models.JSONField(default=dict, blank=True)
    recebido_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-recebido_em"]
        verbose_name = "evento de pagamento"
        verbose_name_plural = "eventos de pagamento"


class retirada(models.Model):
    pedido = models.OneToOneField(pedido, on_delete=models.CASCADE, related_name="retirada")
    data_retirada = models.DateTimeField(auto_now_add=True)
    local_retirada = models.CharField(max_length=200)
    confirmado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="retiradas_confirmadas",
    )
    token_utilizado = models.CharField(max_length=12, blank=True)

    def __str__(self):
        return f"Retirada - Pedido {self.pedido.id}"
