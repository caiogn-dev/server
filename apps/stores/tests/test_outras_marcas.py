"""Faixa "Conheça nossas outras marcas" no cardápio.

O grupo é explícito (`metadata.grupo_de_marcas`), não "todas as lojas do dono":
o mesmo dono pode ter loja que não faz parte da família de marcas.
"""
from django.contrib.auth import get_user_model
from django.core.cache import cache
from rest_framework.test import APITestCase

from apps.stores.models import Store
from apps.stores.services.outras_marcas import outras_marcas

User = get_user_model()


class OutrasMarcasTest(APITestCase):
    def setUp(self):
        cache.clear()
        self.dono = User.objects.create_user(username='dono', email='d@t.com', password='x')
        self.ce = self._loja('ce', grupo='familia', ordem=1)
        self.agriao = self._loja('agriao', grupo='familia', ordem=2,
                                 link='https://agriao.exemplo.com/')
        self.pastita = self._loja('pastita', grupo='familia', ordem=3)
        self.kero = self._loja('kero', grupo=None)

    def _loja(self, slug, grupo, ordem=0, link=None, dono=None, status='active'):
        meta = {}
        if grupo:
            meta['grupo_de_marcas'] = grupo
            meta['ordem_no_grupo'] = ordem
        if link:
            meta['link_da_marca'] = link
        return Store.objects.create(name=slug.title(), slug=slug, owner=dono or self.dono,
                                    status=status, metadata=meta)

    def test_lista_as_outras_marcas_do_grupo_na_ordem(self):
        marcas = outras_marcas(self.ce)
        self.assertEqual([m['slug'] for m in marcas], ['agriao', 'pastita'])

    def test_link_externo_vence_o_cardapio(self):
        marcas = {m['slug']: m for m in outras_marcas(self.ce)}
        self.assertEqual(marcas['agriao']['url'], 'https://agriao.exemplo.com/')
        self.assertEqual(marcas['pastita']['url'], '/pastita')

    def test_loja_sem_grupo_nao_tem_faixa(self):
        self.assertEqual(outras_marcas(self.kero), [])

    def test_nao_mistura_dono_diferente_nem_loja_inativa(self):
        outro = User.objects.create_user(username='outro', email='o@t.com', password='x')
        self._loja('intrusa', grupo='familia', dono=outro)
        self._loja('fechada', grupo='familia', status='inactive')
        slugs = [m['slug'] for m in outras_marcas(self.ce)]
        self.assertNotIn('intrusa', slugs)
        self.assertNotIn('fechada', slugs)

    def test_link_que_nao_e_http_e_ignorado(self):
        self.agriao.metadata['link_da_marca'] = 'javascript:alert(1)'
        self.agriao.save()
        marcas = {m['slug']: m for m in outras_marcas(self.ce)}
        self.assertEqual(marcas['agriao']['url'], '/agriao')

    def test_catalogo_publico_traz_a_faixa(self):
        resp = self.client.get('/api/v1/stores/ce/catalog/')
        self.assertEqual(resp.status_code, 200, resp.content)
        marcas = resp.json()['store']['outras_marcas']
        self.assertEqual([m['slug'] for m in marcas], ['agriao', 'pastita'])
        self.assertEqual(set(marcas[0]), {'slug', 'nome', 'logo_url', 'url'})
