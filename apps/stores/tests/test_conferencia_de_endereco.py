"""Pin e endereço digitado têm que concordar — e ninguém conferia.

Caso real, 14/ago, pedido CE-2608140823 da Cê Saladas:

    texto digitado : "Av jk 110 sul Clínica DVI, Lote 21"
    pin gravado    : -10.2298952, -48.3205388
    reverse do pin : "Q. 706 Sul Avenida LO 19, Palmas - TO"

5,15 km de diferença. O link do Maps é montado das COORDENADAS, não do texto,
então o entregador foi para a 706 Sul. E o frete também sai do pin: a mesma
cliente pagou R$ 7,00 em 31/07 e R$ 11,00 neste — R$ 4,00 a mais para ir ao
lugar errado.

Os dois pedidos vieram marcados `coordinate_source: customer_selected_pin` com
`coordinates_confirmed: true`. O sistema tratava isso como verdade absoluta.

Este módulo não decide nem bloqueia venda: ele só percebe a contradição e
registra, para a loja ver ANTES de o entregador sair. Quando não dá para
afirmar — sem pin, sem texto, geocoder fora do ar — devolve None. Inventar
divergência daria alarme falso em todo pedido, e alarme que toca sempre é
alarme desligado.
"""
import pytest

from apps.stores.services.conferencia_de_endereco import conferir

# O pedido real que motivou tudo.
BARBARA = {
    'street': 'Av jk 110 sul Clínica DVI ', 'number': 'Lote 21',
    'neighborhood': 'Plano diretor sul ', 'city': 'Palmas', 'state': 'TO',
    'lat': -10.2298952, 'lng': -48.3205388,
    'raw_address': 'Av jk 110 sul Clínica DVI , Lote 21 · Plano diretor sul',
    'coordinate_source': 'customer_selected_pin', 'coordinates_confirmed': True,
}


def _geocoder(resposta):
    """Geocoder falso — os testes não podem depender da API do Google."""
    def reverse(lat, lng):
        return resposta
    return reverse


ERRADO = {'formatted_address': 'Q. 706 Sul Avenida LO 19, 16 - Plano Diretor Sul, '
                               'Palmas - TO, 77022-414, Brasil'}
CERTO = {'formatted_address': 'Q. 110 Sul Alameda 1, 56 - 110 Sul, '
                              'Palmas - TO, 77020-142, Brasil'}


class TestOCasoReal:
    def test_pin_na_706_com_texto_da_110_e_divergencia(self):
        d = conferir(BARBARA, reverse_geocode=_geocoder(ERRADO))

        assert d is not None

    def test_a_divergencia_diz_as_DUAS_leituras(self):
        """Quem lê o aviso precisa saber para onde ir — e para onde NÃO ir."""
        d = conferir(BARBARA, reverse_geocode=_geocoder(ERRADO))

        assert d['digitado'] == '110 sul'
        assert d['pin'] == '706 sul'

    def test_o_mesmo_endereco_com_o_pin_certo_nao_acusa(self):
        """31/07, mesma cliente, mesmo texto, pin correto: silêncio."""
        assert conferir(BARBARA, reverse_geocode=_geocoder(CERTO)) is None


class TestNaoPodeDarAlarMEFalso:
    def test_sem_pin_nao_opina(self):
        sem = {k: v for k, v in BARBARA.items() if k not in ('lat', 'lng')}

        assert conferir(sem, reverse_geocode=_geocoder(ERRADO)) is None

    def test_sem_quadra_no_texto_nao_opina(self):
        """Endereço de rua comum não tem quadra — a maior parte do Brasil."""
        comum = {**BARBARA, 'street': 'Rua das Flores', 'raw_address': 'Rua das Flores, 42'}

        assert conferir(comum, reverse_geocode=_geocoder(ERRADO)) is None

    def test_geocoder_fora_do_ar_nao_opina(self):
        def explode(lat, lng):
            raise RuntimeError('google fora')

        assert conferir(BARBARA, reverse_geocode=explode) is None

    def test_geocoder_sem_resposta_nao_opina(self):
        assert conferir(BARBARA, reverse_geocode=_geocoder(None)) is None

    def test_pin_sem_quadra_no_reverse_nao_opina(self):
        vago = {'formatted_address': 'Palmas - TO, Brasil'}

        assert conferir(BARBARA, reverse_geocode=_geocoder(vago)) is None

    def test_retirada_na_loja_nao_opina(self):
        assert conferir({}, reverse_geocode=_geocoder(ERRADO)) is None

    def test_lixo_no_campo_nao_levanta(self):
        for lixo in (None, 'uma string', [], 42):
            assert conferir(lixo, reverse_geocode=_geocoder(ERRADO)) is None


class TestVariacoesDeEscrita:
    """O cliente escreve como quer; a conferência não pode depender disso."""

    @pytest.mark.parametrize('texto', [
        'Av jk 110 sul Clínica DVI',
        'AV JK QUADRA 110 SUL',
        'quadra 110sul, lote 21',
        'Q. 110 Sul Alameda 1',
    ])
    def test_reconhece_a_quadra_escrita_de_varios_jeitos(self, texto):
        d = conferir({**BARBARA, 'street': texto, 'raw_address': texto},
                     reverse_geocode=_geocoder(ERRADO))

        assert d is not None and d['digitado'] == '110 sul'

    def test_norte_e_sul_nao_se_confundem(self):
        """110 Norte e 110 Sul são lados opostos da cidade."""
        norte = {**BARBARA, 'street': 'Quadra 110 norte', 'raw_address': 'Quadra 110 norte'}
        pin_sul = {'formatted_address': 'Q. 110 Sul Alameda 1, Palmas - TO'}

        assert conferir(norte, reverse_geocode=_geocoder(pin_sul)) is not None
