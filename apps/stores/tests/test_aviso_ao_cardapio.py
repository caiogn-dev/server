"""Mudou o catálogo → o cardápio é avisado na hora.

Antes, preço/destaque/promoção levavam ~3 min para aparecer: o server2 apagava
o próprio cache, mas o cardapidex-web (página pré-gerada + cache em memória) e
a Cloudflare só se atualizavam quando o prazo deles vencia E alguém visitava.

Agora todo save/delete de produto, variação, tipo, categoria, combo ou loja
agenda (depois do commit) um aviso ao cardapidex-web, que refaz a página da
loja. Vários saves seguidos viram UM aviso.
"""
from decimal import Decimal
from unittest.mock import MagicMock, patch

import requests
from celery.exceptions import Retry
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings

from apps.stores.models import (
    Store,
    StoreCategory,
    StoreCombo,
    StoreProduct,
    StoreProductType,
    StoreProductVariant,
)
from apps.stores.services import aviso_ao_cardapio
from apps.stores.tasks import revalidar_cardapio

User = get_user_model()
LOCMEM = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}}


@override_settings(CACHES=LOCMEM)
class AvisoAoCardapioTests(TestCase):
    def setUp(self):
        cache.clear()
        self.owner = User.objects.create_user(username='aviso-dono', email='aviso@x.com', password='x')
        self.loja = Store.objects.create(
            billing_exempt=True, name='Loja Aviso', slug='loja-aviso', owner=self.owner, status='active',
        )
        self.categoria = StoreCategory.objects.create(store=self.loja, name='Saladas', slug='saladas')
        self.produto = StoreProduct.objects.create(
            store=self.loja, category=self.categoria, name='Caesar', price=Decimal('30.00'),
        )
        cache.clear()  # os saves do setUp não contam

    def _salvar(self, fazer):
        with patch.object(aviso_ao_cardapio.revalidar_cardapio, 'apply_async') as tarefa:
            with self.captureOnCommitCallbacks(execute=True):
                fazer()
        return tarefa

    def test_mudar_preco_avisa_o_cardapio_da_loja(self):
        def mudar():
            self.produto.price = Decimal('25.00')
            self.produto.save()
        tarefa = self._salvar(mudar)
        tarefa.assert_called_once()
        self.assertEqual(tarefa.call_args.kwargs['args'], ['loja-aviso'])

    def test_por_em_destaque_avisa(self):
        def destacar():
            self.produto.featured = True
            self.produto.save()
        self._salvar(destacar).assert_called_once()

    def test_excluir_produto_avisa(self):
        self._salvar(self.produto.delete).assert_called_once()

    def test_categoria_combo_variacao_tipo_e_loja_avisam(self):
        casos = {
            'categoria': lambda: self.categoria.save(),
            'combo': lambda: StoreCombo.objects.create(store=self.loja, name='Combo', slug='combo', price=Decimal('40.00')),
            'variacao': lambda: StoreProductVariant.objects.create(
                product=self.produto, name='Grande', price=Decimal('35.00'),
            ),
            'tipo': lambda: StoreProductType.objects.create(store=self.loja, name='Bebida', slug='bebida'),
            'loja': lambda: self.loja.save(),
        }
        for nome, fazer in casos.items():
            with self.subTest(nome):
                cache.clear()
                self._salvar(fazer).assert_called_once()

    def test_excluir_combo_avisa(self):
        combo = StoreCombo.objects.create(store=self.loja, name='Combo X', slug='combo-x', price=Decimal('40.00'))
        cache.clear()
        self._salvar(combo.delete).assert_called_once()

    def test_varios_saves_seguidos_viram_um_aviso_so(self):
        def editar_cardapio_inteiro():
            for preco in ('20.00', '21.00', '22.00'):
                self.produto.price = Decimal(preco)
                self.produto.save()
            self.categoria.save()
        tarefa = self._salvar(editar_cardapio_inteiro)
        self.assertEqual(tarefa.call_count, 1)

    def test_aviso_espera_o_commit(self):
        # Sem commit (transação desfeita) o cardápio não pode ser refeito com
        # dado que nunca existiu.
        with patch.object(aviso_ao_cardapio.revalidar_cardapio, 'apply_async') as tarefa:
            with self.captureOnCommitCallbacks(execute=False):
                self.produto.price = Decimal('1.00')
                self.produto.save()
        tarefa.assert_not_called()


@override_settings(
    CACHES=LOCMEM,
    STOREFRONT_INTERNAL_URL='http://web-teste:3010',
    STOREFRONT_REVALIDATE_SECRET='segredo-teste',
)
class TarefaRevalidarCardapioTests(TestCase):
    def setUp(self):
        cache.clear()

    def _resposta(self, status):
        r = MagicMock(status_code=status)
        r.ok = status < 400
        return r

    def test_chama_o_cardapio_com_o_segredo(self):
        with patch('apps.stores.tasks.requests.post', return_value=self._resposta(200)) as post:
            revalidar_cardapio('loja-aviso')
        post.assert_called_once()
        self.assertEqual(post.call_args.args[0], 'http://web-teste:3010/api/revalidar')
        self.assertEqual(post.call_args.kwargs['json'], {'slug': 'loja-aviso'})
        self.assertEqual(post.call_args.kwargs['headers']['x-revalidar-segredo'], 'segredo-teste')

    def test_apaga_o_catalogo_cacheado_antes_de_avisar(self):
        # Uma leitura que começou ANTES do commit pode ter regravado o catálogo
        # velho depois do delete do signal. Se o web refizer a página em cima
        # disso, o preço antigo volta por 5 min.
        cache.set('catalog:loja-aviso', {'velho': True}, 300)
        with patch('apps.stores.tasks.requests.post', return_value=self._resposta(200)):
            revalidar_cardapio('loja-aviso')
        self.assertIsNone(cache.get('catalog:loja-aviso'))

    @override_settings(STOREFRONT_REVALIDATE_SECRET='')
    def test_sem_segredo_nao_chama(self):
        with patch('apps.stores.tasks.requests.post') as post:
            revalidar_cardapio('loja-aviso')
        post.assert_not_called()

    def test_cardapio_fora_do_ar_tenta_de_novo(self):
        # Deploy do web reinicia o processo: alguns segundos fora não podem
        # perder o aviso. Depois das tentativas, o prazo de 60 s cobre.
        with patch('apps.stores.tasks.requests.post', side_effect=requests.ConnectionError('fora')):
            with self.assertRaises(Retry):
                revalidar_cardapio.apply(args=['loja-aviso'])
