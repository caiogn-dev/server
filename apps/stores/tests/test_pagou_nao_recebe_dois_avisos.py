"""Quem acabou de pagar recebe UM aviso, não dois.

Enna, 14/10, 12:44:20 — no mesmo segundo:
    ✅ Pagamento Confirmado! (webhook do pagamento, com itens e total)
    🎉 Pedido confirmado! Pedido #… está confirmado e já entrou na fila.

O pagamento confirma o pedido, e a mudança de status disparava a automática
de "confirmado" — o mesmo fato dito duas vezes. Regra: "confirmado" logo
depois do pagamento (até 2 min) não gera aviso. Pedido confirmado à mão,
sem pagamento recente, continua avisando.
"""
from datetime import timedelta
from unittest import mock

import pytest
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.stores.models import Store, StoreOrder

User = get_user_model()


@pytest.fixture(autouse=True)
def _janela_aberta():
    with mock.patch('apps.automation.mensageiro.janela.aberta', return_value=True):
        yield


@override_settings(AUTOMATION_SEMEAR_MENSAGENS_AO_CRIAR_LOJA=True)
class PagouNaoRecebeDoisAvisosTest(TestCase):
    def setUp(self):
        dono = User.objects.create_user(username='dono-pag', email='p@x.com', password='x')
        self.loja = Store.objects.create(name='Loja Pag', slug='loja-pag', owner=dono, status='active')
        from apps.automation.models import CompanyProfile
        from apps.whatsapp.models import WhatsAppAccount
        conta = WhatsAppAccount.objects.create(name='Conta', phone_number_id='PAG1', waba_id='WPAG')
        CompanyProfile.objects.filter(account=conta).delete()
        perfil = self.loja.automation_profile
        perfil.account = conta
        perfil.save(update_fields=['account'])

    def _pedido(self, pago_ha=None):
        return StoreOrder.objects.create(
            store=self.loja, customer_name='Enna', customer_phone='5563992129009',
            customer_email='e@e.com', subtotal=10, total=10, delivery_method='delivery',
            paid_at=(timezone.now() - pago_ha) if pago_ha is not None else None,
        )

    def _avisar(self, pedido, status):
        from apps.whatsapp.tasks.automation_tasks import notify_order_status_change
        with mock.patch('apps.whatsapp.services.message_service.MessageService') as svc:
            notify_order_status_change(str(pedido.id), status)
        return svc.return_value.send_text_message

    def test_confirmado_logo_depois_de_pagar_fica_quieto(self):
        self._avisar(self._pedido(pago_ha=timedelta(seconds=5)), 'confirmed').assert_not_called()

    def test_confirmado_sem_pagamento_continua_avisando(self):
        self._avisar(self._pedido(), 'confirmed').assert_called_once()

    def test_confirmado_muito_depois_do_pagamento_avisa(self):
        self._avisar(self._pedido(pago_ha=timedelta(minutes=30)), 'confirmed').assert_called_once()
