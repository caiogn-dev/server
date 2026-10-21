"""
Do admin do Prefiro: "Melhorar com IA" na descrição, sugestão de combos pelo
que sai junto, e produto salvo como rascunho.
"""
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.stores.models import StoreOrder, StoreOrderItem, StoreProduct
from apps.stores.services.ai_insights import LLMIndisponivel
from apps.stores.services.descricao_com_ia import IaForaDoAr, SemSugestao, melhorar_descricao
from apps.stores.services.sugestao_de_combos import sugestao_de_combos
from apps.stores.tests.factories import make_store

pytestmark = pytest.mark.django_db

LLM = 'apps.stores.services.ai_insights._llm_text'


@pytest.fixture
def loja():
    return make_store()


@pytest.fixture
def api(loja):
    c = APIClient()
    c.force_authenticate(loja.owner)
    return c


def _produto(loja, nome, preco='20', **extra):
    return StoreProduct.objects.create(store=loja, name=nome, slug=nome.lower().replace(' ', '-'),
                                       price=Decimal(preco), status=StoreProduct.ProductStatus.ACTIVE,
                                       track_stock=False, **extra)


class TestMelhorarDescricao:
    def test_devolve_sugestao_cortada_sem_gravar(self):
        longa = 'folhas ' * 120
        with patch(LLM, return_value='{"descricao": "%s", "descricao_curta": "Salada de folhas."}' % longa):
            r = melhorar_descricao('Salada Verde', 'alface e rúcula', 'Saladas')
        assert len(r['descricao']) <= 401 and r['descricao'].endswith('…')
        assert r['descricao_curta'] == 'Salada de folhas.'

    def test_prompt_leva_os_dados_do_produto(self):
        with patch(LLM, return_value='{"descricao": "ok"}') as llm:
            melhorar_descricao('Bowl de Frango', 'frango grelhado', 'Bowls')
        prompt = llm.call_args[0][0]
        assert 'Bowl de Frango' in prompt and 'frango grelhado' in prompt and 'NÃO invente' in prompt

    def test_sem_nome_nao_chama_a_ia(self):
        with patch(LLM) as llm, pytest.raises(SemSugestao):
            melhorar_descricao('  ')
        llm.assert_not_called()

    def test_ia_fora_do_ar(self):
        with patch(LLM, side_effect=LLMIndisponivel('todos caíram')), pytest.raises(IaForaDoAr):
            melhorar_descricao('Salada')

    def test_api(self, api, loja):
        url = f'/api/v1/stores/{loja.slug}/produtos/melhorar-descricao/'
        with patch(LLM, return_value='{"descricao": "Folhas e frango.", "descricao_curta": "Leve."}'):
            r = api.post(url, {'nome': 'Salada'}, format='json')
        assert r.status_code == 200 and r.data['descricao'] == 'Folhas e frango.'
        assert api.post(url, {'nome': ''}, format='json').status_code == 400
        with patch(LLM, side_effect=LLMIndisponivel('x')):
            assert api.post(url, {'nome': 'Salada'}, format='json').status_code == 503

    def test_api_de_outra_loja_e_404(self, loja):
        from apps.core.models import User
        outro = APIClient()
        outro.force_authenticate(User.objects.create_user(username='intruso-ia', password='x'))
        with patch(LLM) as llm:
            r = outro.post(f'/api/v1/stores/{loja.slug}/produtos/melhorar-descricao/', {'nome': 'X'}, format='json')
        assert r.status_code == 404
        llm.assert_not_called()


def _pedido(loja, produtos, status='delivered', dias=1):
    pedido = StoreOrder.objects.create(store=loja, customer_name='C', customer_phone='5563900000000',
                                       subtotal=Decimal('10'), total=Decimal('10'), status=status)
    StoreOrder.objects.filter(pk=pedido.pk).update(created_at=timezone.now() - timedelta(days=dias))
    for p in produtos:
        StoreOrderItem.objects.create(order=pedido, product=p, product_name=p.name, quantity=1,
                                      unit_price=p.price, subtotal=p.price)
    return pedido


class TestSugestaoDeCombos:
    def test_par_frequente_vira_sugestao_com_desconto(self, loja):
        salada, suco, bolo = _produto(loja, 'Salada', '30'), _produto(loja, 'Suco', '10'), _produto(loja, 'Bolo', '15')
        for _ in range(4):
            _pedido(loja, [salada, suco])
        for _ in range(2):
            _pedido(loja, [salada, bolo])  # abaixo do mínimo
        _pedido(loja, [salada, suco], status='cancelled')
        _pedido(loja, [salada, suco], dias=90)  # fora da janela
        [s] = sugestao_de_combos(loja)
        assert {p['nome'] for p in s['produtos']} == {'Salada', 'Suco'}
        assert s['pedidos_juntos'] == 4 and s['preco_somado'] == 40.0 and s['preco_sugerido'] == 36.0

    def test_produto_desativado_ou_ingrediente_fica_de_fora(self, loja):
        salada, suco = _produto(loja, 'Salada'), _produto(loja, 'Suco')
        queijo = _produto(loja, 'Queijo', tags=['ingrediente'])
        for _ in range(3):
            _pedido(loja, [salada, suco, queijo])
        suco.status = StoreProduct.ProductStatus.INACTIVE
        suco.save(update_fields=['status'])
        assert sugestao_de_combos(loja) == []

    def test_api(self, api, loja):
        r = api.get(f'/api/v1/stores/{loja.slug}/sugestao-de-combos/')
        assert r.status_code == 200 and r.data == {'sugestoes': []}


class TestRascunho:
    def test_rascunho_sem_preco_grava_e_fica_fora_do_cardapio(self, api, loja):
        r = api.post('/api/v1/stores/products/', {'store': str(loja.id), 'name': 'Novo prato', 'slug': 'novo-prato',
                                                   'status': 'draft'}, format='json')
        assert r.status_code == 201, r.content
        p = StoreProduct.objects.get(store=loja, name='Novo prato')
        assert p.status == 'draft' and p.price == 0
        assert not StoreProduct.disponiveis(loja).filter(pk=p.pk).exists()
        publico = APIClient().get(f'/api/v1/public/{loja.slug}/products/').json()
        linhas = publico['results'] if isinstance(publico, dict) else publico
        assert 'Novo prato' not in {x['name'] for x in linhas}

    def test_ativo_sem_preco_e_recusado(self, api, loja):
        r = api.post('/api/v1/stores/products/', {'store': str(loja.id), 'name': 'Sem preço', 'slug': 'sem-preco',
                                                   'status': 'active'}, format='json')
        assert r.status_code == 400 and 'price' in r.data['error']['details']
