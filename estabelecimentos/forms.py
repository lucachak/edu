from django import forms

from .models import FORMATO_CODIGO, estabelecimento, normalizar_codigo


class EstabelecimentoForm(forms.ModelForm):
    """Formulário original ampliado com os novos campos."""

    class Meta:
        model = estabelecimento
        fields = [
            "nome", "endereco", "local", "descricao", "identificacao", "codigo_acesso", "codigo_convite", "email", "telefone",
            "horario_abertura", "horario_fechamento", "ativo",
        ]

        labels = {
            "nome": "Nome do Estabelecimento",
            "endereco": "Endereço do Estabelecimento",
            "local": "Local de retirada",
            "descricao": "Descrição",
            "identificacao": "CNPJ ou código interno",
            "codigo_acesso": "Código da cantina (para clientes)",
            "codigo_convite": "Código de convite para funcionários",
            "email": "E-mail de contato",
            "telefone": "Telefone",
            "horario_abertura": "Abre às",
            "horario_fechamento": "Fecha às",
            "ativo": "Ativo (visível para clientes)",
        }

        widgets = {
            "nome": forms.TextInput(attrs={"placeholder": "Digite o nome do estabelecimento"}),
            "endereco": forms.TextInput(attrs={"placeholder": "Digite o endereço do estabelecimento"}),
            "local": forms.TextInput(attrs={"placeholder": "Térreo, 5º andar..."}),
            "codigo_acesso": forms.TextInput(attrs={
                "placeholder": "Deixe em branco para gerar automaticamente",
                "autocomplete": "off", "style": "text-transform:uppercase",
            }),
            "codigo_convite": forms.TextInput(attrs={"placeholder": "Ex.: CANTINA-UNIDADE-01"}),
            "descricao": forms.Textarea(attrs={"rows": 3}),
            "horario_abertura": forms.TimeInput(attrs={"type": "time"}, format="%H:%M"),
            "horario_fechamento": forms.TimeInput(attrs={"type": "time"}, format="%H:%M"),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["codigo_acesso"].help_text = (
            "O cliente digita este código para se conectar à cantina. "
            "Use de 4 a 20 letras ou números. Em branco, o sistema gera um."
        )

    def clean_codigo_acesso(self):
        codigo = normalizar_codigo(self.cleaned_data.get("codigo_acesso"))
        if not codigo:
            return None  # o modelo gera um código ao salvar
        if not FORMATO_CODIGO.match(codigo):
            raise forms.ValidationError("Use de 4 a 20 letras ou números, sem espaços.")
        repetido = estabelecimento.objects.filter(codigo_acesso__iexact=codigo)
        if self.instance.pk:
            repetido = repetido.exclude(pk=self.instance.pk)
        if repetido.exists():
            raise forms.ValidationError("Este código já é usado por outra cantina.")
        return codigo

    def clean(self):
        dados = super().clean()
        abre, fecha = dados.get("horario_abertura"), dados.get("horario_fechamento")
        if abre and fecha and fecha <= abre:
            self.add_error("horario_fechamento", "O horário de fechamento deve ser depois da abertura.")
        return dados
