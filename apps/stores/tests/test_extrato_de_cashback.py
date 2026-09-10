"""De ONDE veio cada real de cashback do cliente.

O dono abriu a ficha da MADU CACHEADA e não soube responder uma pergunta
simples: os R$ 3,13 dela vieram da compra DELA ou do cupom MADULASH que as
amigas usaram?

O banco sempre soube — o lote é `origin='referral'` e aponta para o pedido
CE-2609104664, que é da Juliane. Mas nada disso aparecia em lugar nenhum: nem
no painel, nem no perfil do cliente. Um programa de indicação que não diz quem
indicou é só um desconto com nome bonito.

O extrato mostra ENTRADAS (lotes) e SAÍDAS (resgates) na mesma linha do tempo,
porque "quanto eu tenho" só faz sentido junto de "o que entrou e o que saiu".
"""
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.stores.models import Store, StoreOrder
from apps.stores.models.cashback import StoreCashbackLot, StoreCashbackRedemption

User = get_user_model()


class ExtratoDeCashbackTest(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='dono-ex', password='x')
        self.outro = User.objects.create_user(username='intruso-ex', password='x')
        self.store = Store.objects.create(
            name='Loja EX', slug='loja-ex', owner=self.owner, status='active')
        self.madu = '5563992433905'
        self.url = f'/api/v1/stores/{self.store.slug}/cashback/extrato/'
        self.client.force_authenticate(user=self.owner)

    def _pedido(self, numero, nome, total='62.68'):
        return StoreOrder.objects.create(
            store=self.store, order_number=numero, customer_name=nome,
            customer_phone='5563984457253', subtotal=Decimal(total), total=Decimal(total))

    def _lote(self, origin, valor, order=None, coupon_code='', dias=30):
        return StoreCashbackLot.objects.create(
            store=self.store, phone=self.madu, origin=origin,
            amount=Decimal(valor), remaining=Decimal(valor), order=order,
            coupon_code=coupon_code,
            expires_at=timezone.now() + timedelta(days=dias))

    def _linhas(self, phone=None):
        resp = self.client.get(self.url, {'phone': phone or self.madu})
        assert resp.status_code == 200, resp.content
        return resp.json()['lancamentos']

    # ── a pergunta do dono ────────────────────────────────────────────────

    def test_indicacao_diz_de_quem_foi_o_pedido(self):
        """A resposta que faltava: veio da amiga, e a ficha diz o nome dela."""
        pedido = self._pedido('CE-2609104664', 'Juliane maximo')
        self._lote('referral', '3.13', order=pedido)
        linha = self._linhas()[0]
        assert linha['origem'] == 'referral'
        assert linha['rotulo'] == 'Indicação'
        assert linha['pedido']['numero'] == 'CE-2609104664'
        assert linha['pedido']['cliente'] == 'Juliane maximo'
        assert Decimal(str(linha['valor'])) == Decimal('3.13')

    def test_compra_propria_tambem_aponta_o_pedido(self):
        pedido = self._pedido('CE-2609103109', 'Madu Cacheada')
        self._lote('purchase', '1.88', order=pedido)
        linha = self._linhas()[0]
        assert linha['rotulo'] == 'Compra própria'
        assert linha['pedido']['numero'] == 'CE-2609103109'

    def test_credito_manual_mostra_o_motivo_no_lugar_do_pedido(self):
        self._lote('adjust', '50.00', coupon_code='CORTESIA')
        linha = self._linhas()[0]
        assert linha['rotulo'] == 'Ajuste manual'
        assert linha['pedido'] is None
        assert linha['referencia'] == 'CORTESIA'

    # ── entradas e saídas na mesma linha do tempo ─────────────────────────

    def test_resgate_aparece_como_saida(self):
        pedido = self._pedido('CE-2609110001', 'Madu Cacheada')
        StoreCashbackRedemption.objects.create(
            store=self.store, phone=self.madu, amount=Decimal('2.00'), order=pedido)
        linha = self._linhas()[0]
        assert linha['tipo'] == 'saida'
        assert linha['rotulo'] == 'Usado no pedido'
        assert Decimal(str(linha['valor'])) == Decimal('2.00')

    def test_entrada_e_saida_convivem_do_mais_novo_para_o_mais_velho(self):
        self._lote('purchase', '1.00')
        StoreCashbackRedemption.objects.create(
            store=self.store, phone=self.madu, amount=Decimal('0.50'))
        linhas = self._linhas()
        assert len(linhas) == 2
        assert [l['tipo'] for l in linhas] == ['saida', 'entrada']

    def test_quanto_ainda_resta_de_cada_entrada(self):
        """Lote parcialmente gasto: a linha diz quanto sobrou dele."""
        lote = self._lote('purchase', '5.00')
        lote.remaining = Decimal('1.50')
        lote.save(update_fields=['remaining'])
        linha = self._linhas()[0]
        assert Decimal(str(linha['valor'])) == Decimal('5.00')
        assert Decimal(str(linha['restante'])) == Decimal('1.50')

    def test_lote_vencido_aparece_marcado_em_vez_de_sumir(self):
        """Some do saldo, não do extrato: o cliente pergunta 'cadê meus R$ 5'
        e a resposta é 'venceram em tal dia'."""
        self._lote('purchase', '5.00', dias=-1)
        linha = self._linhas()[0]
        assert linha['vencido'] is True

    # ── telefone e permissão ──────────────────────────────────────────────

    def test_acha_o_cliente_em_qualquer_grafia_do_telefone(self):
        self._lote('purchase', '1.00')
        assert len(self._linhas('556392433905')) == 1     # sem o nono dígito
        assert len(self._linhas('63992433905')) == 1      # sem o DDI

    def test_sem_telefone_recusa_em_vez_de_listar_a_loja_toda(self):
        assert self.client.get(self.url).status_code == 400

    def test_nao_dono_recebe_403(self):
        self.client.force_authenticate(user=self.outro)
        assert self.client.get(self.url, {'phone': self.madu}).status_code == 403

    def test_cliente_sem_cashback_devolve_lista_vazia(self):
        assert self._linhas('5563900000000') == []
