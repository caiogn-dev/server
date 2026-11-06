"""PDV (Balcão) vende só o cardápio da loja ativa.

Medido em 06/11: o Balcão da Cê Saladas mostrava "5 lojas" e itens de Agrião,
Ivoneth e Pastita. O painel puxava o catálogo de todas as lojas do usuário, e o
backend deixava: `GET /stores/products/` sem `store` devolvia o cardápio de
todas as lojas a que a conta tem acesso, misturado.

Regra:
- listar produtos exige a loja; loja sem acesso é 404 (não vaza que existe);
- a venda nasce na loja da URL (`/stores/<loja>/orders/`), e item de outra
  loja — mesmo que do mesmo dono — é recusado.
"""
import pytest
from rest_framework.test import APIClient

from apps.stores.models import StoreOrder, StoreProduct
from apps.stores.tests.factories import make_store


def _produto(loja, nome):
    return StoreProduct.objects.create(
        store=loja, name=nome, price='20.00',
        status=StoreProduct.ProductStatus.ACTIVE, track_stock=False,
    )


@pytest.fixture
def ce(db):
    return make_store(name='Cê Saladas')


@pytest.fixture
def agriao(ce):
    # Mesmo dono: o vazamento acontecia justamente entre lojas da mesma conta.
    loja = make_store(name='Agrião')
    loja.owner = ce.owner
    loja.save(update_fields=['owner'])
    return loja


@pytest.fixture
def api(ce):
    c = APIClient()
    c.force_authenticate(user=ce.owner)
    return c


def _ids(resposta):
    dados = resposta.json()
    linhas = dados.get('results', dados) if isinstance(dados, dict) else dados
    return {linha['id'] for linha in linhas}


def _venda(loja, produto, **extra):
    return {
        'customer_name': 'Cliente Balcão',
        'customer_phone': '00000000000',
        'delivery_method': 'pickup',
        'payment_method': 'cash',
        'source': 'pdv',
        'suppress_notifications': True,
        'items': [{'product_id': str(produto.id), 'quantity': 1}],
        **extra,
    }


@pytest.mark.django_db
class TestCatalogoDaLojaAtiva:
    def test_listar_produtos_sem_loja_e_recusado(self, api, ce, agriao):
        _produto(ce, 'Salada Cê')
        _produto(agriao, 'Marmita Agrião')
        r = api.get('/api/v1/stores/products/')
        assert r.status_code == 400

    def test_listar_com_loja_traz_so_a_loja(self, api, ce, agriao):
        da_ce = _produto(ce, 'Salada Cê')
        do_agriao = _produto(agriao, 'Marmita Agrião')
        r = api.get(f'/api/v1/stores/products/?store={ce.slug}&status=active')
        assert r.status_code == 200
        assert _ids(r) == {str(da_ce.id)}
        assert str(do_agriao.id) not in _ids(r)

    def test_loja_sem_acesso_e_404(self, api, ce):
        alheia = make_store(name='Loja de outro dono')
        _produto(alheia, 'Prato alheio')
        r = api.get(f'/api/v1/stores/products/?store={alheia.slug}')
        assert r.status_code == 404
        r = api.get(f'/api/v1/stores/products/?store={alheia.id}')
        assert r.status_code == 404

    def test_rota_aninhada_continua_valendo(self, api, ce, agriao):
        da_ce = _produto(ce, 'Salada Cê')
        _produto(agriao, 'Marmita Agrião')
        r = api.get(f'/api/v1/stores/stores/{ce.id}/products/')
        assert r.status_code == 200
        assert _ids(r) == {str(da_ce.id)}

    def test_detalhe_pela_rota_plana_nao_exige_loja(self, api, ce):
        """Vincular código no PDV faz PATCH /stores/products/<id>/ sem `store`."""
        da_ce = _produto(ce, 'Salada Cê')
        r = api.patch(f'/api/v1/stores/products/{da_ce.id}/', {'barcode': '789000000001'}, format='json')
        assert r.status_code == 200


@pytest.mark.django_db
class TestVendaDoBalcao:
    def test_venda_nasce_na_loja_da_url(self, api, ce):
        salada = _produto(ce, 'Salada Cê')
        r = api.post(f'/api/v1/stores/stores/{ce.slug}/orders/', _venda(ce, salada, store=ce.slug), format='json')
        assert r.status_code == 201, r.content
        assert StoreOrder.objects.get(id=r.json()['id']).store_id == ce.id

    def test_item_de_outra_loja_do_mesmo_dono_e_recusado(self, api, ce, agriao):
        marmita = _produto(agriao, 'Marmita Agrião')
        r = api.post(f'/api/v1/stores/stores/{ce.slug}/orders/', _venda(ce, marmita, store=ce.slug), format='json')
        assert r.status_code == 400
        assert not StoreOrder.objects.filter(store__in=[ce, agriao]).exists()

    def test_loja_do_corpo_diferente_da_url_e_recusada(self, api, ce, agriao):
        """URL da Cê com `store` do Agrião no corpo gravava a venda no Agrião."""
        marmita = _produto(agriao, 'Marmita Agrião')
        r = api.post(f'/api/v1/stores/stores/{ce.slug}/orders/', _venda(ce, marmita, store=agriao.slug), format='json')
        assert r.status_code == 400
        assert not StoreOrder.objects.filter(store__in=[ce, agriao]).exists()
