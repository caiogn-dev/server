"""Aviso ao cliente sai pelo número de ENVIO, não pelo de identidade (26/10).

`normalize_phone_number` acrescenta o nono dígito — é a chave que junta o
mesmo cliente. Para MANDAR, o número é o que o WhatsApp conhece
(`telefone_para_envio_e164`): a medição em `StoreOrder` deu 29% de falha com
o dígito inventado contra 1,5% sem. O pedido já grava o número de envio; os
caminhos de aviso o reprocessavam com a função de identidade.
"""
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.stores.api.webhooks import MercadoPagoWebhookView
from apps.stores.models import Store, StoreOrder

User = get_user_model()

SEM_NONO = '556391124171'  # wa_id como a Meta entrega


class NumeroDeEnvioTests(TestCase):
    def setUp(self):
        owner = User.objects.create_user(username='ow-envio', email='ow-envio@t.com', password='x')
        self.store = Store.objects.create(name='Loja E', slug='loja-envio', owner=owner, status='active')
        self.pedido = StoreOrder.objects.create(
            store=self.store, customer_name='Ana', customer_phone=SEM_NONO,
            subtotal=Decimal('40'), total=Decimal('40'),
        )

    def test_confirmacao_de_pagamento_nao_inventa_digito(self):
        with patch.object(Store, 'get_whatsapp_account', return_value=MagicMock()), \
                patch('apps.automation.mensageiro.enviar_texto') as enviar:
            MercadoPagoWebhookView()._send_payment_confirmation_whatsapp(self.pedido)
        self.assertEqual(enviar.call_args[0][1], SEM_NONO)


def test_caminhos_de_envio_nao_usam_a_funcao_de_identidade():
    """Catraca: quem MANDA mensagem não passa o número por normalize_phone_number."""
    apps = Path(__file__).resolve().parents[2]
    for rel in (
        'whatsapp/tasks/automation_tasks.py',
        'stores/api/webhooks.py',
        'stores/services/mensagem_do_entregador.py',
    ):
        assert 'normalize_phone_number(' not in (apps / rel).read_text(), rel
    assert '_normalize_phone_number' not in (apps / 'stores/models/order.py').read_text()
