"""Painel → "Minhas marcas": o dono escolhe quais lojas dele aparecem juntas
na faixa "Conheça nossas outras marcas", em que ordem e com que link.

Antes (até 20/11) o grupo só existia no metadata, montado pelo shell.
"""
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from rest_framework.test import APITestCase

from apps.stores.models import Store
from apps.stores.services.outras_marcas import outras_marcas

User = get_user_model()
URL = '/api/v1/stores/minhas-marcas/'


class MinhasMarcasTest(APITestCase):
    def setUp(self):
        cache.clear()
        self.dono = User.objects.create_user(username='dono', email='d@t.com', password='x')
        self.outro = User.objects.create_user(username='outro', email='o@t.com', password='x')
        self.ce = self._loja('ce', grupo='familia', ordem=1)
        self.agriao = self._loja('agriao', grupo='familia', ordem=2, link='https://agriao.exemplo.com/')
        self.kero = self._loja('kero')
        self.alheia = self._loja('alheia', dono=self.outro)
        self.client.force_authenticate(self.dono)
        avisa = mock.patch('apps.stores.services.minhas_marcas._avisar_cardapio')
        self.avisar = avisa.start()
        self.addCleanup(avisa.stop)

    def _loja(self, slug, grupo=None, ordem=0, link=None, dono=None):
        meta = {'outra_chave': 'fica'}
        if grupo:
            meta.update(grupo_de_marcas=grupo, ordem_no_grupo=ordem)
        if link:
            meta['link_da_marca'] = link
        return Store.objects.create(name=slug.title(), slug=slug, owner=dono or self.dono,
                                    status='active', metadata=meta)

    def test_lista_so_as_lojas_do_dono_com_o_grupo_atual(self):
        r = self.client.get(URL, {'store': 'ce'})
        self.assertEqual(r.status_code, 200)
        marcas = r.json()['marcas']
        self.assertEqual([m['slug'] for m in marcas], ['ce', 'agriao', 'kero'])
        self.assertEqual([m['no_grupo'] for m in marcas], [True, True, False])
        self.assertEqual(marcas[1]['link'], 'https://agriao.exemplo.com/')

    def test_salvar_monta_o_grupo_na_ordem_escolhida(self):
        r = self.client.put(URL + '?store=ce', {'marcas': [
            {'slug': 'kero', 'no_grupo': True, 'link': ''},
            {'slug': 'ce', 'no_grupo': True, 'link': ''},
            {'slug': 'agriao', 'no_grupo': False, 'link': ''},
        ]}, format='json')
        self.assertEqual(r.status_code, 200, r.content)
        for loja in (self.ce, self.agriao, self.kero):
            loja.refresh_from_db()
        self.assertEqual([m['slug'] for m in outras_marcas(self.ce)], ['kero'])
        self.assertEqual(outras_marcas(self.agriao), [])
        self.assertNotIn('grupo_de_marcas', self.agriao.metadata)
        self.assertNotIn('link_da_marca', self.agriao.metadata)
        self.assertEqual(self.kero.metadata['outra_chave'], 'fica')
        avisadas = {c.args[0] for c in self.avisar.call_args_list}
        self.assertEqual(avisadas, {'ce', 'agriao', 'kero'})

    def test_loja_de_outro_dono_nao_entra(self):
        r = self.client.put(URL + '?store=ce', {'marcas': [
            {'slug': 'ce', 'no_grupo': True}, {'slug': 'alheia', 'no_grupo': True},
        ]}, format='json')
        self.assertEqual(r.status_code, 400)
        self.alheia.refresh_from_db()
        self.assertNotIn('grupo_de_marcas', self.alheia.metadata)

    def test_link_invalido_e_recusado(self):
        r = self.client.put(URL + '?store=ce', {'marcas': [
            {'slug': 'ce', 'no_grupo': True}, {'slug': 'agriao', 'no_grupo': True, 'link': 'javascript:alert(1)'},
        ]}, format='json')
        self.assertEqual(r.status_code, 400)

    def test_quem_nao_e_dono_nao_mexe(self):
        self.ce.staff.add(self.outro)
        self.client.force_authenticate(self.outro)
        self.assertEqual(self.client.get(URL, {'store': 'ce'}).status_code, 403)
        r = self.client.put(URL + '?store=ce', {'marcas': [{'slug': 'ce', 'no_grupo': True}]}, format='json')
        self.assertEqual(r.status_code, 403)
