from datetime import date

from django import forms
from django.contrib.auth import authenticate, password_validation
from django.contrib.auth.forms import PasswordChangeForm
from django.utils import timezone

from estabelecimentos.models import estabelecimento as Estabelecimento

from .models import Permissao, Usuario, Vinculo


def somente_digitos(valor):
    return "".join(c for c in (valor or "") if c.isdigit())


def cpf_valido(cpf):
    cpf = somente_digitos(cpf)
    if len(cpf) != 11 or cpf == cpf[0] * 11:
        return False
    for tamanho in (9, 10):
        soma = sum(int(cpf[i]) * (tamanho + 1 - i) for i in range(tamanho))
        digito = (soma * 10) % 11 % 10
        if digito != int(cpf[tamanho]):
            return False
    return True


class LoginForm(forms.Form):
    AREAS = [("cliente", "Cliente"), ("cantina", "Cantina")]

    area = forms.ChoiceField(choices=AREAS, initial="cliente", widget=forms.RadioSelect)
    email = forms.EmailField(
        label="E-mail",
        widget=forms.EmailInput(attrs={"placeholder": "fulano@gmail.com", "autocomplete": "email", "autofocus": True}),
    )
    senha = forms.CharField(
        label="Senha", strip=False,
        widget=forms.PasswordInput(attrs={"placeholder": "••••••••", "autocomplete": "current-password"}),
    )
    email_responsavel = forms.EmailField(
        label="E-mail do responsável", required=False,
        widget=forms.EmailInput(attrs={"placeholder": "E-mail do responsável", "autocomplete": "email"}),
    )

    erro_credenciais = "E-mail ou senha inválidos."

    def __init__(self, request=None, *args, **kwargs):
        self.request = request
        self.usuario = None
        self.precisa_autorizacao = False
        self.email_responsavel = ""
        super().__init__(*args, **kwargs)

    def clean(self):
        dados = super().clean()
        email = (dados.get("email") or "").lower()
        senha = dados.get("senha")
        if email and senha:
            self.usuario = authenticate(self.request, username=email, password=senha)
            if self.usuario is None:
                raise forms.ValidationError(self.erro_credenciais)
            area = dados.get("area")
            if self.usuario.data_nascimento:
                hoje = timezone.localdate()
                nascimento = self.usuario.data_nascimento
                idade = hoje.year - nascimento.year - ((hoje.month, hoje.day) < (nascimento.month, nascimento.day))
                if idade < 17 and not self.usuario.responsavel_confirmado:
                    responsavel = (dados.get("email_responsavel") or "").strip().lower()
                    if not responsavel:
                        self.add_error("email_responsavel", "Informe o e-mail do responsável para autorizar o acesso.")
                    elif responsavel == email:
                        self.add_error("email_responsavel", "Use um e-mail diferente do e-mail do cliente.")
                    else:
                        self.precisa_autorizacao = True
                        self.email_responsavel = responsavel
            if area == "cantina" and self.usuario.eh_cliente:
                raise forms.ValidationError(
                    "Esta conta é de cliente. Selecione “Cliente” para entrar."
                )
            if area == "cantina" and self.usuario.eh_funcionario and not self.usuario.estabelecimentos_vinculados().exists():
                raise forms.ValidationError("Seu cadastro de funcionário ainda aguarda aprovação da cantina.")
            if area == "cliente" and not self.usuario.eh_cliente:
                raise forms.ValidationError(
                    "Esta conta é de funcionário ou administrador. Selecione “Cantina” para entrar."
                )
        return dados


