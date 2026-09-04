"""Quem veio por quem.

O CASO REAL (04/09) é a pergunta do dono, inteira: "a Elisangela quis indicar,
mas como vou saber quem veio pela Elisangela?".

Não havia como. O rastreio funciona ponta a ponta no backend — o link
`?indica=<telefone>` vira `metadata.indicado_por` no pedido do amigo e credita
quem indicou —, e o resultado morria num número somado na tela de cashback:
"saldo de indicação: R$ 12,40". Sem nome, sem pedido, sem data.

Um programa de indicação que não diz QUEM indicou não é um programa: é um
desconto com um nome bonito. A loja não consegue agradecer a Elisangela, não
sabe quem são os divulgadores dela, e não tem como perceber que um mesmo
telefone está "indicando" trinta desconhecidos.

O dado sempre esteve gravado: o lote de indicação guarda o telefone de quem
indicou e aponta para o pedido do amigo. Só faltava alguém perguntar.
"""
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.utils import timezone
from django.test import TestCase
from rest_framework.test import APIClient

from apps.stores.models import Store, StoreCashbackLot, StoreOrder

User = get_user_model()


class IndicacoesNoPainelTest(TestCase):
    def setUp(self):
        self.dono = User.objects.create_user(username='dona-ce', password='x')
        self.store = Store.objects.create(
            billing_exempt=True, name='Cê Saladas', slug='ce-indicacoes', owner=self.dono,
            store_type='food', status='active', metadata={'cashback_enabled': True},
        )
        self.client = APIClient()
        self.client.force_authenticate(self.dono)
        self.url = f'/api/v1/stores/{self.store.slug}/indicacoes/'

        self.elisangela = '5563999547790'

    def _pedido(self, nome, phone, total='50.00'):
        return StoreOrder.objects.create(
            store=self.store, customer_name=nome, customer_phone=phone,
            subtotal=Decimal(total), total=Decimal(total),
            status='delivered', payment_status='paid',
        )

    def _indicacao(self, indicador, pedido, valor='2.50'):
        return StoreCashbackLot.objects.create(
            store=self.store, phone=indicador, amount=Decimal(valor),
            remaining=Decimal(valor), origin=StoreCashbackLot.Origin.REFERRAL,
            order=pedido, expires_at=timezone.now() + timedelta(days=30),
        )

    # ── o que o dono precisa ver ────────────────────────────────────────

    def test_diz_quem_indicou_e_quem_veio(self):
        amigo = self._pedido('Kamilly Araújo', '5563981286498')
        self._indicacao(self.elisangela, amigo, '2.50')

        resposta = self.client.get(self.url)

        self.assertEqual(resposta.status_code, 200)
        linha = resposta.data['indicacoes'][0]
        self.assertEqual(linha['indicador_phone'], self.elisangela)
        self.assertEqual(linha['amigo_nome'], 'Kamilly Araújo')
        self.assertEqual(Decimal(linha['valor']), Decimal('2.50'))
        self.assertEqual(linha['pedido'], amigo.order_number)

    def test_agrupa_por_quem_indicou(self):
        """A Elisangela que trouxe 3 pessoas é a informação, não as 3 linhas."""
        for nome, tel in [('Ana', '5563984301666'), ('Tania', '5563984153026'),
                          ('Laura', '5563992621765')]:
            self._indicacao(self.elisangela, self._pedido(nome, tel), '2.00')
        outra = '5563981128125'
        self._indicacao(outra, self._pedido('Yasmine', '5563984195663'), '3.00')

        dados = self.client.get(self.url).data

        top = dados['por_indicador']
        self.assertEqual(top[0]['phone'], self.elisangela)
        self.assertEqual(top[0]['total_indicados'], 3)
        self.assertEqual(Decimal(top[0]['total_creditado']), Decimal('6.00'))
        self.assertEqual(top[1]['phone'], outra)

    def test_usa_o_nome_do_indicador_quando_ele_ja_comprou(self):
        """Telefone não diz nada ao dono. Nome diz."""
        self._pedido('Elisangela Souza', self.elisangela)
        self._indicacao(self.elisangela, self._pedido('Ana', '5563984301666'))

        dados = self.client.get(self.url).data

        self.assertEqual(dados['por_indicador'][0]['nome'], 'Elisangela Souza')

    def test_sem_indicacao_devolve_vazio_sem_quebrar(self):
        dados = self.client.get(self.url).data

        self.assertEqual(dados['indicacoes'], [])
        self.assertEqual(dados['por_indicador'], [])

    # ── dinheiro é do dono ──────────────────────────────────────────────

    def test_loja_de_outro_dono_e_recusada(self):
        """Telefone e histórico de compra de cliente. IDOR aqui é vazamento."""
        intruso = User.objects.create_user(username='intruso', password='x')
        self.client.force_authenticate(intruso)

        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_visitante_nao_ve_nada(self):
        self.client.force_authenticate(None)

        self.assertIn(self.client.get(self.url).status_code, (401, 403))

    def test_nao_vaza_indicacao_de_outra_loja(self):
        outro_dono = User.objects.create_user(username='dono2', password='x')
        outra = Store.objects.create(
            billing_exempt=True, name='Outra', slug='outra-loja-indica', owner=outro_dono,
            store_type='food', status='active', metadata={'cashback_enabled': True},
        )
        pedido_alheio = StoreOrder.objects.create(
            store=outra, customer_name='Cliente da Outra', customer_phone='5511999999999',
            subtotal=Decimal('50'), total=Decimal('50'),
            status='delivered', payment_status='paid',
        )
        StoreCashbackLot.objects.create(
            store=outra, phone='5511988888888', amount=Decimal('5'), remaining=Decimal('5'),
            origin=StoreCashbackLot.Origin.REFERRAL, order=pedido_alheio,
            expires_at=timezone.now() + timedelta(days=30),
        )

        dados = self.client.get(self.url).data

        self.assertEqual(dados['indicacoes'], [])
