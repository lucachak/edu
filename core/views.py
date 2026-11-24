from django.shortcuts import redirect

from .permissions import destino_inicial


def inicio(request):
    if not request.user.is_authenticated:
        return redirect("usuarios:login")
    return redirect(destino_inicial(request.user))


def _erro(request, status, titulo, mensagem):
    from django.shortcuts import render

    return render(request, "erro.html", {"status": status, "titulo": titulo, "mensagem": mensagem}, status=status)


def erro_403(request, exception=None):
    mensagem = str(exception) if exception and str(exception) else "Você não tem permissão para acessar esta página."
    return _erro(request, 403, "Acesso negado", mensagem)


def erro_404(request, exception=None):
    return _erro(request, 404, "Página não encontrada", "O endereço acessado não existe ou foi removido.")


def erro_500(request):
    return _erro(request, 500, "Algo deu errado", "Tivemos um problema inesperado. Tente novamente em instantes.")
