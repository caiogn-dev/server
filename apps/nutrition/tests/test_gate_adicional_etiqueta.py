"""O módulo de nutrição só abre para loja com o adicional Etiqueta ANVISA.

Contratado OU grandfather (billing_exempt). O resto recebe 402 com um código
que o painel reconhece e troca por um estado de "bloqueado" com o botão de
contratar — nunca um erro cru. A etiqueta pública (QR impresso na embalagem)
fica fora do portão: etiqueta que já está na prateleira não pode sumir.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from apps.nutrition.models import ProductNutritionProfile
from apps.stores.models import Store, StoreProduct, StoreSubscription

ETIQUETA = 'etiqueta_anvisa'


class PortaoDoAdicionalTest(TestCase):
    def setUp(self):
        self.dono = get_user_model().objects.create_user(
            username='dono-gate', email='dono-gate@t.local', password='x')
        self.loja = Store.objects.create(name='Loja', slug='loja-gate', owner=self.dono)
        self.sub = StoreSubscription.objects.create(store=self.loja, plan='pro', status='active')
        self.produto = StoreProduct.objects.create(
            store=self.loja, name='Salada', slug='salada-gate', price=10)
        self.perfil = ProductNutritionProfile.objects.create(product=self.produto)
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {Token.objects.create(user=self.dono).key}')

    def _contratar(self, loja=None):
        StoreSubscription.objects.update_or_create(
            store=loja or self.loja, defaults={'plan': 'pro', 'adicionais': {ETIQUETA: {}}})

    def test_sem_adicional_402_com_mensagem_de_venda(self):
        r = self.client.get('/api/v1/nutrition/profiles/')
        self.assertEqual(r.status_code, 402)
        erro = r.json()['error']
        self.assertEqual(erro['code'], 'adicional_necessario')
        self.assertIn('Contrate o adicional Etiqueta ANVISA', erro['message'])
        self.assertEqual(erro['details']['adicional'], ETIQUETA)

    def test_sem_adicional_nao_calcula_nem_lista_ingredientes(self):
        self.assertEqual(self.client.post('/api/v1/nutrition/recipes/previa/', {'items': []},
                                          format='json').status_code, 402)
        self.assertEqual(self.client.get('/api/v1/nutrition/ingredients/',
                                         {'store': str(self.loja.id)}).status_code, 402)

    def test_contratado_abre(self):
        self._contratar()
        r = self.client.get('/api/v1/nutrition/profiles/')
        self.assertEqual(r.status_code, 200)

    def test_grandfather_abre_sem_contratar(self):
        self.loja.billing_exempt = True
        self.loja.save()
        r = self.client.get('/api/v1/nutrition/profiles/')
        self.assertEqual(r.status_code, 200)

    def test_loja_com_adicional_nao_empresta_para_a_outra_do_mesmo_dono(self):
        """Dono de duas lojas contrata numa só: a outra continua fechada."""
        outra = Store.objects.create(name='Outra', slug='outra-gate', owner=self.dono)
        StoreSubscription.objects.create(store=outra, plan='pro', adicionais={ETIQUETA: {}})
        produto_fechado = StoreProduct.objects.create(
            store=self.loja, name='Wrap', slug='wrap-gate', price=10)

        r = self.client.post('/api/v1/nutrition/recipes/',
                             {'product': str(produto_fechado.id), 'serving_size_g': 100},
                             format='json')
        self.assertEqual(r.status_code, 402)
        r = self.client.get('/api/v1/nutrition/ingredients/', {'store': str(self.loja.id)})
        self.assertEqual(r.status_code, 402)

        lista = self.client.get('/api/v1/nutrition/profiles/')
        self.assertEqual(lista.status_code, 200)
        ids = [p['id'] for p in lista.json().get('results', lista.json())]
        self.assertNotIn(str(self.perfil.id), ids)

    def test_etiqueta_publica_fica_fora_do_portao(self):
        r = APIClient().get(f'/api/v1/nutrition/public/{self.produto.id}/')
        self.assertNotEqual(r.status_code, 402)
