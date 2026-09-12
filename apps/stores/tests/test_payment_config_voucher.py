from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.stores.api.views.storefront_views import build_store_payment_config
from apps.stores.models import Store, StorePaymentGateway

User = get_user_model()


class PaymentConfigVoucherTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username='o-cfg', password='x', email='owner-cfg@real.com',
        )
        self.store = Store.objects.create(
            name='Loja Cfg', slug='loja-cfg', owner=self.owner, status='active',
        )

    def _liga_pagarme(self, **kwargs):
        dados = dict(
            store=self.store, name='Pagar.me', gateway_type='pagarme',
            api_key='sk_test_x', public_key='pk_test_y', is_enabled=True,
            is_sandbox=True, configuration={'voucher_brands': ['vr', 'sodexo']},
        )
        dados.update(kwargs)
        return StorePaymentGateway.objects.create(**dados)

    def test_loja_sem_pagarme_nao_ve_voucher(self):
        config = build_store_payment_config(self.store)
        self.assertNotIn('voucher', config['enabled_methods'])
        self.assertEqual(config.get('pagarme', {}).get('public_key', ''), '')

    def test_loja_com_pagarme_ve_voucher_e_as_bandeiras(self):
        self._liga_pagarme()
        config = build_store_payment_config(self.store)
        self.assertIn('voucher', config['enabled_methods'])
        self.assertEqual(config['pagarme']['public_key'], 'pk_test_y')
        self.assertTrue(config['pagarme']['is_sandbox'])
        # O cardapio recebe rotulo pronto: ele nao tem o direito de saber que
        # 'vr' se escreve 'VR Beneficios'.
        marcas = config['pagarme']['brands']
        self.assertEqual([m['value'] for m in marcas], ['vr', 'sodexo'])
        # A Sodexo virou Pluxee em 2024 — o cartao do cliente diz Pluxee.
        self.assertEqual([m['label'] for m in marcas], ['VR Benefícios', 'Pluxee'])
        # E a logo viaja junto, para o cardapio nao ter arquivo proprio.
        for m in marcas:
            self.assertIn('logo', m)
        # E recebe a URL de tokenizacao, em vez de carrega-la fixa no JS.
        self.assertTrue(config['pagarme']['tokens_url'].endswith('/tokens'))

    def test_o_catalogo_e_servido_ao_painel(self):
        """O painel monta os toggles a partir DESTE endpoint. Sem ele, a lista
        de bandeiras viraria um array hardcoded no .tsx — a terceira copia."""
        self.client.force_authenticate(user=self.owner)
        r = self.client.get('/api/v1/stores/payments/gateways/bandeiras-de-vale/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(
            [b['value'] for b in r.data['brands']], ['vr', 'sodexo', 'ticket'],
        )
        self.assertTrue(all(b['label'] for b in r.data['brands']))
        self.assertTrue(all('logo' in b for b in r.data['brands']))

    def test_gateway_desabilitado_nao_liga_voucher(self):
        self._liga_pagarme(is_enabled=False)
        config = build_store_payment_config(self.store)
        self.assertNotIn('voucher', config['enabled_methods'])

    def test_sem_chave_publica_nao_liga_voucher(self):
        """Sem public key o browser nao tokeniza. Anunciar o metodo seria
        oferecer um caminho que morre no clique — o mesmo erro do
        `free_delivery_threshold`, que anunciava frete gratis que o backend
        nunca aplicava."""
        self._liga_pagarme(public_key='')
        config = build_store_payment_config(self.store)
        self.assertNotIn('voucher', config['enabled_methods'])

    def test_sem_bandeira_habilitada_nao_liga_voucher(self):
        self._liga_pagarme(configuration={'voucher_brands': []})
        config = build_store_payment_config(self.store)
        self.assertNotIn('voucher', config['enabled_methods'])

    def test_a_secret_key_nunca_sai_na_config(self):
        """Esta config vai inteira para o browser."""
        self._liga_pagarme()
        self.assertNotIn('sk_test_x', str(build_store_payment_config(self.store)))

    def test_pix_e_cartao_continuam_iguais(self):
        """O Mercado Pago nao pode mudar de comportamento por causa do voucher."""
        antes = build_store_payment_config(self.store)
        self._liga_pagarme()
        depois = build_store_payment_config(self.store)
        self.assertEqual(antes['mercado_pago'], depois['mercado_pago'])
        self.assertEqual(
            list(antes['enabled_methods']),
            [m for m in depois['enabled_methods'] if m != 'voucher'],
        )
