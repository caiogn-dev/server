"""Quem vai buscar não recebe "Saiu para entrega".

MEDIDO (05/10): 3 das 44 retiradas da Cê Saladas em 30 dias passaram por
`out_for_delivery` — o KDS e o Kanban levam todo pedido pronto para "Saiu".
O cliente que já tinha lido "Pode vir buscar!" no aviso de pronto recebia em
seguida "🛵 Saiu para entrega", e fica esperando um motoboy que não existe.

Regra: retirada (e digital) em `out_for_delivery` não gera aviso. O pedido
continua podendo passar pelo status — só o WhatsApp fica quieto.
"""
from unittest import mock

import pytest
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.stores.models import Store, StoreOrder

User = get_user_model()


@pytest.fixture(autouse=True)
def _janela_aberta():
    with mock.patch('apps.automation.mensageiro.janela.aberta', return_value=True):
        yield


@override_settings(AUTOMATION_SEMEAR_MENSAGENS_AO_CRIAR_LOJA=True)
class RetiradaNaoSaiParaEntregaTest(TestCase):
    def setUp(self):
        dono = User.objects.create_user(username='dono-ret', email='r@x.com', password='x')
        self.loja = Store.objects.create(name='Loja Ret', slug='loja-ret', owner=dono, status='active')
        from apps.automation.models import CompanyProfile
        from apps.whatsapp.models import WhatsAppAccount
        conta = WhatsAppAccount.objects.create(name='Conta', phone_number_id='RET1', waba_id='WRET')
        CompanyProfile.objects.filter(account=conta).delete()
        perfil = self.loja.automation_profile
        perfil.account = conta
        perfil.save(update_fields=['account'])

    def _pedido(self, metodo):
        return StoreOrder.objects.create(
            store=self.loja, customer_name='Ana', customer_phone='5563999990001',
            customer_email='a@a.com', subtotal=10, total=10, delivery_method=metodo,
        )

    def _avisar(self, pedido, status):
        from apps.whatsapp.tasks.automation_tasks import notify_order_status_change
        with mock.patch('apps.whatsapp.services.message_service.MessageService') as svc:
            notify_order_status_change(str(pedido.id), status)
        return svc.return_value.send_text_message

    def test_retirada_em_saiu_para_entrega_fica_quieta(self):
        self._avisar(self._pedido('pickup'), 'out_for_delivery').assert_not_called()

    def test_entrega_continua_avisando_que_saiu(self):
        self._avisar(self._pedido('delivery'), 'out_for_delivery').assert_called_once()

    def test_retirada_continua_recebendo_pronto(self):
        self._avisar(self._pedido('pickup'), 'ready').assert_called_once()
