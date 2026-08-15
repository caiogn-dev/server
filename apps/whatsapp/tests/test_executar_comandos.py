"""Os atalhos "/" precisam AGIR — hoje só sabem se apresentar.

O interpretador existe desde 13/ago e o painel mostra a paleta, mas a execução
respondia "ainda não está ligado — em breve". Ou seja: a dona digita `/pix`,
lê um aviso de obra, e vai fazer à mão do mesmo jeito. O atalho que não age não
economiza os 5 minutos que motivaram tudo — só adiciona um passo.

Duas regras que valem dinheiro:

- **Só o pedido daquela conversa.** Agir no pedido errado é pior que não agir;
  cancelar a venda de outro cliente é irreversível.
- **Comando destrutivo exige confirmação explícita.** `/cancelar` sem confirmar
  transforma um erro de digitação em venda perdida.
"""
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from apps.whatsapp.services.comandos import executar


@pytest.fixture
def loja(db):
    from apps.stores.tests.factories import make_store
    return make_store(name='Cê Saladas', city='Palmas', state='TO')


@pytest.fixture
def pedido(loja):
    from apps.stores.models import StoreOrder
    return StoreOrder.objects.create(
        store=loja, total=Decimal('142.00'), subtotal=Decimal('142.00'),
        status='pending', payment_status='pending', payment_method='pix',
        customer_phone='+5563984143551', customer_name='Dyana',
    )


def _conversa(telefone='+5563984143551'):
    return MagicMock(phone_number=telefone, id='conv-1')


@pytest.mark.django_db
class TestComandosDeLeitura:
    def test_pedido_mostra_o_resumo(self, loja, pedido):
        r = executar('pedido', '', conversa=_conversa(), store=loja)

        assert r.ok
        assert pedido.order_number in r.texto
        assert '142' in r.texto

    def test_status_mostra_a_etapa(self, loja, pedido):
        r = executar('status', '', conversa=_conversa(), store=loja)

        assert r.ok
        assert 'pendente' in r.texto.lower() or 'Pendente' in r.texto

    def test_leitura_nao_manda_nada_pro_cliente(self, loja, pedido):
        """`/pedido` é consulta da dona — a cliente não pode receber nada."""
        r = executar('pedido', '', conversa=_conversa(), store=loja)

        assert r.enviar_ao_cliente is False

    def test_sem_pedido_avisa_em_vez_de_estourar(self, loja):
        r = executar('pedido', '', conversa=_conversa('+5563900000000'), store=loja)

        assert not r.ok
        assert 'nenhum pedido' in r.texto.lower()


@pytest.mark.django_db
class TestComandosQueMudamOPedido:
    def test_entregue_exige_confirmacao(self, loja, pedido):
        r = executar('entregue', '', conversa=_conversa(), store=loja, confirmado=False)

        assert not r.ok
        pedido.refresh_from_db()
        assert pedido.status == 'pending'

    def test_entregue_confirmado_muda_o_status(self, loja, pedido):
        r = executar('entregue', '', conversa=_conversa(), store=loja, confirmado=True)

        assert r.ok
        pedido.refresh_from_db()
        assert pedido.status == 'delivered'

    def test_cancelar_exige_confirmacao(self, loja, pedido):
        """Erro de digitação não pode virar venda perdida."""
        executar('cancelar', '', conversa=_conversa(), store=loja, confirmado=False)

        pedido.refresh_from_db()
        assert pedido.status != 'cancelled'

    def test_cancelar_confirmado_cancela(self, loja, pedido):
        r = executar('cancelar', '', conversa=_conversa(), store=loja, confirmado=True)

        assert r.ok
        pedido.refresh_from_db()
        assert pedido.status == 'cancelled'


@pytest.mark.django_db
class TestOEscopoDaConversa:
    def test_nao_age_no_pedido_de_OUTRO_cliente(self, loja, pedido):
        """Cancelar a venda de outra pessoa é irreversível."""
        r = executar('cancelar', '', conversa=_conversa('+5563911112222'),
                     store=loja, confirmado=True)

        assert not r.ok
        pedido.refresh_from_db()
        assert pedido.status == 'pending'

    def test_nao_age_em_pedido_de_OUTRA_loja(self, loja, pedido):
        from apps.stores.tests.factories import make_store
        outra = make_store(name='Kero Kero')

        r = executar('cancelar', '', conversa=_conversa(), store=outra, confirmado=True)

        assert not r.ok
        pedido.refresh_from_db()
        assert pedido.status == 'pending'


