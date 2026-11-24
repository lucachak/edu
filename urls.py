from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

admin.site.site_header = "FastLine - administração técnica"
admin.site.site_title = "FastLine"

urlpatterns = [
    path("", include("core.urls")),
    path("conta/", include("usuarios.urls")),
    path("cantinas/", include("estabelecimentos.urls")),
    path("cardapio/", include("produtos.urls")),
    path("", include("pedidos.urls")),
    path("painel/", include("painel.urls")),
    path("administracao/", include("administracao.urls")),
    path("admin/", admin.site.urls),
]

handler403 = "core.views.erro_403"
handler404 = "core.views.erro_404"
handler500 = "core.views.erro_500"

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
