"""O que o dono precisa ver e fazer com a carteira, sem abrir o banco.

TRÊS PERGUNTAS QUE A TELA RESPONDE, e por que cada uma importa:

- **De onde veio o saldo que está em circulação?** Cashback de compra é custo
  de marketing; carteira pré-paga é dinheiro que JÁ ENTROU no caixa. Somar os
  dois num número só faz o dono achar que deve R$ 5.000 quando R$ 4.500 já
  foram pagos adiantado por clientes.

- **Quanto disso já virou desconto?** Saldo em circulação é promessa; resgatado
  é a conta paga.

- **Como creditar na mão?** Cliente que reclamou, brinde, erro de cobrança —
  hoje isso exigiria abrir o Django shell em produção, que é como se perde
  dinheiro sem rastro. O ajuste manual grava QUEM fez e POR QUÊ.

E a trava que sustenta tudo: só o dono da loja vê e mexe. Cashback é dinheiro,
e endpoint de dinheiro sem checagem de dono é IDOR — o erro que já apareceu
neste repositório em junho.
"""
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.stores.models import Store, StoreCashbackLot, StoreOrder
from apps.stores.services.cashback_service import CashbackService

TELEFONE = '5563991386719'
User = get_user_model()


@pytest.fixture
def dono(db):
    return User.objects.create_user(username='dono-painel', email='d@t.local', password='x')


@pytest.fixture
def loja(db, dono):
    return Store.objects.create(
        owner=dono, name='Cê Teste', slug='ce-teste-painel', store_type='food',
        status='active',
        metadata={
            'cashback_enabled': True, 'cashback_percent': '3',
            'cashback_expiry_days': '30',
            'carteira_tiers': [
                {'id': 'familia', 'nome': 'Família', 'paga': '395.00',
                 'credito': '456.00', 'cupons_entrega': 5},
            ],
        },
    )


@pytest.fixture
def cliente(loja, dono):
    c = APIClient()
    c.force_authenticate(user=dono)
    return c


def _saldos(loja):
    """Um de cada origem, para a quebra ter o que separar.

    A carteira entra pelo CAMINHO REAL (cobrança paga → webhook):
    `credit_prepaid` sozinho credita o dinheiro mas não concede os cupons de
    entrega, então um atalho aqui produziria uma tela verde sobre um estado
    que a produção nunca gera.
    """
    from apps.stores.models import StorePayment
    from apps.stores.services.checkout_service import CheckoutService

    cobranca = StorePayment.objects.create(
        store=loja, order=None, amount=Decimal('395.00'),
        payment_method=StorePayment.PaymentMethod.PIX,
        status=StorePayment.PaymentStatus.PENDING,
        external_reference=f'carteira-familia-{TELEFONE}-p1', payer_name='C',
    )
    CheckoutService._handle_storepayment_webhook(cobranca, 'approved')
    pedido = StoreOrder.objects.create(
        store=loja, customer_name='C', customer_phone=TELEFONE,
        subtotal=Decimal('100.00'), delivery_fee=Decimal('0'), discount=Decimal('0'),
        total=Decimal('100.00'), payment_status='paid',
    )
    CashbackService.credit_purchase(pedido)


@pytest.mark.django_db
class TestResumoSeparaAsOrigens:

    def test_carteira_e_cashback_aparecem_separados(self, loja, cliente):
        _saldos(loja)
        r = cliente.get(f'/api/v1/stores/{loja.slug}/cashback/')
        assert r.status_code == 200, r.content
        porOrigem = r.json()['resumo']['por_origem']

        assert Decimal(str(porOrigem['prepaid'])) == Decimal('456.00')
        assert Decimal(str(porOrigem['purchase'])) == Decimal('3.00')
        assert Decimal(str(r.json()['resumo']['saldo_em_circulacao'])) == Decimal('459.00')

    def test_dinheiro_ja_recebido_nao_se_confunde_com_custo(self, loja, cliente):
        """`prepaid` foi PAGO pelo cliente; `purchase` a loja deu de brinde."""
        _saldos(loja)
        resumo = cliente.get(f'/api/v1/stores/{loja.slug}/cashback/').json()['resumo']
        assert Decimal(str(resumo['saldo_pago_pelo_cliente'])) == Decimal('456.00')
        assert Decimal(str(resumo['saldo_concedido_pela_loja'])) == Decimal('3.00')


@pytest.mark.django_db
class TestLinhaDoCliente:

    def test_mostra_de_onde_vem_o_saldo_e_os_cupons(self, loja, cliente):
        _saldos(loja)
        linha = cliente.get(f'/api/v1/stores/{loja.slug}/cashback/').json()['results'][0]
        assert linha['phone'] == TELEFONE
        assert Decimal(str(linha['saldo'])) == Decimal('459.00')
        assert Decimal(str(linha['saldo_carteira'])) == Decimal('456.00')
        assert linha['cupons_entrega'] == 5


