"""O motivo do cancelamento chega ao banco e volta para o painel.

19/09: 0 dos 37 pedidos cancelados em 30 dias tinham motivo. O campo
`cancel_reason` existia e `cancel_order` gravava quando recebia — mas o botão
da lista de pedidos cancelava sem mandar motivo, o do detalhe cancelava por
`update_status` (que não aceitava motivo) e a API do pedido nem expunha o
campo. O dono não tinha como saber por que perde venda.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.stores.models import Store, StoreOrder


class MotivoDoCancelamentoTests(APITestCase):
    def setUp(self):
        self.dono = get_user_model().objects.create_user(username='dono-motivo', password='x')
        self.loja = Store.objects.create(name='Loja Motivo', slug='loja-motivo', owner=self.dono, status='active')
        self.pedido = StoreOrder.objects.create(
            store=self.loja, customer_name='Cliente', customer_phone='63999990501',
            subtotal=Decimal('30'), total=Decimal('30'), status='confirmed',
        )
        self.client.force_authenticate(self.dono)

    def _url(self, acao):
        return f'/api/v1/stores/orders/{self.pedido.id}/{acao}/'

    def test_cancelar_pelo_status_grava_o_motivo(self):
        r = self.client.post(self._url('update_status'), {'status': 'cancelled', 'reason': 'Acabou o produto'}, format='json')

        assert r.status_code == 200, r.content
        self.pedido.refresh_from_db()
        assert self.pedido.cancel_reason == 'Acabou o produto'

    def test_a_api_do_pedido_devolve_o_motivo(self):
        self.client.post(self._url('update_status'), {'status': 'cancelled', 'reason': 'Cliente desistiu'}, format='json')

        r = self.client.get(f'/api/v1/stores/orders/{self.pedido.id}/')

        assert r.json().get('cancel_reason') == 'Cliente desistiu'

    def test_mudar_para_outro_status_nao_grava_motivo(self):
        self.client.post(self._url('update_status'), {'status': 'preparing', 'reason': 'qualquer'}, format='json')

        self.pedido.refresh_from_db()
        assert self.pedido.cancel_reason in ('', None)
