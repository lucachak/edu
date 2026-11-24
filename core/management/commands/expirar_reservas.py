from django.core.management.base import BaseCommand

from pedidos.services import expirar_reservas_vencidas


class Command(BaseCommand):
    help = "Cancela pedidos não pagos com reserva vencida e devolve as unidades à disponibilidade online."

    def handle(self, *args, **options):
        total = expirar_reservas_vencidas()
        if options["verbosity"]:
            self.stdout.write(self.style.SUCCESS(f"{total} reserva(s) expirada(s) liberada(s)."))
