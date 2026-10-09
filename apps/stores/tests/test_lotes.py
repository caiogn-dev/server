"""
Lote de produção (Agrião, 09/10): um lote por prato por dia, impresso na etiqueta
e rastreável no painel.

Código: 3 primeiras letras do prato + dia de fabricação (ddmmaa) + ordem do prato
no dia na loja. Ex.: Estrogonofe, 1º prato de 09/10/26 → EST-09102601.
Reimprimir o mesmo prato no mesmo dia devolve o MESMO lote e soma as etiquetas.
"""
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.stores.models import Store, StoreLote, StoreProduct
from apps.stores.services.lotes import garantir_lotes, prefixo_do_prato

User = get_user_model()
HOJE = date(2026, 10, 9)
URL = '/api/v1/stores/lotes/'


class PrefixoTest(APITestCase):
    def test_tres_letras_sem_acento_em_maiuscula(self):
        self.assertEqual(prefixo_do_prato('Estrogonofe de Frango'), 'EST')
        self.assertEqual(prefixo_do_prato('Ácido Úmido'), 'ACI')
        self.assertEqual(prefixo_do_prato('Bobó'), 'BOB')
        self.assertEqual(prefixo_do_prato('X'), 'X')


class LotesTest(APITestCase):
    def setUp(self):
        self.dona = User.objects.create_user(username='dona-l', email='l@t.local', password='x')
        self.loja = Store.objects.create(name='Agrião', slug='agriao-l', owner=self.dona, status='active')
        self.estro = StoreProduct.objects.create(store=self.loja, name='Estrogonofe de Frango', slug='estro', price=Decimal('30'))
        self.esc1 = StoreProduct.objects.create(store=self.loja, name='Escondidinho de Frango', slug='esc-f', price=Decimal('30'))
        self.esc2 = StoreProduct.objects.create(store=self.loja, name='Escondidinho de Patinho', slug='esc-p', price=Decimal('30'))
        self.client.force_authenticate(self.dona)

    def test_um_lote_por_prato_por_dia_na_ordem_do_dia(self):
        cod = garantir_lotes(self.loja, [(self.estro.id, 10), (self.esc1.id, 5), (self.esc2.id, 3)], HOJE, 90)
        self.assertEqual(cod[str(self.estro.id)]['codigo'], 'EST-09102601')
        self.assertEqual(cod[str(self.esc1.id)]['codigo'], 'ESC-09102602')
        self.assertEqual(cod[str(self.esc2.id)]['codigo'], 'ESC-09102603')
        lote = StoreLote.objects.get(codigo='EST-09102601')
        self.assertEqual(lote.validade, HOJE + timedelta(days=90))
        self.assertEqual(lote.etiquetas, 10)

    def test_reimprimir_no_mesmo_dia_mantem_o_lote_e_soma(self):
        garantir_lotes(self.loja, [(self.estro.id, 10)], HOJE, 90)
        cod = garantir_lotes(self.loja, [(self.estro.id, 4)], HOJE, 90)
        self.assertEqual(cod[str(self.estro.id)]['codigo'], 'EST-09102601')
        self.assertEqual(StoreLote.objects.get(codigo='EST-09102601').etiquetas, 14)

    def test_outro_dia_e_outro_lote(self):
        garantir_lotes(self.loja, [(self.estro.id, 1)], HOJE, 90)
        cod = garantir_lotes(self.loja, [(self.estro.id, 1)], HOJE + timedelta(days=1), 90)
        self.assertEqual(cod[str(self.estro.id)]['codigo'], 'EST-10102601')

    def test_api_garante_e_lista_com_busca(self):
        with patch('apps.stores.services.lotes.hoje', return_value=HOJE):
            r = self.client.post(URL + 'garantir/', {'store': str(self.loja.id), 'validade_dias': 90,
                                                     'itens': [{'produto': str(self.estro.id), 'quantidade': 2}]}, format='json')
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.data['lotes'][str(self.estro.id)]['codigo'], 'EST-09102601')
        self.assertEqual(r.data['lotes'][str(self.estro.id)]['validade'], '2027-01-07')
        r = self.client.get(URL, {'store': self.loja.slug, 'q': 'est-0910'})
        self.assertEqual(r.status_code, 200)
        linhas = r.data.get('results', r.data)
        self.assertEqual([l['codigo'] for l in linhas], ['EST-09102601'])
        self.assertEqual(linhas[0]['produto_nome'], 'Estrogonofe de Frango')

    def test_outra_loja_nao_ve_nem_cria(self):
        intrusa = User.objects.create_user(username='intrusa', email='i@t.local', password='x')
        garantir_lotes(self.loja, [(self.estro.id, 1)], HOJE, 90)
        self.client.force_authenticate(intrusa)
        r = self.client.get(URL, {'store': self.loja.slug})
        self.assertEqual(len(r.data.get('results', r.data)), 0)
        r = self.client.post(URL + 'garantir/', {'store': str(self.loja.id), 'validade_dias': 90,
                                                 'itens': [{'produto': str(self.estro.id), 'quantidade': 1}]}, format='json')
        self.assertEqual(r.status_code, 404)
