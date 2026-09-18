"""Loja fechada no fluxo de botões: o recado de agendamento leva o link do cardápio.

REGRA DO DONO (18/09): loja fechada → o bot manda o link do cardápio e diz
que dá para pedir com agendamento. O fluxo de botões já oferecia agendar
(`_offer_scheduling`), mas sem o link — quem prefere escolher pelo site não
tinha por onde.
"""
from types import SimpleNamespace
from unittest.mock import patch

from apps.whatsapp.intents.handlers.interactive import InteractiveReplyHandler


def _handler(**loja):
    h = InteractiveReplyHandler.__new__(InteractiveReplyHandler)
    base = dict(name='Cê Saladas', slug='ce-saladas', website_url='https://cesaladas.com.br',
                custom_domain='', operating_hours={})
    base.update(loja)
    h.store = SimpleNamespace(**base)
    return h


def test_recado_de_loja_fechada_leva_o_link_do_cardapio():
    h = _handler()
    with patch.object(InteractiveReplyHandler, '_next_open_slots',
                      return_value=[{'id': 'sched_2026-09-21_09:00', 'title': 'Segunda 09:00',
                                     'description': 'Agendar para este horário'}]):
        resultado = h._offer_scheduling([])

    assert 'https://cesaladas.com.br' in str(vars(resultado))


def test_recado_continua_oferecendo_os_horarios():
    h = _handler()
    with patch.object(InteractiveReplyHandler, '_next_open_slots',
                      return_value=[{'id': 'sched_2026-09-21_09:00', 'title': 'Segunda 09:00',
                                     'description': 'Agendar para este horário'}]):
        resultado = h._offer_scheduling([])

    assert 'Segunda 09:00' in str(vars(resultado))
