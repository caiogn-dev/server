"""Reajuste de preço em massa — somar ou reduzir em R$ ou %, nos itens escolhidos.

Pedido do dono (06/10), visto no Prefiro ("Ajustes → Incrementar preços"):
hoje reajustar o cardápio é abrir produto por produto.

Regras (casos de exceção pensados junto):
- prévia não grava nada;
- tudo ou nada: preço que ficaria R$ 0 ou negativo trava o reajuste inteiro
  e diz quais itens;
- variantes com preço próprio seguem a mesma regra;
- avisa promoção que fica igual/acima do preço novo e "de" que fica abaixo;
- só produtos da loja (id de outra loja é ignorado);
- desfazer o último reajuste só reverte item que ninguém mexeu depois.
"""
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.stores.models import Store, StoreProduct
from apps.stores.models.product import StoreProductVariant

URL = '/api/v1/stores/products/reajuste-de-preco/'
URL_DESFAZER = '/api/v1/stores/products/reajuste-de-preco/desfazer/'


@pytest.fixture
def loja(db):
    dono = get_user_model().objects.create_user(username='dono-reaj', password='x')
    return Store.objects.create(owner=dono, name='Cê Reaj', slug='ce-reaj', status='active')


@pytest.fixture
def api(loja):
    c = APIClient()
    c.force_authenticate(loja.owner)
    return c


def _produto(loja, nome, preco, **extra):
    return StoreProduct.objects.create(store=loja, name=nome, slug=nome.lower().replace(' ', '-'),
                                       price=Decimal(preco), status='active', **extra)


def _reajustar(api, loja, produtos, operacao='acrescentar', modo='percentual', valor='10', previa=False):
    return api.post(URL, {
        'store': loja.slug, 'operacao': operacao, 'modo': modo, 'valor': valor,
        'produtos': [str(p.id) for p in produtos], 'previa': previa,
    }, format='json')


def _preco(p):
    p.refresh_from_db()
    return p.price


@pytest.mark.django_db
class TestReajuste:
    def test_acrescentar_percentual_arredonda_no_centavo(self, api, loja):
        p = _produto(loja, 'Salada', '36.99')
        r = _reajustar(api, loja, [p], valor='10')
        assert r.status_code == 200, r.content
        assert _preco(p) == Decimal('40.69')  # 36,99 × 1,10 = 40,689

    def test_reduzir_em_reais(self, api, loja):
        p = _produto(loja, 'Suco', '9.90')
        _reajustar(api, loja, [p], operacao='reduzir', modo='valor', valor='1.00')
        assert _preco(p) == Decimal('8.90')

    def test_previa_nao_grava_e_mostra_antes_e_depois(self, api, loja):
        p = _produto(loja, 'Salada', '40.00')
        r = _reajustar(api, loja, [p], valor='5', previa=True)
        assert _preco(p) == Decimal('40.00')
        [item] = r.json()['itens']
        assert (item['antes'], item['depois']) == ('40.00', '42.00')

    def test_variante_com_preco_proprio_acompanha(self, api, loja):
        p = _produto(loja, 'Molho', '5.00')
        v = StoreProductVariant.objects.create(product=p, name='Mostarda', price=Decimal('6.00'))
        _reajustar(api, loja, [p], modo='valor', valor='1')
        v.refresh_from_db()
        assert (_preco(p), v.price) == (Decimal('6.00'), Decimal('7.00'))

    def test_preco_que_ficaria_zero_trava_tudo_e_diz_qual(self, api, loja):
        barato = _produto(loja, 'Sachê', '0.50')
        caro = _produto(loja, 'Salada', '40.00')
        r = _reajustar(api, loja, [barato, caro], operacao='reduzir', modo='valor', valor='1')
        assert r.status_code == 400
        assert [x['nome'] for x in r.json()['recusados']] == ['Sachê']
        assert (_preco(barato), _preco(caro)) == (Decimal('0.50'), Decimal('40.00'))

    def test_avisa_promocao_que_fica_acima_do_preco_novo(self, api, loja):
        p = _produto(loja, 'Camarão', '48.99', promo_price=Decimal('36.74'), promo_weekday=0)
        r = _reajustar(api, loja, [p], operacao='reduzir', modo='percentual', valor='30', previa=True)
        [item] = r.json()['itens']
        assert any('promoção' in a for a in item['avisos'])

    def test_produto_de_outra_loja_e_ignorado(self, api, loja):
        dono2 = get_user_model().objects.create_user(username='outro-reaj', password='x')
        outra = Store.objects.create(owner=dono2, name='Outra', slug='outra-reaj', status='active')
        alheio = _produto(outra, 'Alheio', '10.00')
        r = _reajustar(api, loja, [alheio], valor='10')
        assert r.status_code == 400
        assert _preco(alheio) == Decimal('10.00')

    def test_loja_alheia_e_404(self, loja):
        intruso = get_user_model().objects.create_user(username='intruso-reaj', password='x')
        c = APIClient()
        c.force_authenticate(intruso)
        p = _produto(loja, 'Salada', '40.00')
        assert _reajustar(c, loja, [p]).status_code == 404

    @pytest.mark.parametrize('valor', ['0', '-5', 'abc', ''])
    def test_valor_invalido_responde_400(self, api, loja, valor):
        p = _produto(loja, 'Salada', '40.00')
        assert _reajustar(api, loja, [p], valor=valor).status_code == 400

    def test_reduzir_100_por_cento_e_recusado(self, api, loja):
        p = _produto(loja, 'Salada', '40.00')
        assert _reajustar(api, loja, [p], operacao='reduzir', valor='100').status_code == 400


@pytest.mark.django_db
class TestDesfazer:
    def test_desfaz_o_ultimo_reajuste(self, api, loja):
        p = _produto(loja, 'Salada', '40.00')
        _reajustar(api, loja, [p], valor='10')
        r = api.post(URL_DESFAZER, {'store': loja.slug}, format='json')
        assert r.status_code == 200, r.content
        assert _preco(p) == Decimal('40.00')

    def test_item_mexido_depois_nao_e_desfeito(self, api, loja):
        p = _produto(loja, 'Salada', '40.00')
        q = _produto(loja, 'Suco', '10.00')
        _reajustar(api, loja, [p, q], valor='10')
        StoreProduct.objects.filter(pk=q.pk).update(price=Decimal('12.50'))  # dono editou à mão
        r = api.post(URL_DESFAZER, {'store': loja.slug}, format='json')
        assert (_preco(p), _preco(q)) == (Decimal('40.00'), Decimal('12.50'))
        assert r.json()['mantidos'] == ['Suco']

    def test_sem_reajuste_para_desfazer_responde_400(self, api, loja):
        assert api.post(URL_DESFAZER, {'store': loja.slug}, format='json').status_code == 400
