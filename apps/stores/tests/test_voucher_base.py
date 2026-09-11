import pytest

from apps.stores.services.voucher.base import (
    DadosDoVoucher, ResultadoDaCobranca, VoucherProvider,
)


def test_provider_e_abstrato():
    """Instanciar o protocolo direto tem que ser impossível — a junta existe
    para ser implementada, não usada."""
    with pytest.raises(TypeError):
        VoucherProvider()


def test_um_provider_concreto_so_precisa_de_cobrar():
    """Este teste é o contrato que a Volus vai cumprir depois."""
    class ProviderFalso(VoucherProvider):
        def cobrar(self, order, dados, total=None):
            return ResultadoDaCobranca(
                aprovado=True, status='approved', external_id='x',
                mensagem='', bruto={},
            )

    resultado = ProviderFalso().cobrar(None, DadosDoVoucher('t', 'vr', 'ANA', '390'))
    assert resultado.aprovado is True
    assert resultado.status == 'approved'


def test_dados_do_voucher_nao_carrega_pan_nem_cvv():
    """Se um dia alguém acrescentar `number` aqui, o PAN passa a atravessar o
    servidor e o escopo PCI muda. Este teste é a trava."""
    campos = set(DadosDoVoucher.__dataclass_fields__)
    assert campos == {'card_token', 'brand', 'holder_name', 'holder_document'}
