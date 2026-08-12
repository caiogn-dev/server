"""O aviso de "pedido pronto" não pode falar dos dois mundos ao mesmo tempo.

O texto padrão era: "pronto para retirada. Aguarde a chegada do entregador ou
venha buscar!" — uma frase que se contradiz e que numa entrega (pedido
CE-2608129257, Diana, 12/ago) chegou junto com "está a caminho".

O caminho do painel foi corrigido para não passar por `ready` em entrega, mas
`ready` continua sendo um estado legítimo (a cozinha terminou). Então o texto
ganha `{proximo_passo}`, preenchido conforme o pedido é retirada ou entrega, e
a loja segue livre para reescrever a frase inteira.
"""
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.automation.models import AutoMessage, CompanyProfile
from apps.stores.models import Store, StoreOrder
from apps.whatsapp.tasks.automation_tasks import notify_order_status_change

User = get_user_model()


class AvisoDeProntoPorMetodoTest(TestCase):
    def setUp(self):
        dono = User.objects.create_user(username='dono-aviso', password='x')
        self.store = Store.objects.create(
            name='Loja Aviso', slug='loja-aviso', owner=dono, status='active',
        )
        self.profile = CompanyProfile.objects.get(store=self.store)
        self.profile.order_status_notification_enabled = True
        self.profile.save(update_fields=['order_status_notification_enabled'])

    def _pedido(self, delivery_method):
        return StoreOrder.objects.create(
            store=self.store, subtotal=50, total=50,
            customer_phone='63999990000', customer_name='Diana',
            delivery_method=delivery_method, status='ready',
        )

    def _template(self, texto):
        AutoMessage.objects.update_or_create(
            company=self.profile,
            event_type=AutoMessage.EventType.ORDER_READY,
            defaults={'name': 'Pedido pronto', 'message_text': texto, 'is_active': True},
        )

    def _texto_enviado(self, order):
        """Roda a task e devolve o texto que iria para o WhatsApp."""
        from django.core.cache import cache
        cache.clear()  # a task é idempotente por (pedido, status)
        with patch('apps.whatsapp.services.message_service.MessageService.send_text_message') as envio, \
             patch('apps.whatsapp.tasks.automation_tasks._get_account_for_profile') as conta:
            conta.return_value = type('C', (), {'id': 'conta-1'})()
            notify_order_status_change(str(order.id), 'ready')
            if not envio.called:
                return None
            return envio.call_args.kwargs.get('text') or envio.call_args[1].get('text')

    def test_retirada_manda_o_cliente_vir_buscar(self):
        self._template('Pedido #{order_number} está pronto!\n\n{proximo_passo}')

        texto = self._texto_enviado(self._pedido('pickup'))

        self.assertIn('buscar', texto.lower())
        self.assertNotIn('entregador', texto.lower())

    def test_entrega_nao_manda_o_cliente_vir_buscar(self):
        """O erro que a Diana viu: "venha buscar" num pedido com entregador."""
        self._template('Pedido #{order_number} está pronto!\n\n{proximo_passo}')

        texto = self._texto_enviado(self._pedido('delivery'))

        self.assertNotIn('buscar', texto.lower())
        self.assertIn('entrega', texto.lower())

    def test_template_da_loja_sem_a_variavel_continua_intacto(self):
        """Quem já reescreveu o texto não pode ver `{proximo_passo}` aparecer."""
        self._template('Oi! Seu pedido #{order_number} ficou pronto.')

        texto = self._texto_enviado(self._pedido('delivery'))

        self.assertEqual(texto, 'Oi! Seu pedido #%s ficou pronto.' % (
            StoreOrder.objects.get(delivery_method='delivery').order_number))
        self.assertNotIn('{', texto)
