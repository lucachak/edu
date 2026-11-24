from django.core.management.base import BaseCommand
from django.utils import timezone

from produtos.models import DisponibilidadeOnline


class Command(BaseCommand):
    help = (
        "Cria a disponibilidade online de hoje para produtos ativos que ainda não têm, "
        "copiando a quantidade ofertada do último dia registrado (ou usando --quantidade). "
        "O sistema também faz isso sozinho no primeiro acesso do dia ao cardápio/painel."
    )

    def add_arguments(self, parser):
        parser.add_argument("--quantidade", type=int, default=None, help="Quantidade fixa para todos os produtos.")

    def handle(self, *args, quantidade=None, **options):
        hoje = timezone.localdate()
        criados = DisponibilidadeOnline.abrir_dia(quantidade=quantidade, data=hoje)
        if options["verbosity"]:
            self.stdout.write(self.style.SUCCESS(f"Disponibilidade de {hoje:%d/%m/%Y} criada para {criados} produto(s)."))