@pytest.mark.django_db
class TestNotaEBot:
    def test_nota_e_interna(self, loja, pedido):
        r = executar('nota', 'cliente pediu sem cebola', conversa=_conversa(), store=loja)

        assert r.ok
        assert r.enviar_ao_cliente is False
        pedido.refresh_from_db()
        assert 'sem cebola' in str(pedido.metadata)

    def test_nota_vazia_nao_grava_nada(self, loja, pedido):
        r = executar('nota', '', conversa=_conversa(), store=loja)

        assert not r.ok

    def test_bot_off_desliga(self, loja, pedido):
        with patch('apps.whatsapp.services.comandos._mudar_bot') as mudar:
            r = executar('bot', 'off', conversa=_conversa(), store=loja)

        assert r.ok
        mudar.assert_called_once()
        assert mudar.call_args[0][1] is False

    def test_bot_sem_argumento_pergunta(self, loja, pedido):
        r = executar('bot', '', conversa=_conversa(), store=loja)

        assert not r.ok


@pytest.mark.django_db
class TestOQueNaoPodeAcontecer:
    def test_comando_desconhecido_nao_age(self, loja, pedido):
        r = executar('pixx', '', conversa=_conversa(), store=loja)

        assert not r.ok
        assert r.enviar_ao_cliente is False

    def test_nada_do_resultado_vaza_pro_cliente_por_engano(self, loja, pedido):
        """Só `/pix` fala com a cliente, e ainda assim de propósito."""
        for nome in ('pedido', 'status', 'nota', 'bot', 'pixx'):
            r = executar(nome, 'off', conversa=_conversa(), store=loja)
            assert r.enviar_ao_cliente is False, nome


@pytest.mark.django_db
class TestCardapio:
    """"/cardapio" — o dono digitou esperando que existisse.

    Atalho que a pessoa tenta sozinha é atalho que faltava. Antes respondia
    "Não conheço /cardapio".
    """

    def test_manda_o_link_pra_cliente(self, loja):
        r = executar('cardapio', '', conversa=_conversa(), store=loja)

        assert r.ok
        assert r.enviar_ao_cliente is True
        assert 'http' in r.texto

    def test_a_url_e_da_LOJA(self, loja):
        """Nunca domínio fixo: foi assim que campanha da Cê Saladas saiu como "Pastita"."""
        r = executar('cardapio', '', conversa=_conversa(), store=loja)

        assert loja.slug in r.texto or getattr(loja, 'custom_domain', '') in r.texto

    def test_nao_precisa_de_pedido_aberto(self, loja):
        """Mandar cardápio é o começo da venda, não o meio."""
        r = executar('cardapio', '', conversa=_conversa('+5563900000000'), store=loja)

        assert r.ok


@pytest.mark.django_db
class TestOAtalhoLiquidaAVenda:
    """`/entregue` também setava o status na mão e pulava a regra do dinheiro.

    Escrito em 14/08 com o mesmo defeito que causou os R$ 306,00 — a terceira
    cópia da mesma decisão.
    """

    def test_entregue_em_dinheiro_marca_pago(self, loja):
        from apps.stores.models import StoreOrder

        pedido = StoreOrder.objects.create(
            store=loja, total=Decimal('95.00'), subtotal=Decimal('95.00'),
            status='out_for_delivery', payment_status='pending',
            payment_method='cash', customer_phone='+5563984143551',
        )

        r = executar('entregue', '', conversa=_conversa(), store=loja, confirmado=True)

        assert r.ok
        pedido.refresh_from_db()
        assert pedido.payment_status == 'paid'

    def test_entregue_em_pix_NAO_marca_pago(self, loja):
        from apps.stores.models import StoreOrder

        pedido = StoreOrder.objects.create(
            store=loja, total=Decimal('95.00'), subtotal=Decimal('95.00'),
            status='out_for_delivery', payment_status='pending',
            payment_method='pix', customer_phone='+5563984143551',
        )

        executar('entregue', '', conversa=_conversa(), store=loja, confirmado=True)

        pedido.refresh_from_db()
        assert pedido.payment_status == 'pending'
