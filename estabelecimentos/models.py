import re
import secrets
import uuid

from django.db import models

# Sem caracteres que se confundem ao digitar (0/O, 1/I/L).
ALFABETO_CODIGO = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
TAMANHO_CODIGO = 6
FORMATO_CODIGO = re.compile(r"^[A-Z0-9]{4,20}$")


def normalizar_codigo(valor):
    """Deixa o código em maiúsculas e sem espaços, hífens ou pontos."""
    return re.sub(r"[^A-Za-z0-9]", "", valor or "").upper()


def gerar_codigo_acesso(modelo=None):
    """Gera um código curto e único que o cliente digita para se conectar."""
    modelo = modelo or estabelecimento
    while True:
        codigo = "".join(secrets.choice(ALFABETO_CODIGO) for _ in range(TAMANHO_CODIGO))
        if not modelo.objects.filter(codigo_acesso__iexact=codigo).exists():
            return codigo


class EstabelecimentoQuerySet(models.QuerySet):
    def ativos(self):
        return self.filter(ativo=True)


class estabelecimento(models.Model):
    """Cantina / refeitório que usa a plataforma.

    O nome da classe em minúsculo foi mantido do projeto original para não
    renomear a tabela nem as migrações existentes.
    """

    nome = models.CharField(max_length=100)
    endereco = models.CharField("endereço", max_length=200)
    unique_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    codigo_convite = models.CharField("código de convite para funcionários", max_length=40, unique=True, blank=True, null=True)
    codigo_acesso = models.CharField(
        "código de acesso para clientes", max_length=20, unique=True, blank=True, null=True,
        help_text="Código que o cliente digita para encontrar a cantina. Ex.: SENAI01, CANT42.",
    )

    descricao = models.TextField("descrição", blank=True)
    local = models.CharField(
        "local de retirada", max_length=100, blank=True,
        help_text="Ex.: Térreo, 5º andar, Bloco B.",
    )
    identificacao = models.CharField(
        "identificação (CNPJ ou código interno)", max_length=30, blank=True,
    )
    email = models.EmailField("e-mail de contato", blank=True)
    telefone = models.CharField(max_length=20, blank=True)
    horario_abertura = models.TimeField("abre às", null=True, blank=True)
    horario_fechamento = models.TimeField("fecha às", null=True, blank=True)
    ativo = models.BooleanField(
        default=True, help_text="Estabelecimentos desativados não aparecem para clientes.",
    )
    criado_em = models.DateTimeField(auto_now_add=True, null=True)
    atualizado_em = models.DateTimeField(auto_now=True, null=True)

    objects = EstabelecimentoQuerySet.as_manager()

    class Meta:
        ordering = ["nome"]
        verbose_name = "estabelecimento"
        verbose_name_plural = "estabelecimentos"

    def __str__(self):
        return self.nome

    def save(self, *args, **kwargs):
        self.codigo_acesso = normalizar_codigo(self.codigo_acesso) or gerar_codigo_acesso()
        update_fields = kwargs.get("update_fields")
        if update_fields is not None and "codigo_acesso" not in update_fields:
            kwargs["update_fields"] = list(update_fields) + ["codigo_acesso"]
        super().save(*args, **kwargs)

    def regenerar_codigo_acesso(self):
        self.codigo_acesso = gerar_codigo_acesso()
        self.save(update_fields=["codigo_acesso"])
        return self.codigo_acesso

    @property
    def local_completo(self):
        partes = [p for p in (self.local, self.endereco) if p]
        return " - ".join(partes)


# Alias com a convenção de nomes do Python, para uso no código novo.
Estabelecimento = estabelecimento