class CadastroForm(forms.ModelForm):
    data_nascimento = forms.DateField(
        label="Data de nascimento",
        widget=forms.DateInput(attrs={"type": "date", "autocomplete": "bday"}),
    )
    email_responsavel = forms.EmailField(
        label="E-mail do responsável", required=False,
        widget=forms.EmailInput(attrs={"placeholder": "responsavel@email.com", "autocomplete": "email"}),
    )
    senha = forms.CharField(
        label="Senha", strip=False,
        widget=forms.PasswordInput(attrs={"placeholder": "Mínimo de 8 caracteres", "autocomplete": "new-password"}),
        help_text=password_validation.password_validators_help_text_html(),
    )
    confirmar_senha = forms.CharField(
        label="Confirmar senha", strip=False,
        widget=forms.PasswordInput(attrs={"placeholder": "Repita a senha", "autocomplete": "new-password"}),
    )

    class Meta:
        model = Usuario
        fields = ["nome", "email", "data_nascimento", "email_responsavel"]
        labels = {"nome": "Nome completo", "email": "E-mail", "data_nascimento": "Data de nascimento"}
        widgets = {
            "nome": forms.TextInput(attrs={"placeholder": "Ronaldo Caires da Rosa", "autocomplete": "name"}),
            "email": forms.EmailInput(attrs={"placeholder": "fulano@gmail.com", "autocomplete": "email"}),
            "data_nascimento": forms.DateInput(attrs={"type": "date", "autocomplete": "bday"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        if Usuario.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("Já existe uma conta com este e-mail.")
        return email

    def clean(self):
        dados = super().clean()
        nascimento = dados.get("data_nascimento")
        responsavel = (dados.get("email_responsavel") or "").strip().lower()
        if nascimento:
            hoje = timezone.localdate()
            idade = hoje.year - nascimento.year - ((hoje.month, hoje.day) < (nascimento.month, nascimento.day))
            if nascimento > hoje:
                self.add_error("data_nascimento", "A data de nascimento não pode estar no futuro.")
            elif idade < 17:
                if not responsavel:
                    self.add_error("email_responsavel", "Informe o e-mail do responsável para autorizar o cadastro.")
                elif responsavel == (dados.get("email") or "").lower():
                    self.add_error("email_responsavel", "Use um e-mail diferente do e-mail do cliente.")
        senha, confirmar = dados.get("senha"), dados.get("confirmar_senha")
        if senha and confirmar and senha != confirmar:
            self.add_error("confirmar_senha", "As senhas não conferem.")
        if senha:
            usuario_temp = Usuario(nome=dados.get("nome", ""), email=dados.get("email", ""))
            try:
                password_validation.validate_password(senha, usuario_temp)
            except forms.ValidationError as erro:
                self.add_error("senha", erro)
        return dados

    def save(self, commit=True):
        usuario = super().save(commit=False)
        usuario.permissao = Permissao.CLIENTE
        usuario.email_responsavel = (self.cleaned_data.get("email_responsavel") or "").strip().lower()
        nascimento = self.cleaned_data["data_nascimento"]
        hoje = timezone.localdate()
        idade = hoje.year - nascimento.year - ((hoje.month, hoje.day) < (nascimento.month, nascimento.day))
        usuario.responsavel_confirmado = idade >= 17
        usuario.is_active = idade >= 17
        usuario.set_password(self.cleaned_data["senha"])
        if commit:
            usuario.save()
        return usuario


def campo_cpf(**kwargs):
    """Aceita CPF com máscara (14 caracteres); o clean_cpf guarda só os 11 dígitos."""
    return forms.CharField(
        label="CPF", required=False, max_length=14,
        widget=forms.TextInput(attrs={"inputmode": "numeric", "placeholder": "000.000.000-00"}), **kwargs,
    )


def campo_telefone():
    return forms.CharField(
        label="Celular", required=False, max_length=20,
        widget=forms.TextInput(attrs={"inputmode": "tel", "placeholder": "(11) 91234-5678"}),
    )


class PerfilForm(forms.ModelForm):
    class Meta:
        model = Usuario
        fields = ["nome", "email"]
        labels = {"nome": "Nome de exibição", "email": "E-mail de login"}

    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        if Usuario.objects.filter(email__iexact=email).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("Já existe uma conta com este e-mail.")
        return email

    def clean_cpf(self):
        cpf = somente_digitos(self.cleaned_data.get("cpf"))
        if cpf and not cpf_valido(cpf):
            raise forms.ValidationError("CPF inválido.")
        return cpf

    def clean_telefone(self):
        tel = somente_digitos(self.cleaned_data.get("telefone"))
        if tel and len(tel) not in (10, 11):
            raise forms.ValidationError("Informe DDD + número (10 ou 11 dígitos).")
        return tel


class CpfForm(forms.Form):
    cpf = forms.CharField(
        label="CPF do pagador", max_length=14,
        widget=forms.TextInput(attrs={"inputmode": "numeric", "placeholder": "000.000.000-00"}),
    )

    def clean_cpf(self):
        cpf = somente_digitos(self.cleaned_data["cpf"])
        if not cpf_valido(cpf):
            raise forms.ValidationError("CPF inválido.")
        return cpf


class SenhaForm(PasswordChangeForm):
    pass


# ---------------------------------------------------------------------------
# Painel do administrador
# ---------------------------------------------------------------------------
class UsuarioAdminForm(forms.ModelForm):
    cpf = campo_cpf()
    telefone = campo_telefone()
    nova_senha = forms.CharField(
        label="Nova senha", required=False, strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
        help_text="Deixe em branco para manter a senha atual.",
    )

    class Meta:
        model = Usuario
        fields = ["nome", "email", "permissao", "is_active", "cpf", "telefone"]
        labels = {"permissao": "Permissão", "is_active": "Conta ativa"}

    def __init__(self, *args, editor=None, **kwargs):
        self.editor = editor
        super().__init__(*args, **kwargs)
        if not self.instance.pk:
            self.fields["nova_senha"].required = True
            self.fields["nova_senha"].label = "Senha"
            self.fields["nova_senha"].help_text = ""

    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        if Usuario.objects.filter(email__iexact=email).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("Já existe uma conta com este e-mail.")
        return email

    clean_cpf = PerfilForm.clean_cpf
    clean_telefone = PerfilForm.clean_telefone

    def clean(self):
        dados = super().clean()
        if self.editor and self.instance.pk == self.editor.pk:
            if dados.get("permissao") != Permissao.ADMIN or not dados.get("is_active"):
                raise forms.ValidationError("Você não pode remover o seu próprio acesso de administrador.")
        senha = dados.get("nova_senha")
        if senha:
            try:
                password_validation.validate_password(senha, self.instance)
            except forms.ValidationError as erro:
                self.add_error("nova_senha", erro)
        return dados

    def save(self, commit=True):
        usuario = super().save(commit=False)
        if self.cleaned_data.get("nova_senha"):
            usuario.set_password(self.cleaned_data["nova_senha"])
        if commit:
            usuario.save()
        return usuario


class VinculoForm(forms.ModelForm):
    class Meta:
        model = Vinculo
        fields = ["estabelecimento", "funcao", "pode_gerenciar_produtos", "ativo"]
        labels = {"funcao": "Função", "pode_gerenciar_produtos": "Pode gerenciar produtos"}
        widgets = {"funcao": forms.TextInput(attrs={"placeholder": "Atendente, Gerente..."})}

    def __init__(self, *args, usuario=None, **kwargs):
        self.usuario = usuario
        super().__init__(*args, **kwargs)
        self.fields["estabelecimento"].queryset = Estabelecimento.objects.order_by("nome")
        self.fields["estabelecimento"].empty_label = "Selecione"

    def clean_estabelecimento(self):
        estab = self.cleaned_data["estabelecimento"]
        if self.usuario and Vinculo.objects.filter(usuario=self.usuario, estabelecimento=estab).exclude(
            pk=self.instance.pk
        ).exists():
            raise forms.ValidationError("Este usuário já tem vínculo com este estabelecimento.")
        return estab


class CadastroFuncionarioForm(forms.Form):
    nome = forms.CharField(max_length=100, label="Nome")
    email = forms.EmailField(label="E-mail")
    data_nascimento = forms.DateField(label="Data de nascimento", widget=forms.DateInput(attrs={"type": "date"}))
    email_responsavel = forms.EmailField(label="E-mail do responsável", required=False)
    senha = forms.CharField(label="Senha", min_length=8, widget=forms.PasswordInput)
    confirmar_senha = forms.CharField(label="Confirmar senha", widget=forms.PasswordInput)
    codigo_convite = forms.CharField(label="Código da cantina", max_length=40)

    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        if Usuario.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("Já existe uma conta com este e-mail.")
        return email

    def clean_codigo_convite(self):
        codigo = self.cleaned_data["codigo_convite"].strip()
        if not Estabelecimento.objects.filter(codigo_convite__iexact=codigo, ativo=True).exists():
            raise forms.ValidationError("Código de cantina inválido.")
        return codigo

    def clean(self):
        dados = super().clean()
        nascimento = dados.get("data_nascimento")
        responsavel = (dados.get("email_responsavel") or "").strip().lower()
        if nascimento:
            hoje = timezone.localdate()
            idade = hoje.year - nascimento.year - ((hoje.month, hoje.day) < (nascimento.month, nascimento.day))
            if nascimento > hoje:
                self.add_error("data_nascimento", "A data de nascimento não pode estar no futuro.")
            elif idade < 17:
                if not responsavel:
                    self.add_error("email_responsavel", "Informe o e-mail do responsável.")
                elif responsavel == (dados.get("email") or "").lower():
                    self.add_error("email_responsavel", "Use um e-mail diferente do e-mail do funcionário.")
        senha, confirmar = dados.get("senha"), dados.get("confirmar_senha")
        if senha and confirmar and senha != confirmar:
            self.add_error("confirmar_senha", "As senhas não conferem.")
        if senha:
            usuario_temp = Usuario(nome=dados.get("nome", ""), email=dados.get("email", ""))
            try:
                password_validation.validate_password(senha, usuario_temp)
            except forms.ValidationError as erro:
                self.add_error("senha", erro)
        return dados

    def save(self):
        cantina = Estabelecimento.objects.get(codigo_convite__iexact=self.cleaned_data["codigo_convite"], ativo=True)
        nascimento = self.cleaned_data["data_nascimento"]
        hoje = timezone.localdate()
        idade = hoje.year - nascimento.year - ((hoje.month, hoje.day) < (nascimento.month, nascimento.day))
        usuario = Usuario(
            nome=self.cleaned_data["nome"],
            email=self.cleaned_data["email"],
            permissao=Permissao.FUNCIONARIO,
            data_nascimento=nascimento,
            email_responsavel=(self.cleaned_data.get("email_responsavel") or "").strip().lower(),
            responsavel_confirmado=idade >= 17,
            is_active=idade >= 17,
        )
        usuario.set_password(self.cleaned_data["senha"])
        usuario.save()
        Vinculo.objects.create(usuario=usuario, estabelecimento=cantina, funcao="funcionario", ativo=False, pode_gerenciar_produtos=False)
        return usuario, cantina


class VincularOutraCantinaForm(forms.Form):
    codigo_convite = forms.CharField(
        label="Código da nova cantina", max_length=40,
        widget=forms.TextInput(attrs={"placeholder": "Digite o código de convite", "data-maiusculo": ""}),
    )

    def clean_codigo_convite(self):
        codigo = self.cleaned_data["codigo_convite"].strip()
        cantina = Estabelecimento.objects.filter(codigo_convite__iexact=codigo, ativo=True).first()
        if not cantina:
            raise forms.ValidationError("Não encontramos uma cantina ativa com esse código.")
        if Vinculo.objects.filter(usuario=self.usuario, estabelecimento=cantina).exists():
            raise forms.ValidationError("Sua conta já possui um vínculo com essa cantina.")
        self.cantina = cantina
        return codigo

    def __init__(self, *args, usuario=None, **kwargs):
        self.usuario = usuario
        super().__init__(*args, **kwargs)

    def save(self):
        return Vinculo.objects.create(
            usuario=self.usuario,
            estabelecimento=self.cantina,
            funcao="funcionario",
            ativo=False,
            pode_gerenciar_produtos=False,
        )
