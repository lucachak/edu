"""Regras de negócio de pedidos: reserva, confirmação, cancelamento e retirada.

Toda mudança de status passa por aqui, sempre dentro de transações e com o
pedido bloqueado (``select_for_update``) para evitar condições de corrida.
"""

import logging
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from produtos.models import DisponibilidadeOnline, Produto

from .models import (
    STATUS_ATIVOS,
    StatusPagamento,
    StatusPedido,
    gerar_token_retirada,
    item_pedido,
    normalizar_token,
    pedido as Pedido,
    retirada as Retirada,
)

logger = logging.getLogger("fastline.pedidos")


class PedidoErro(Exception):
    """Erro de regra de negócio com mensagem pronta para o usuário."""


class ProdutoIndisponivel(PedidoErro):
    def __init__(self, produto, disponivel):
        self.produto = produto
        self.disponivel = disponivel
        if disponivel <= 0:
            msg = f"“{produto.nome}” esgotou para pedidos online."
        else:
            msg = f"Restam apenas {disponivel} unidade(s) de “{produto.nome}”."
        super().__init__(msg)


# ---------------------------------------------------------------------------
# Criação do pedido com reserva da disponibilidade
# ---------------------------------------------------------------------------
def criar_pedido(usuario, estabelecimento, itens, metodo_pagamento=""):
    """Cria o pedido reservando a disponibilidade online de cada item.

    ``itens`` é um dicionário ``{produto_id: quantidade}`` vindo do carrinho
    da sessão. Preços são lidos do banco. Se qualquer item não puder ser
    reservado, nada é gravado (rollback da transação inteira).
    """
    if not estabelecimento or not estabelecimento.ativo:
        raise PedidoErro("Esta cantina não está recebendo pedidos no momento.")
    itens = {int(pid): int(qtd) for pid, qtd in itens.items() if int(qtd) > 0}
    if not itens:
        raise PedidoErro("Seu carrinho está vazio.")

    expirar_reservas_vencidas()
    hoje = timezone.localdate()

    with transaction.atomic():
        produtos = {
            p.pk: p
            for p in Produto.objects.select_for_update().filter(
                pk__in=itens.keys(), estabelecimento=estabelecimento, ativo=True,
            )
        }
        if len(produtos) != len(itens):
            raise PedidoErro("Algum produto do carrinho não está mais disponível. Revise o carrinho.")


        taxa = Decimal(settings.FASTLINE_TAXA_SERVICO)
        novo = Pedido.objects.create(
            usuario=usuario,
            estabelecimento=estabelecimento,
            status=StatusPedido.AGUARDANDO_PAGAMENTO,
            metodo_pagamento=metodo_pagamento,
            data_disponibilidade=hoje,
            taxa_servico=taxa,
            reserva_expira_em=timezone.now() + timedelta(minutes=settings.FASTLINE_RESERVA_MINUTOS),
        )
        subtotal = Decimal("0.00")
        for produto_id in sorted(itens):  # ordem fixa evita deadlocks no PostgreSQL
            produto = produtos[produto_id]
            quantidade = itens[produto_id]
            disp = None  # sem cota de salgados: só o funcionário controla o produto ativo
            item_pedido.objects.create(
                pedido=novo,
                produto=produto,
                nome_produto=produto.nome[:100],
                quantidade=quantidade,
                preco_unitario=produto.preco,
                disponibilidade=disp,
            )
            subtotal += produto.preco * quantidade

        novo.subtotal = subtotal
        novo.valor_total = subtotal + taxa
        novo.save(update_fields=["subtotal", "valor_total"])
    logger.info("Pedido %s criado (reserva até %s)", novo.pk, novo.reserva_expira_em)
    return novo


# ---------------------------------------------------------------------------
# Liberação de reservas
# ---------------------------------------------------------------------------
def _liberar_itens(p):
    if p.reserva_liberada:
        return
    for item in p.itens.all():
        if item.disponibilidade_id:
            DisponibilidadeOnline.liberar(item.disponibilidade_id, item.quantidade)
    p.reserva_liberada = True


