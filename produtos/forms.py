from django import forms

from .models import CardapioEspecial, Categoria, Produto


class ProdutoForm(forms.ModelForm):
    nova_categoria = forms.CharField(
        label="Ou crie uma categoria", required=False, max_length=60,
        widget=forms.TextInput(attrs={"placeholder": "Ex.: Salgado"}),
    )
    class Meta:
        model = Produto
        fields = ["nome", "descricao", "preco", "categoria", "imagem", "ativo"]
        labels = {"preco": "Preço (R$)", "descricao": "Descrição", "ativo": "Ativo no cardápio"}
        widgets = {
            "nome": forms.TextInput(attrs={"placeholder": "Ex.: Coxinha de Frango"}),
            "descricao": forms.Textarea(attrs={"rows": 2}),
            "preco": forms.NumberInput(attrs={"step": "0.01", "min": "0", "placeholder": "5,00"}),
            "imagem": forms.ClearableFileInput(attrs={"accept": "image/*"}),
        }

    def __init__(self, *args, estabelecimento=None, **kwargs):
        self.estabelecimento = estabelecimento
        super().__init__(*args, **kwargs)
        self.fields["categoria"].queryset = Categoria.objects.filter(estabelecimento=estabelecimento)
        self.fields["categoria"].required = False
        self.fields["categoria"].empty_label = "Selecione"

    def clean_preco(self):
        preco = self.cleaned_data["preco"]
        if preco is None or preco <= 0:
            raise forms.ValidationError("Informe um preço maior que zero.")
        return preco

    def clean(self):
        dados = super().clean()
        nome_cat = (dados.get("nova_categoria") or "").strip()
        if not dados.get("categoria") and not nome_cat:
            self.add_error("categoria", "Escolha ou crie uma categoria.")
        return dados

    def save(self, commit=True):
        produto = super().save(commit=False)
        produto.estabelecimento = self.estabelecimento
        nome_cat = (self.cleaned_data.get("nova_categoria") or "").strip()
        if nome_cat:
            produto.categoria, _ = Categoria.objects.get_or_create(
                estabelecimento=self.estabelecimento, nome__iexact=nome_cat,
                defaults={"nome": nome_cat},
            )
        if commit:
            produto.save()
        return produto


class CardapioEspecialForm(forms.ModelForm):
    class Meta:
        model = CardapioEspecial
        fields = ["titulo", "descricao", "data", "imagem", "preco", "produtos", "ativo"]
        labels = {"titulo": "Título", "descricao": "Descrição", "imagem": "Foto do almoço", "preco": "Preço (R$)"}
        widgets = {
            "titulo": forms.TextInput(attrs={"placeholder": "Almoço do dia"}),
            "descricao": forms.Textarea(attrs={"rows": 2, "placeholder": "Arroz, feijão, frango grelhado e salada"}),
            "data": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "produtos": forms.CheckboxSelectMultiple,
            "imagem": forms.ClearableFileInput(attrs={"accept": "image/*"}),
            "preco": forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
        }

    def __init__(self, *args, estabelecimento=None, **kwargs):
        self.estabelecimento = estabelecimento
        super().__init__(*args, **kwargs)
        self.fields["produtos"].queryset = Produto.objects.filter(estabelecimento=estabelecimento, ativo=True)
        self.fields["produtos"].required = False

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.estabelecimento = self.estabelecimento
        if commit:
            obj.save()
            self.save_m2m()
        return obj
