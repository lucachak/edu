import uuid

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.db import models
from django.utils import timezone


class Permissao(models.TextChoices):
    CLIENTE = "cliente", "Cliente"
    FUNCIONARIO = "funcionario", "Funcionário"
    ADMIN = "admin", "Administrador"


class UsuarioManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email, password, **extra):
        if not email:
            raise ValueError("O e-mail é obrigatório.")
        email = self.normalize_email(email).lower()
        usuario = self.model(email=email, **extra)
        usuario.set_password(password)
        usuario.save(using=self._db)
        return usuario

    def create_user(self, email, password=None, **extra):
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra)

    def create_superuser(self, email, password=None, **extra):
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        extra.setdefault("permissao", Permissao.ADMIN)
        extra.setdefault("nome", "Administrador")
        return self._create_user(email, password, **extra)


class Usuario(AbstractBaseUser, PermissionsMixin):
    """Usuário do FastLine.

    Mantém os campos do modelo original (nome, email, codigo_conta,
    data_nascimento, permissao). A senha em texto puro (campo ``senha``) foi
    substituída pelo campo ``password`` do Django, que guarda apenas o hash.
    """

    nome = models.CharField(max_length=100)
    email = models.EmailField(unique=True)
    codigo_conta = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    data_nascimento = models.DateField(null=True, blank=True)
    email_responsavel = models.EmailField("e-mail do responsável", blank=True)
    responsavel_confirmado = models.BooleanField(default=False)
    permissao = models.CharField(max_length=20, choices=Permissao.choices, default=Permissao.CLIENTE)
    cpf = models.CharField(
        "CPF", max_length=11, blank=True,
        help_text="Somente números. Exigido pelo PagSeguro para gerar cobranças.",
    )
    telefone = models.CharField(max_length=20, blank=True)

    is_active = models.BooleanField("ativo", default=True)
    is_staff = models.BooleanField(
        "acesso ao admin do Django", default=False,
        help_text="Permite entrar no /admin/ técnico do Django.",
    )
    date_joined = models.DateTimeField("cadastrado em", default=timezone.now)

    estabelecimento_atual = models.ForeignKey(
        "estabelecimentos.estabelecimento", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="+",
        help_text="Cantina selecionada pelo cliente para comprar.",
    )
    favoritos = models.ManyToManyField(
        "estabelecimentos.estabelecimento", blank=True, related_name="favoritado_por",
    )

    objects = UsuarioManager()

    USERNAME_FIELD = "email"
    EMAIL_FIELD = "email"
    REQUIRED_FIELDS = ["nome"]

    class Meta:
        verbose_name = "usuário"
        verbose_name_plural = "usuários"

    def __str__(self):
        return self.nome or self.email

    def get_full_name(self):
        return self.nome

    def get_short_name(self):
        return (self.nome or self.email).split(" ")[0]

    # ---- papéis -------------------------------------------------------
    @property
    def eh_admin(self):
        return self.is_active and (self.is_superuser or self.permissao == Permissao.ADMIN)

    @property
    def eh_funcionario(self):
        return self.is_active and self.permissao == Permissao.FUNCIONARIO

    @property
    def eh_cliente(self):
        return self.is_active and self.permissao == Permissao.CLIENTE

    def estabelecimentos_vinculados(self):
        from estabelecimentos.models import estabelecimento

        return estabelecimento.objects.filter(
            vinculos__usuario=self, vinculos__ativo=True, ativo=True,
        ).distinct()

    def vinculo_com(self, estab):
        if estab is None:
            return None
        return self.vinculos.filter(estabelecimento=estab, ativo=True).first()


class Vinculo(models.Model):
    """Liga um funcionário a um estabelecimento (modelo original mantido)."""

    usuario = models.ForeignKey(Usuario, on_delete=models.CASCADE, related_name="vinculos")
    estabelecimento = models.ForeignKey(
        "estabelecimentos.Estabelecimento", on_delete=models.CASCADE, related_name="vinculos",
    )
    funcao = models.CharField(max_length=100)
    ativo = models.BooleanField(default=True)
    pode_gerenciar_produtos = models.BooleanField(
        default=True, help_text="Permite cadastrar/editar produtos e disponibilidade.",
    )
    criado_em = models.DateTimeField(auto_now_add=True, null=True)

    class Meta:
        verbose_name = "vínculo"
        verbose_name_plural = "vínculos"
        constraints = [
            models.UniqueConstraint(fields=["usuario", "estabelecimento"], name="vinculo_unico_por_estabelecimento"),
        ]

    def __str__(self):
        return f"{self.usuario.nome} - {self.estabelecimento.nome}"
