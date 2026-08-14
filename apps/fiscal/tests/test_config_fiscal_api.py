"""Fiscal: configurar a emissão pelo painel, sem shell do Django.

A config vive em store.metadata['fiscal'] e é opt-in por loja (decisão de
jun/2026: só ALGUMAS lojas emitem). Este endpoint é o que torna a feature
alcançável — hoje nenhuma das 13 lojas tem config porque não existe tela.

Regra de segurança: o token do provedor e a senha do certificado entram, mas
nunca voltam em claro numa resposta HTTP.
"""
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.stores.models import Store

User = get_user_model()


class ConfigFiscalApiTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username='owner-cfg', email='owner-cfg@test.com', password='x',
        )
        self.store = Store.objects.create(
            name='Loja Cfg', slug='loja-cfg', owner=self.owner, status='active',
        )
        self.client.force_authenticate(self.owner)
        # StoreViewSet vive em /stores/stores/ (router aninhado sob o prefixo
        # do app) — o painel usa exatamente este caminho.
        self.url = f'/api/v1/stores/stores/{self.store.slug}/fiscal-config/'

    def test_loja_sem_config_responde_desligada(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.data['habilitado'])

    def test_salvar_config_valida_liga_a_emissao(self):
        resp = self.client.patch(self.url, {
            'habilitado': True,
            'provider': 'focus',
            'ambiente': 'homologacao',
            'cnpj': '11.444.777/0001-61',
            'focus_token': 'tok-secreto',
            'serie': '1',
        }, format='json')
        self.assertEqual(resp.status_code, 200, resp.content)
        self.store.refresh_from_db()
        cfg = self.store.metadata['fiscal']
        self.assertTrue(cfg['habilitado'])
        self.assertEqual(cfg['cnpj'], '11444777000161')  # guarda limpo
        self.assertEqual(cfg['focus_token'], 'tok-secreto')

    def test_token_nunca_volta_em_claro(self):
        self.client.patch(self.url, {
            'habilitado': True, 'provider': 'focus', 'cnpj': '11444777000161',
            'focus_token': 'tok-secreto-do-cliente',
        }, format='json')
        resp = self.client.get(self.url)
        corpo = str(resp.content)
        self.assertNotIn('tok-secreto-do-cliente', corpo)
        self.assertTrue(resp.data['focus_token_configurado'])

    def test_patch_sem_token_preserva_o_token_ja_salvo(self):
        """Editar a série não pode apagar o token que a tela nunca mostrou."""
        self.client.patch(self.url, {
            'habilitado': True, 'provider': 'focus', 'cnpj': '11444777000161',
            'focus_token': 'tok-original',
        }, format='json')
        self.client.patch(self.url, {'serie': '2'}, format='json')
        self.store.refresh_from_db()
        self.assertEqual(self.store.metadata['fiscal']['focus_token'], 'tok-original')
        self.assertEqual(self.store.metadata['fiscal']['serie'], '2')

    def test_cnpj_invalido_e_recusado(self):
        resp = self.client.patch(self.url, {
            'habilitado': True, 'provider': 'focus', 'cnpj': '11.111.111/1111-11',
            'focus_token': 'tok',
        }, format='json')
        self.assertEqual(resp.status_code, 400)
        self.assertIn('cnpj', resp.data['error']['details'])

    def test_ligar_sem_token_do_provedor_e_recusado(self):
        """Ligar a emissão sem credencial só produziria erro no primeiro pedido."""
        resp = self.client.patch(self.url, {
            'habilitado': True, 'provider': 'focus', 'cnpj': '11444777000161',
        }, format='json')
        self.assertEqual(resp.status_code, 400)

    def test_config_desligada_nao_exige_credencial(self):
        resp = self.client.patch(self.url, {'habilitado': False}, format='json')
        self.assertEqual(resp.status_code, 200, resp.content)

    def test_outra_loja_nao_enxerga_a_config(self):
        estranho = User.objects.create_user(
            username='estranho', email='estranho@test.com', password='x',
        )
        self.client.force_authenticate(estranho)
        self.assertIn(self.client.get(self.url).status_code, (403, 404))
