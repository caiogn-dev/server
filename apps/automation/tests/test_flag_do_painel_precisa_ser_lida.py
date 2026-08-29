"""
Botão no painel que o backend nunca lê é mentira contada ao lojista.

Esta classe de defeito já apareceu quatro vezes:

  free_delivery_threshold   UI que o backend nunca aplicou (ago/24)
  operating_hours.is_open   dia marcado fechado continuava vendendo (29/ago)
  auto_reply_enabled        desligar o bot não desligava nada (29/ago)
  welcome_message_enabled   e menu_auto_send: zero leitura no backend

O dono resumiu: "mudar no painel mas não mudar no backend é osso".

Este teste é a peneira. Para cada flag de comportamento, exige pelo menos uma
leitura FORA de model, migration, serializer, admin e teste — ou seja, algum
lugar que de fato DECIDA algo com ela.

Quando uma flag nova entrar, ela precisa nascer nesta lista. Se ainda não tem
comportamento, ela não deveria estar no painel.
"""
import re
from pathlib import Path

import pytest


RAIZ = Path(__file__).resolve().parents[3]

# Flags de comportamento que o painel expõe como interruptor.
FLAGS = [
    'delivery_enabled',
    'pickup_enabled',
    'min_order_value',
    'free_delivery_threshold',
    'default_delivery_fee',
    'auto_reply_enabled',
    'abandoned_cart_notification',
    'abandoned_cart_delay_minutes',
    'pix_notification_enabled',
    'payment_confirmation_enabled',
    'order_status_notification_enabled',
    'delivery_notification_enabled',
    'use_ai_agent',
]

# Ainda SEM comportamento no backend. Estão aqui para o teste não mentir sobre
# o estado do sistema — e para a lista encolher, nunca crescer.
SEM_COMPORTAMENTO_AINDA = {
    'welcome_message_enabled',
    'menu_auto_send',
}

IGNORAR = re.compile(r'/(migrations|tests?)/|/models/|serializers|admin\.py|test_')


def _arquivos_de_codigo():
    """Todo .py de app, menos o que não decide nada."""
    for caminho in (RAIZ / 'apps').rglob('*.py'):
        if IGNORAR.search(str(caminho)):
            continue
        yield caminho


def _leituras(flag: str) -> list[str]:
    """Onde a flag aparece em código que decide algo."""
    achados = []
    for caminho in _arquivos_de_codigo():
        try:
            texto = caminho.read_text(encoding='utf-8', errors='ignore')
        except OSError:
            continue
        for n, linha in enumerate(texto.splitlines(), 1):
            if flag in linha:
                achados.append(f'{caminho.relative_to(RAIZ)}:{n}')
    return achados


@pytest.mark.parametrize('flag', FLAGS)
def test_a_flag_decide_alguma_coisa(flag):
    linhas = _leituras(flag)
    assert linhas, (
        f'"{flag}" é um interruptor no painel e o backend nunca lê: '
        f'o lojista mexe e nada muda. Ou implemente o comportamento, ou tire '
        f'o botão da tela.'
    )


@pytest.mark.parametrize('flag', sorted(SEM_COMPORTAMENTO_AINDA))
def test_a_lista_de_pendentes_nao_mente(flag):
    """Se alguém implementar o comportamento, a flag sai desta lista."""
    linhas = _leituras(flag)
    # `signals.py` só atribui o padrão na criação — não é decisão.
    decisoes = [l for l in linhas if 'signals.py' not in l]
    assert not decisoes, (
        f'"{flag}" já tem comportamento em {decisoes}: '
        f'mova-a para FLAGS e tire de SEM_COMPORTAMENTO_AINDA.'
    )