@pytest.mark.django_db
class TestCreditoManual:

    def _ajustar(self, cliente, loja, **campos):
        return cliente.post(
            f'/api/v1/stores/{loja.slug}/cashback/ajustar/', campos, format='json',
        )

    def test_dono_credita_saldo_com_motivo(self, loja, cliente):
        r = self._ajustar(cliente, loja, phone=TELEFONE, valor='50.00',
                          motivo='Pedido atrasado, cortesia')
        assert r.status_code == 201, r.content
        assert CashbackService.balance(loja, TELEFONE, verificado=True) == Decimal('50.00')

        lote = StoreCashbackLot.objects.get(store=loja, origin=StoreCashbackLot.Origin.ADJUST)
        assert lote.coupon_code == 'Pedido atrasado, cortesia'[:50]

    def test_ajuste_sem_motivo_e_recusado(self, loja, cliente):
        """Crédito sem motivo é dinheiro saindo sem rastro."""
        r = self._ajustar(cliente, loja, phone=TELEFONE, valor='50.00')
        assert r.status_code == 400
        assert CashbackService.balance(loja, TELEFONE, verificado=True) == Decimal('0.00')

    def test_valor_invalido_e_recusado(self, loja, cliente):
        """Zero, texto e vazio são recusados. NEGATIVO não: dá baixa."""
        for valor in ['0', 'abc', '']:
            r = self._ajustar(cliente, loja, phone=TELEFONE, valor=valor, motivo='x')
            assert r.status_code == 400, f'aceitou valor {valor!r}'
        assert not StoreCashbackLot.objects.filter(store=loja).exists()

    def test_valor_negativo_da_baixa_em_vez_de_ser_recusado(self, loja, cliente):
        """O ajuste só sabia creditar. Quando o cliente gastava o saldo por fora
        — desconto no WhatsApp, no balcão — o painel seguia mostrando o crédito
        e a loja pagava o mesmo desconto duas vezes."""
        self._ajustar(cliente, loja, phone=TELEFONE, valor='50.00', motivo='cortesia')

        r = self._ajustar(cliente, loja, phone=TELEFONE, valor='-20.00',
                          motivo='usou no balcão')
        assert r.status_code in (200, 201), r.content
        assert CashbackService.balance(loja, TELEFONE, verificado=True) == Decimal('30.00')

    def test_baixa_maior_que_o_saldo_nunca_deixa_negativo(self, loja, cliente):
        self._ajustar(cliente, loja, phone=TELEFONE, valor='10.00', motivo='cortesia')

        self._ajustar(cliente, loja, phone=TELEFONE, valor='-999.00', motivo='engano')
        assert CashbackService.balance(loja, TELEFONE, verificado=True) == Decimal('0.00')

    def test_ajuste_acima_do_teto_e_recusado_nos_dois_sentidos(self, loja, cliente):
        """Um zero a mais num ajuste manual só aparece no fechamento do mês."""
        for valor in ['9000.00', '-9000.00']:
            r = self._ajustar(cliente, loja, phone=TELEFONE, valor=valor, motivo='x')
            assert r.status_code == 400, f'aceitou {valor!r}'

    def test_o_credito_manual_so_aparece_para_o_numero_comprovado(self, loja, cliente):
        """Até 12/set a cortesia da loja saía sem prova. Desde então todo saldo
        — cashback, indicação, carteira e crédito manual — exige o número
        confirmado pelo código do WhatsApp: senão bastava digitar o telefone
        de quem ganhou o brinde para gastá-lo."""
        self._ajustar(cliente, loja, phone=TELEFONE, valor='50.00', motivo='brinde')
        assert CashbackService.balance(loja, TELEFONE, verificado=False) == Decimal('0.00')
        assert CashbackService.balance(loja, TELEFONE, verificado=True) == Decimal('50.00')
    def test_estranho_nao_le_a_carteira_da_loja(self, loja, db):
        outro = User.objects.create_user(username='estranho', email='e@t.local', password='x')
        c = APIClient(); c.force_authenticate(user=outro)
        assert c.get(f'/api/v1/stores/{loja.slug}/cashback/').status_code == 403

    def test_estranho_nao_credita_saldo_na_loja_dos_outros(self, loja, db):
        outro = User.objects.create_user(username='estranho2', email='e2@t.local', password='x')
        c = APIClient(); c.force_authenticate(user=outro)
        r = c.post(f'/api/v1/stores/{loja.slug}/cashback/ajustar/',
                   {'phone': TELEFONE, 'valor': '999.00', 'motivo': 'x'}, format='json')
        assert r.status_code == 403
        assert not StoreCashbackLot.objects.filter(store=loja).exists()

    def test_visitante_sem_login_nao_credita_nada(self, loja, db):
        r = APIClient().post(f'/api/v1/stores/{loja.slug}/cashback/ajustar/',
                             {'phone': TELEFONE, 'valor': '999.00', 'motivo': 'x'}, format='json')
        assert r.status_code in (401, 403)
        assert not StoreCashbackLot.objects.filter(store=loja).exists()