def _rereservar_itens(p):
    """Tenta reservar de novo as unidades de um pedido cuja reserva expirou."""
    reservados = []
    for item in p.itens.select_related("disponibilidade").order_by("produto_id"):
        # Pedidos novos não usam cotas; pedidos antigos ainda podem ter uma
        # disponibilidade vinculada e precisam respeitar a reserva legada.
        if not item.disponibilidade_id:
            continue
        if DisponibilidadeOnline.reservar(item.disponibilidade_id, item.quantidade):
            reservados.append(item)
            continue
        for desfazer in reservados:
            DisponibilidadeOnline.liberar(desfazer.disponibilidade_id, desfazer.quantidade)
        return False
    p.reserva_liberada = False
    return True


def cancelar_pedido(p, motivo="", por=None):
    """Cancela o pedido e devolve as unidades à disponibilidade online."""
    with transaction.atomic():
        p = Pedido.objects.select_for_update().get(pk=p.pk)
        if p.status in (StatusPedido.RETIRADO, StatusPedido.CANCELADO):
            raise PedidoErro("Este pedido não pode mais ser cancelado.")
        _liberar_itens(p)
        p.status = StatusPedido.CANCELADO
        p.cancelado_em = timezone.now()
        p.motivo_cancelamento = (motivo or "Cancelado")[:200]
        p.save()
        pag = getattr(p, "pagamento", None) if hasattr(p, "pagamento") else None
        if pag and pag.status == StatusPagamento.PENDENTE:
            pag.status = StatusPagamento.CANCELADO
            pag.save(update_fields=["status", "atualizado_em"])
    logger.info("Pedido %s cancelado: %s", p.pk, motivo)
    return p


def expirar_reservas_vencidas(agora=None):
    """Cancela pedidos não pagos cuja reserva venceu. Retorna a quantidade.

    Chamado de forma preguiçosa (ao abrir o cardápio e ao criar pedidos) e
    pelo comando ``python manage.py expirar_reservas``.
    """
    agora = agora or timezone.now()
    vencidos = list(
        Pedido.objects.filter(
            status=StatusPedido.AGUARDANDO_PAGAMENTO, reserva_expira_em__lte=agora,
        ).values_list("pk", flat=True)
    )
    total = 0
    for pk in vencidos:
        with transaction.atomic():
            p = Pedido.objects.select_for_update().filter(pk=pk).first()
            if not p or p.status != StatusPedido.AGUARDANDO_PAGAMENTO or not p.reserva_expirada:
                continue
            _liberar_itens(p)
            p.status = StatusPedido.CANCELADO
            p.cancelado_em = agora
            p.motivo_cancelamento = (
                f"Reserva expirada: pagamento não confirmado em {settings.FASTLINE_RESERVA_MINUTOS} minutos."
            )
            p.save()
            if hasattr(p, "pagamento") and p.pagamento.status == StatusPagamento.PENDENTE:
                p.pagamento.status = StatusPagamento.CANCELADO
                p.pagamento.save(update_fields=["status", "atualizado_em"])
            total += 1
    if total:
        logger.info("%s reserva(s) expirada(s) liberada(s)", total)
    return total


# ---------------------------------------------------------------------------
# Confirmação do pagamento e geração do token
# ---------------------------------------------------------------------------
def _atribuir_token(p):
    for _ in range(10):
        candidato = gerar_token_retirada()
        if not Pedido.objects.filter(token_retirada=candidato).exists():
            p.token_retirada = candidato
            p.token_expira_em = timezone.now() + timedelta(hours=4)
            return
    raise PedidoErro("Não foi possível gerar um token único. Tente novamente.")


def confirmar_pagamento(p, por=None):
    """Marca o pedido como pago/confirmado e gera o token de retirada.

    Só deve ser chamado depois que o pagamento foi validado no backend
    (consulta à API do PagSeguro ou confirmação de um funcionário no balcão).
    Retorna o pedido atualizado. Idempotente: chamar duas vezes não gera
    outro token.
    """
    for tentativa in range(3):
        try:
            return _confirmar_pagamento(p, por)
        except IntegrityError:  # colisão rara de token único: tenta de novo
            if tentativa == 2:
                raise
    return p


