"""Vale sem integracao: o pedido nasce, a cobranca vai por WhatsApp."""
from decimal import Decimal

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.stores.api.views.storefront_views import build_store_payment_config
from apps.stores.models import Store, StoreOrder
from apps.stores.services.checkout_service import CheckoutService

User = get_user_model()


class ValePorLinkTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username='o-vpl', password='x', email='o-vpl@real.com')
        self.store = Store.objects.create(
            name='Loja Link', slug='loja-link', owner=self.owner, status='active',
            whatsapp_number='5563999998888',
            metadata={'voucher_manual_brands': ['volus']},
        )

    def _order(self, total='25.00'):
        return StoreOrder.objects.create(
            store=self.store, customer_name='Cliente',
            customer_phone='5563988887777', customer_email='c@real.com',
            subtotal=Decimal(total), total=Decimal(total))

    def test_o_pedido_NASCE_pendente(self):
        """Sem pedido, a loja nao teria o que cobrar e o cliente repetiria
        tudo no WhatsApp — que e onde a venda se perde."""
        order = self._order()
        r = CheckoutService.create_payment(order, 'voucher_link', {'brand': 'volus'})
        self.assertTrue(r['success'], r)
        order.refresh_from_db()
        self.assertEqual(order.payment_status, StoreOrder.PaymentStatus.PENDING)
        self.assertEqual(order.payment_method, 'voucher_link')

    def test_a_bandeira_fica_gravada_no_pedido(self):
        """A loja precisa saber QUAL vale para mandar o link certo."""
        order = self._order()
        CheckoutService.create_payment(order, 'voucher_link', {'brand': 'volus'})
        order.refresh_from_db()
        self.assertEqual(order.metadata.get('vale_por_link'), 'volus')

    def test_a_mensagem_diz_o_que_fazer_e_qual_vale(self):
        """Ele precisa saber TRÊS coisas: que chega um QR, por onde chega, e
        de qual vale. Sem isso fica esperando sem saber o quê."""
        order = self._order()
        r = CheckoutService.create_payment(order, 'voucher_link', {'brand': 'volus'})
        self.assertIn('QR Code', r['message'])
        self.assertIn('WhatsApp', r['message'])
        self.assertIn('Vólus', r['message'])

    def test_o_pedido_NAO_e_marcado_como_pago(self):
        """Ninguem pagou ainda. Marcar pago aqui inventaria receita."""
        order = self._order()
        CheckoutService.create_payment(order, 'voucher_link', {'brand': 'volus'})
        order.refresh_from_db()
        self.assertNotEqual(order.payment_status, StoreOrder.PaymentStatus.PAID)

    def test_bandeira_que_a_loja_nao_marcou_e_recusada(self):
        order = self._order()
        r = CheckoutService.create_payment(order, 'voucher_link', {'brand': 'xpto'})
        self.assertFalse(r['success'])
        order.refresh_from_db()
        self.assertNotEqual(order.payment_method, 'voucher_link')

    def test_loja_sem_whatsapp_nao_oferece_a_opcao(self):
        """Oferecer 'fale no WhatsApp' sem WhatsApp e mandar o cliente para
        lugar nenhum — o mesmo erro do frete gratis que nunca era aplicado."""
        self.store.whatsapp_number = ''
        self.store.save(update_fields=['whatsapp_number'])
        cfg = build_store_payment_config(self.store)
        self.assertNotIn('voucher_link', cfg['enabled_methods'])

    def test_loja_sem_bandeira_marcada_nao_oferece(self):
        self.store.metadata = {}
        self.store.save(update_fields=['metadata'])
        cfg = build_store_payment_config(self.store)
        self.assertNotIn('voucher_link', cfg['enabled_methods'])

    def test_com_tudo_configurado_a_opcao_aparece_com_a_bandeira(self):
        cfg = build_store_payment_config(self.store)
        self.assertIn('voucher_link', cfg['enabled_methods'])
        bloco = cfg['vale_por_link']
        self.assertEqual([b['value'] for b in bloco['brands']], ['volus'])
        self.assertEqual(bloco['brands'][0]['label'], 'Vólus')
        self.assertEqual(bloco['whatsapp'], '5563999998888')

    def test_bandeira_inventada_na_config_da_loja_e_ignorada(self):
        """Lixo no metadata nao pode virar opcao na tela do cliente."""
        self.store.metadata = {'voucher_manual_brands': ['volus', 'xpto']}
        self.store.save(update_fields=['metadata'])
        cfg = build_store_payment_config(self.store)
        self.assertEqual([b['value'] for b in cfg['vale_por_link']['brands']], ['volus'])
