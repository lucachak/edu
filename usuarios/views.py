from django.contrib import messages
from django.core import signing
from django.core.mail import send_mail
from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from core.permissions import destino_inicial

from .forms import CadastroForm, CadastroFuncionarioForm, LoginForm, PerfilForm, SenhaForm, VincularOutraCantinaForm
from .models import Usuario, Permissao


def entrar(request):
    if request.user.is_authenticated:
        return redirect(destino_inicial(request.user))
    form = LoginForm(request, data=request.POST or None, initial={"area": request.GET.get("area", "cliente")})
    if request.method == "POST" and form.is_valid():
        if form.precisa_autorizacao:
            usuario = form.usuario
            usuario.email_responsavel = form.email_responsavel
            usuario.save(update_fields=["email_responsavel"])
            token = signing.dumps(usuario.pk, salt="fastline-responsavel")
            link = request.build_absolute_uri(f"/conta/confirmar-responsavel/{token}/")
            send_mail(
                "Autorização de acesso - FastLine",
                f"Foi solicitada autorização para uma conta de menor de 17 anos no FastLine. Para autorizar, acesse: {link}. O link expira em 3 dias.",
                None, [usuario.email_responsavel], fail_silently=False,
            )
            messages.info(request, "Enviamos um link de autorização para o responsável. O acesso será liberado após a confirmação.")
            return redirect("usuarios:login")
        login(request, form.usuario)
        messages.success(request, f"Olá, {form.usuario.get_short_name()}!")
        proximo = request.POST.get("next") or request.GET.get("next")
        if proximo and url_has_allowed_host_and_scheme(proximo, {request.get_host()}, request.is_secure()):
            return redirect(proximo)
        return redirect(destino_inicial(form.usuario))
    return render(request, "usuarios/login.html", {"form": form, "next": request.GET.get("next", "")})


def cadastro(request):
    if request.user.is_authenticated:
        return redirect(destino_inicial(request.user))
    form = CadastroForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        usuario = form.save()
        if not usuario.is_active:
            token = signing.dumps(usuario.pk, salt="fastline-responsavel")
            link = request.build_absolute_uri(f"/conta/confirmar-responsavel/{token}/")
            send_mail(
                "Autorização de cadastro - FastLine",
                f"Foi solicitado um cadastro de menor de 17 anos no FastLine. Para autorizar, acesse: {link}. O link expira em 3 dias.",
                None, [usuario.email_responsavel], fail_silently=False,
            )
            messages.info(request, "Cadastro pendente. Enviamos um link de autorização para o e-mail do responsável.")
            return redirect("usuarios:login")
        login(request, usuario, backend="django.contrib.auth.backends.ModelBackend")
        messages.success(request, "Conta criada! Agora escolha a cantina onde deseja comprar.")
        return redirect("estabelecimentos:escolher")
    return render(request, "usuarios/cadastro.html", {"form": form})



def confirmar_responsavel(request, token):
    try:
        usuario_id = signing.loads(token, salt="fastline-responsavel", max_age=60 * 60 * 24 * 3)
    except signing.SignatureExpired:
        return render(request, "usuarios/confirmacao_responsavel.html", {"expirado": True})
    except signing.BadSignature:
        return render(request, "usuarios/confirmacao_responsavel.html", {"invalido": True}, status=400)
    usuario = get_object_or_404(Usuario, pk=usuario_id)
    usuario.responsavel_confirmado = True
    usuario.is_active = True
    usuario.save(update_fields=["responsavel_confirmado", "is_active"])
    return render(request, "usuarios/confirmacao_responsavel.html", {"confirmado": True})


@login_required
def vincular_cantina(request):
    if not request.user.eh_funcionario:
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied("Somente funcionários podem solicitar vínculo com outra cantina.")
    form = VincularOutraCantinaForm(request.POST or None, usuario=request.user)
    if request.method == "POST" and form.is_valid():
        vinculo = form.save()
        messages.success(request, f"Solicitação enviada para {vinculo.estabelecimento.nome}. Um gerente precisa aprovar.")
        return redirect("painel:pedidos")
    return render(request, "usuarios/vincular_cantina.html", {"form": form})


@require_POST
def sair(request):
    logout(request)
    messages.info(request, "Você saiu da sua conta.")
    return redirect("usuarios:login")


@login_required
def perfil(request):
    form = PerfilForm(request.POST or None, instance=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Dados atualizados com sucesso.")
        return redirect("usuarios:perfil")
    return render(request, "usuarios/perfil.html", {"form": form, "secao": "perfil"})


@login_required
def alterar_senha(request):
    form = SenhaForm(request.user, request.POST or None)
    if request.method == "POST" and form.is_valid():
        usuario = form.save()
        update_session_auth_hash(request, usuario)
        messages.success(request, "Senha alterada com sucesso.")
        return redirect("usuarios:perfil")
    return render(request, "usuarios/senha.html", {"form": form, "secao": "perfil"})


def cadastro_funcionario(request):
    if request.user.is_authenticated:
        return redirect(destino_inicial(request.user))
    form = CadastroFuncionarioForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        usuario, cantina = form.save()
        if not usuario.is_active:
            token = signing.dumps(usuario.pk, salt="fastline-responsavel")
            link = request.build_absolute_uri(f"/conta/confirmar-responsavel/{token}/")
            send_mail(
                "Autorização de cadastro de funcionário - FastLine",
                f"Foi solicitado um cadastro de funcionário menor de 17 anos no FastLine. Para autorizar, acesse: {link}. O link expira em 3 dias.",
                None, [usuario.email_responsavel], fail_silently=False,
            )
            messages.info(request, f"Autorização enviada ao responsável. Depois da confirmação, um gerente de {cantina.nome} ainda precisará aprovar o vínculo.")
        else:
            messages.success(request, f"Cadastro enviado para {cantina.nome}. Um gerente precisa aprovar seu acesso antes do primeiro login.")
        return redirect("usuarios:login")
    return render(request, "usuarios/cadastro_funcionario.html", {"form": form})
