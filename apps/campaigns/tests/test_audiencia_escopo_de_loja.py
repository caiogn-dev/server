"""A audiência tem que ser da LOJA da campanha, não de tudo que o dono acessa.

RELATADO PELO DONO em 29/ago/2026:

    "alguns segmentos nao funcionam direito, produtos estao vindo de TODAS AS
     LOJAS"

Ele tem acesso a DOZE lojas (várias de demonstração: kowa-burger, ei-pizza,
cachorrao-lanches...). O endpoint montava a audiência com
`accessible_store_ids(user)` — todas elas — e o estrago ia muito além do
seletor de produtos:

    perfis de compra    95 "compradores"  contra  59 reais
    inativos            21                contra   7 reais

Ou seja: quem comprou na Pastita entrava como cliente da Cê Saladas, e o
segmento "sumidos" prometia gente que nunca foi cliente daquela loja. Mandar
"sentimos sua falta" para quem nunca comprou ali é pior do que não mandar.

A REGRA: a loja vem do parâmetro `store`; sem ele, das lojas ligadas à conta
de WhatsApp da campanha. NUNCA "todas as lojas que o usuário enxerga".
"""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.stores.models import Store, StoreOrder, StoreProduct
from apps.whatsapp.models import WhatsAppAccount

User = get_user_model()


class EscopoDeLojaTests(TestCase):
    def setUp(self):
        self.dono = User.objects.create_user(username='dono', password='x')
        self.conta = WhatsAppAccount.objects.create(
            name='Cê', phone_number_id='PH1', waba_id='W1'
        )
        # A loja da campanha.
        self.loja = Store.objects.create(
            name='Cê Saladas', slug='ce-saladas', owner=self.dono,
            whatsapp_account=self.conta,
        )
        # Outra loja do MESMO dono, sem relação com esta conta de WhatsApp.
        self.outra = Store.objects.create(
            name='Kowa Burger', slug='kowa-burger', owner=self.dono,
        )

        StoreProduct.objects.create(
            store=self.loja, name='Salada Caesar', price=30, is_active=True
        )
        StoreProduct.objects.create(
            store=self.outra, name='X-Burger', price=25, is_active=True
        )

        self._pedido(self.loja, '556391110001', dias=1)
        # Mesma pessoa comprando na OUTRA loja: não pode contar aqui.
        for _ in range(6):
            self._pedido(self.outra, '556391110001', dias=1)
        # Cliente só da outra loja: não pode aparecer nesta audiência.
        self._pedido(self.outra, '556391119999', dias=1)

        self.client = APIClient()
        self.client.force_authenticate(self.dono)

    def _pedido(self, loja, telefone, dias, total=50):
        p = StoreOrder.objects.create(
            store=loja, customer_phone=telefone, customer_name='C',
            status='delivered', payment_status='paid',
            subtotal=total, delivery_fee=0, total=total,
        )
        StoreOrder.objects.filter(pk=p.pk).update(
            created_at=timezone.now() - timedelta(days=dias)
        )

    def test_produtos_sao_so_da_loja_pedida(self):
        r = self.client.get('/api/v1/campaigns/audiencia/opcoes/', {'store': 'ce-saladas'})
        nomes = {p['nome'] for p in r.data['produtos']}
        self.assertIn('Salada Caesar', nomes)
        self.assertNotIn('X-Burger', nomes)

    def test_produtos_sem_store_saem_da_conta_e_nao_de_todas_as_lojas(self):
        # O painel antigo não manda `store`. Mesmo assim não pode devolver o
        # catálogo das doze lojas.
        r = self.client.get('/api/v1/campaigns/audiencia/opcoes/',
                            {'account_id': str(self.conta.id)})
        nomes = {p['nome'] for p in r.data['produtos']}
        self.assertNotIn('X-Burger', nomes)

    def test_pedidos_de_outra_loja_nao_inflam_a_frequencia(self):
        # 1 pedido na Cê + 6 na Kowa. Somando tudo a pessoa vira VIP de uma
        # loja onde comprou uma vez só.
        r = self.client.get('/api/v1/campaigns/system-contacts/',
                            {'store': 'ce-saladas', 'account_id': str(self.conta.id)})
        pessoa = next(
            (c for c in r.data['results'] if c['phone'] == '556391110001'), None
        )
        self.assertIsNotNone(pessoa)
        self.assertEqual(pessoa['pedidos'], 1)
        self.assertEqual(pessoa['frequencia'], 'novo')

    def test_cliente_exclusivo_de_outra_loja_nao_entra_na_lista(self):
        """O vazamento também estava na LISTA, não só no perfil de compra.

        Os contatos vindos de pedido e de inscritos eram buscados em
        `accessible_store_ids(user)` — as doze lojas. Quem só comprou na Kowa
        Burger aparecia como contato da campanha da Cê Saladas e receberia a
        mensagem.
        """
        r = self.client.get('/api/v1/campaigns/system-contacts/',
                            {'store': 'ce-saladas'})
        telefones = {c['phone'] for c in r.data['results']}
        self.assertNotIn('556391119999', telefones)
        self.assertIn('556391110001', telefones)

    def test_inscrito_de_outra_loja_nao_entra_na_lista(self):
        from apps.marketing.models import Subscriber
        Subscriber.objects.create(
            store=self.outra, email='dakowa@x.com', phone='556391118888',
        )
        r = self.client.get('/api/v1/campaigns/system-contacts/',
                            {'store': 'ce-saladas'})
        telefones = {c['phone'] for c in r.data['results']}
        self.assertNotIn('556391118888', telefones)

    def test_filtro_de_vip_nao_traz_vip_de_outra_loja(self):
        r = self.client.get('/api/v1/campaigns/system-contacts/',
                            {'store': 'ce-saladas', 'frequencia': 'vip'})
        self.assertEqual(r.data['results'], [])

    def test_frase_da_tela_nomeia_o_produto_filtrado(self):
        """Regressão: o cabeçalho dizia "Todos os contatos" filtrando produto."""
        produto = StoreProduct.objects.get(store=self.loja, name='Salada Caesar')
        r = self.client.get('/api/v1/campaigns/system-contacts/', {
            'store': 'ce-saladas', 'produtos': str(produto.id),
        })
        self.assertIn('Salada Caesar', r.data['descricao'])
        self.assertNotEqual(r.data['descricao'], 'Todos os contatos')

    def test_frase_nao_nomeia_produto_de_outra_loja(self):
        # Pedir o id do produto alheio não pode revelar o nome dele.
        alheio = StoreProduct.objects.get(store=self.outra, name='X-Burger')
        r = self.client.get('/api/v1/campaigns/system-contacts/', {
            'store': 'ce-saladas', 'produtos': str(alheio.id),
        })
        self.assertNotIn('X-Burger', r.data['descricao'])

    def test_loja_de_outro_dono_e_recusada(self):
        estranho = User.objects.create_user(username='estranho', password='x')
        Store.objects.create(name='Alheia', slug='alheia', owner=estranho)

        r = self.client.get('/api/v1/campaigns/audiencia/opcoes/', {'store': 'alheia'})
        # Não pode vazar o catálogo alheio nem cair silenciosamente em "todas".
        self.assertIn(r.status_code, (403, 404))
