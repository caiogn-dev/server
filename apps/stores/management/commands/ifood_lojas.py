"""Lista as lojas que aprovaram o app no iFood (GET /merchants) e a qual loja
do Cardapidex cada uma está ligada. Uso interno — não vai para o painel do
lojista porque mostra lojas de todos os clientes."""
from django.core.management.base import BaseCommand

from apps.stores.models.ifood import StoreIfoodIntegration
from apps.stores.services import loja_no_ifood


class Command(BaseCommand):
    help = 'Lojas do iFood que aprovaram o app Cardapidex'

    def handle(self, *args, **opts):
        ligadas = dict(StoreIfoodIntegration.objects.exclude(merchant_id='')
                       .values_list('merchant_id', 'store__slug'))
        for loja in loja_no_ifood.lojas_do_app():
            self.stdout.write(f"{loja['id']}  {loja['nome']} ({loja['razao_social']})  →  "
                              f"{ligadas.get(loja['id'], 'não ligada')}")