def _marcar_pagamento_pago(p, por, mensagem=""):
    if not hasattr(p, "pagamento"):
        return
    pag = p.pagamento
    pag.status = StatusPagamento.PAGO
    pag.pago_em = pag.pago_em or timezone.now()
    if por is not None:
        pag.confirmado_por = por
    if mensagem:
        pag.mensagem = mensagem[:255]
    pag.save()


def _confirmar_pagamento(p, por):
    erro = None
    with transaction.atomic():
        p = Pedido.objects.select_for_update().get(pk=p.pk)
        if p.status in STATUS_ATIVOS or p.status == StatusPedido.RETIRADO:
            return p  # já confirmado (idempotente)
        reativar = p.status == StatusPedido.CANCELADO
        if reativar and not _rereservar_itens(p):
            # Pagamento chegou depois da expiração e o produto esgotou.
            erro = (
                "Pagamento aprovado após a expiração da reserva e o produto esgotou. "
                "Estorno necessário."
            )
            p.motivo_cancelamento = erro[:200]
            p.save(update_fields=["motivo_cancelamento", "atualizado_em"])
            _marcar_pagamento_pago(p, por, mensagem=erro)
            logger.warning("Pedido %s pago após expirar e sem disponibilidade", p.pk)
        else:
            if reativar:
                p.cancelado_em = None
                p.motivo_cancelamento = ""
            p.status = StatusPedido.CONFIRMADO
            p.confirmado_em = timezone.now()
            p.reserva_expira_em = None
            _atribuir_token(p)
            p.save()
            _marcar_pagamento_pago(p, por)
    if erro:
        raise PedidoErro(erro)
    logger.info("Pedido %s confirmado, token gerado", p.pk)
    return p


# ---------------------------------------------------------------------------
# Painel do funcionário
# ---------------------------------------------------------------------------
def atualizar_status(p, novo_status, por):
    if novo_status == StatusPedido.CANCELADO:
        return cancelar_pedido(p, motivo=f"Cancelado por {por.get_short_name()} (funcionário)", por=por)
    with transaction.atomic():
        p = Pedido.objects.select_for_update().get(pk=p.pk)
        if novo_status not in p.transicoes_permitidas():
            raise PedidoErro(
                f"Não é possível mudar de “{p.get_status_display()}” para "
                f"“{StatusPedido(novo_status).label}”."
            )
        p.status = novo_status
        p.save(update_fields=["status", "atualizado_em"])
    return p


def buscar_por_token(token, estabelecimento):
    token = normalizar_token(token)
    if not token:
        return None
    return (
        Pedido.objects.filter(token_retirada=token, estabelecimento=estabelecimento)
        .select_related("usuario", "estabelecimento")
        .prefetch_related("itens")
        .first()
    )


def confirmar_retirada(token, estabelecimento, funcionario):
    """Valida o token e registra a retirada. O token só pode ser usado uma vez."""
    token = normalizar_token(token)
    with transaction.atomic():
        p = (
            Pedido.objects.select_for_update()
            .filter(token_retirada=token, estabelecimento=estabelecimento)
            .first()
        )
        if p is None:
            raise PedidoErro("Token inválido para este estabelecimento.")
        if p.status == StatusPedido.RETIRADO:
            quando = timezone.localtime(p.retirada.data_retirada).strftime("%d/%m/%Y às %H:%M")
            raise PedidoErro(f"Este token já foi utilizado em {quando}.")
        if p.status not in STATUS_ATIVOS:
            raise PedidoErro(f"Pedido com status “{p.get_status_display()}” não pode ser retirado.")
        if p.token_expira_em and p.token_expira_em <= timezone.now():
            raise PedidoErro("Este ticket expirou. Solicite ajuda no balcão da cantina.")
        Retirada.objects.create(
            pedido=p,
            local_retirada=estabelecimento.local_completo or estabelecimento.nome,
            confirmado_por=funcionario,
            token_utilizado=token,
        )
        p.status = StatusPedido.RETIRADO
        p.save(update_fields=["status", "atualizado_em"])
    logger.info("Retirada do pedido %s confirmada por %s", p.pk, funcionario.pk)
    return p
