"""'Olá, .!' — o nome do WhatsApp era um ponto (28/09, Cê Saladas 13:35)."""
from unittest.mock import Mock

from apps.whatsapp.intents.handlers.base import IntentHandler


def _handler(nome):
    h = IntentHandler.__new__(IntentHandler)
    h.conversation = Mock(contact_name=nome)
    return h


def test_nome_sem_letra_vira_cliente():
    assert _handler('.').get_customer_name() == 'Cliente'
    assert _handler('🙂').get_customer_name() == 'Cliente'
    assert _handler('   ').get_customer_name() == 'Cliente'
    assert _handler(None).get_customer_name() == 'Cliente'


def test_nome_de_verdade_passa():
    assert _handler('Ângela Victor').get_customer_name() == 'Ângela Victor'
