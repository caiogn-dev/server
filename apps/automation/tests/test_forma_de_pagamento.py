"""O cliente pede cartão e recebe cartão.

O detector de intenções só conhecia PIX. O padrão que capturava pagamento era
`quero pagar|forma de pagamento|como pago`, e "quero pagar no cartão" casa com
`quero pagar` — então o cliente pedia cartão e recebia um código PIX.

E quando ele dizia que não conseguia abrir o link, não havia resposta nenhuma:
a venda morria ali, com o pedido montado.
"""
import pytest

from apps.automation.services.forma_de_pagamento import (
    CARTAO, DINHEIRO, MAQUININHA, PIX, detectar,
)


@pytest.mark.parametrize('frase', [
    'quero pagar no cartão',
    'cartao de credito',
    'no crédito',
    'débito',
    'vou passar no cartão',
    'aceita visa?',
    'pode ser no master',
])
def test_cartao(frase):
    assert detectar(frase) == CARTAO


@pytest.mark.parametrize('frase', [
    'pix',
    'quero pagar no pix',
    'manda o pix',
    'prefiro PIX',
])
def test_pix(frase):
    assert detectar(frase) == PIX


@pytest.mark.parametrize('frase', [
    'dinheiro',
    'vou pagar em dinheiro',
    'em espécie',
    'troco pra 50',
])
def test_dinheiro(frase):
    assert detectar(frase) == DINHEIRO


class TestOFallbackDaMaquininha:
    """"E caso ele fale: 'não consigo pagar pelo link' ENVIAMOS A MÁQUINA!" """

    @pytest.mark.parametrize('frase', [
        'não consigo pagar pelo link',
        'nao consegui pagar',
        'o link não abre',
        'deu erro no link',
        'não foi',
        'tem maquininha?',
        'passa na maquininha',
        'pode ser na máquina',
        'pago na entrega',
        'na hora da entrega',
    ])
    def test_reconhece(self, frase):
        assert detectar(frase) == MAQUININHA

    def test_vem_ANTES_de_cartao(self):
        """Senão o bot devolve o link que o cliente disse não conseguir abrir."""
        assert detectar('não consigo pagar pelo link do cartão') == MAQUININHA

    def test_reclamacao_de_link_nao_vira_pedido_de_pix(self):
        assert detectar('não consigo pagar pelo link, e o pix também não foi') == MAQUININHA


class TestNaoPodeChutar:
    @pytest.mark.parametrize('frase', [
        '', '   ', 'boa noite', 'quero uma salada', 'quanto tempo demora?',
        None,
    ])
    def test_sem_sinal_devolve_None(self, frase):
        """Chutar a forma de pagamento é como o cliente recebe PIX pedindo cartão."""
        assert detectar(frase) is None

    def test_cartao_vence_pix_quando_os_dois_aparecem(self):
        """"não quero pix, prefiro cartão" — o desejo é o cartão."""
        assert detectar('não quero pix, prefiro cartão') == CARTAO

    def test_acento_nao_muda_nada(self):
        assert detectar('CRÉDITO') == detectar('credito') == CARTAO

    def test_palavra_dentro_de_outra_nao_conta(self):
        """"pixel", "cartaz" — casar por substring é como 'sem' virou 'sempre'."""
        assert detectar('vi no pixel da tela') is None
        assert detectar('coloquei um cartaz') is None
