"""Da nota de teste para a nota de verdade.

19/set, primeira NF-e autorizada (homologação, pedido IVO2609177724). Três
defeitos apareceram de uma vez, e cada um impedia a nota REAL:

1. A Focus devolve a chave como "NFe" + 44 dígitos. A coluna tem 44: a
   consulta explodia em 500, o painel engolia o erro e o bloco da nota sumia.
2. `caminho_danfe` vem relativo ("/arquivos/..."): o link abria no domínio
   do painel.
3. A nota de homologação autorizada contava como "já emitida" — ao virar a
   loja para produção, emitir devolvia a nota de teste em vez de emitir.
"""
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.fiscal.models import FiscalDocument
from apps.fiscal.providers.base import EmitResult
from apps.fiscal.providers.focus import FocusProvider
from apps.stores.models import Store, StoreCategory, StoreOrder, StoreOrderItem, StoreProduct

User = get_user_model()

CHAVE = '17260955599700000136550020000000011234567890'

FISCAL_CFG = {
    'provider': 'focus',
    'ambiente': 'homologacao',
    'focus_token': 'tok-teste',
    'cnpj': '11444777000161',
    'inscricao_estadual': '295724145',
    'serie': '2',
    'habilitado': True,
    'uf': 'TO',
}


class RespostaDaFocusTests(APITestCase):
    def test_chave_com_prefixo_nfe_vira_os_44_digitos(self):
        provider = FocusProvider({'ambiente': 'homologacao'})
        result = provider._to_result({'status': 'autorizado', 'chave_nfe': f'NFe{CHAVE}'})
        self.assertEqual(result.chave_acesso, CHAVE)

    def test_caminho_relativo_do_danfe_vira_link_do_ambiente(self):
        homolog = FocusProvider({'ambiente': 'homologacao'})._to_result({
            'status': 'autorizado',
            'caminho_danfe': '/arquivos_development/nfe/danfe.pdf',
            'caminho_xml_nota_fiscal': '/arquivos_development/nfe/nota.xml',
        })
        self.assertEqual(
            homolog.danfe_url,
            'https://homologacao.focusnfe.com.br/arquivos_development/nfe/danfe.pdf',
        )
        self.assertEqual(
            homolog.xml_url,
            'https://homologacao.focusnfe.com.br/arquivos_development/nfe/nota.xml',
        )
        producao = FocusProvider({'ambiente': 'producao'})._to_result({
            'status': 'autorizado', 'caminho_danfe': '/arquivos/nfe/danfe.pdf',
        })
        self.assertEqual(producao.danfe_url, 'https://api.focusnfe.com.br/arquivos/nfe/danfe.pdf')

    def test_link_absoluto_passa_intacto(self):
        url = 'https://s3.amazonaws.com/focusnfe/danfe.pdf'
        result = FocusProvider({'ambiente': 'producao'})._to_result({
            'status': 'autorizado', 'caminho_danfe': url,
        })
        self.assertEqual(result.danfe_url, url)


class NotaDeTesteNaoBloqueiaNotaRealTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username='owner-amb', email='owner-amb@test.com', password='x',
        )
        self.store = Store.objects.create(
            name='Loja Amb', slug='loja-amb', owner=self.owner, status='active',
            metadata={'fiscal': dict(FISCAL_CFG)},
        )
        category = StoreCategory.objects.create(store=self.store, name='Geral', slug='geral')
        product = StoreProduct.objects.create(
            store=self.store, name='Congelado', price=500, track_stock=False,
            category=category, sku='C1',
        )
        self.order = StoreOrder.objects.create(
            store=self.store, customer_name='PULVERIZA DRONES LTDA',
            customer_phone='63992424213',
            subtotal=Decimal('500.00'), total=Decimal('500.00'),
            payment_method='pix', delivery_method='pickup',
            status='confirmed', payment_status='paid',
            delivery_address={
                'street': 'Q ACSE 80, Avenida LO 19', 'number': 'SN',
                'neighborhood': 'Plano Diretor Sul', 'city': 'Palmas',
                'state': 'TO', 'zip_code': '77023008',
            },
            metadata={'cpf_nota': '51162926000203', 'ie_nota': '295504641'},
        )
        StoreOrderItem.objects.create(
            order=self.order, product=product, product_name='Congelado',
            sku='C1', unit_price=500, quantity=1, subtotal=500,
        )
        self.client.force_authenticate(self.owner)
        base = f'/api/v1/stores/{self.store.slug}/orders/{self.order.id}'
        self.url_emitir = f'{base}/emit_nfce/'
        self.url_consultar = f'{base}/nfce/'

    def _virar_producao(self):
        self.store.metadata = {'fiscal': {**FISCAL_CFG, 'ambiente': 'producao'}}
        self.store.save(update_fields=['metadata'])

    @patch('apps.fiscal.services.FocusProvider.emit_nfe')
    def test_nota_nasce_marcada_com_o_ambiente(self, mock_emit):
        mock_emit.return_value = EmitResult(status='authorized', chave_acesso=CHAVE, numero='1')
        self.client.post(self.url_emitir, {'modelo': '55'}, format='json')
        self.assertEqual(FiscalDocument.objects.get(order=self.order).ambiente, 'homologacao')

    @patch('apps.fiscal.services.FocusProvider.emit_nfe')
    def test_producao_emite_mesmo_com_nota_de_teste_autorizada(self, mock_emit):
        FiscalDocument.objects.create(
            store=self.store, order=self.order, provider='focus', modelo='55',
            status='authorized', ref=f'nfe-{self.order.id}', ambiente='homologacao',
            chave_acesso=CHAVE, numero='1',
        )
        self._virar_producao()
        mock_emit.return_value = EmitResult(status='authorized', chave_acesso='5' * 44, numero='1')

        resp = self.client.post(self.url_emitir, {'modelo': '55'}, format='json')

        self.assertEqual(resp.status_code, 201, resp.content)
        mock_emit.assert_called_once()
        real = FiscalDocument.objects.get(order=self.order, ambiente='producao')
        self.assertEqual(real.status, 'authorized')
        self.assertEqual(real.ref, f'nfe-{self.order.id}-r2')

    @patch('apps.fiscal.services.FocusProvider.emit_nfe')
    def test_producao_nao_duplica_a_nota_real(self, mock_emit):
        self._virar_producao()
        mock_emit.return_value = EmitResult(status='authorized', chave_acesso='5' * 44, numero='1')
        self.client.post(self.url_emitir, {'modelo': '55'}, format='json')
        self.client.post(self.url_emitir, {'modelo': '55'}, format='json')
        mock_emit.assert_called_once()

    def test_consulta_em_producao_nao_mostra_nota_de_teste(self):
        """Nota de homologação na lista faria o painel dizer "Nota emitida" e
        esconder o botão da nota real."""
        FiscalDocument.objects.create(
            store=self.store, order=self.order, provider='focus', modelo='55',
            status='authorized', ref=f'nfe-{self.order.id}', ambiente='homologacao',
        )
        self._virar_producao()
        resp = self.client.get(self.url_consultar)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['documentos'], [])

    @patch('apps.fiscal.providers.focus.FocusProvider.consult')
    def test_consulta_que_autoriza_com_chave_longa_nao_da_500(self, mock_consult):
        FiscalDocument.objects.create(
            store=self.store, order=self.order, provider='focus', modelo='55',
            status='pending', ref=f'nfe-{self.order.id}', ambiente='homologacao',
        )
        mock_consult.side_effect = lambda **kw: FocusProvider(FISCAL_CFG)._to_result(
            {'status': 'autorizado', 'chave_nfe': f'NFe{CHAVE}', 'numero': '1'}
        )
        resp = self.client.get(self.url_consultar)
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.data['documentos'][0]['status'], 'authorized')
        self.assertEqual(resp.data['documentos'][0]['chave_acesso'], CHAVE)
