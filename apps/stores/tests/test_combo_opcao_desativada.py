"""
Opção desativada não aparece no combo da vitrine.

Dono, 20/10, Queridinha + Suco + Sobremesa (Cê): 9 bebidas, 3 desativadas no
painel e 2 zeradas. A vitrine recebia todas — as desativadas ainda clicáveis,
as zeradas cinzas — e a lista ficava poluída. O painel (editor de combos)
continua vendo todas, senão o dono não consegue reativar nem tirar do grupo.
"""
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.stores.api.serializers import build_combo_groups
from apps.stores.models import StoreProduct
from apps.stores.tests.factories import make_combo_with_groups


class OpcaoDesativadaNoComboTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.store, cls.combo = make_combo_with_groups(groups=1, variants=0, options=4)
        cls.produtos = [o.product for o in cls.combo.groups.get().product_options.order_by('position')]
        for p in cls.produtos:
            p.track_stock = True
            p.allow_backorder = False
            p.stock_quantity = 5
            p.status = StoreProduct.ProductStatus.ACTIVE
            p.save()

    def _nomes(self, **kw):
        return [o['name'] for o in build_combo_groups(self.combo, **kw)[0]['product_options']]

    def test_vitrine_esconde_desativado_pausado_e_zerado(self):
        desativado, pausado, zerado, ok = self.produtos
        desativado.status = StoreProduct.ProductStatus.INACTIVE
        desativado.save()
        pausado.paused_until = timezone.now() + timedelta(hours=2)
        pausado.save()
        zerado.stock_quantity = 0
        zerado.save()

        assert self._nomes(somente_disponiveis=True) == [ok.name]

    def test_painel_continua_vendo_todas(self):
        self.produtos[0].status = StoreProduct.ProductStatus.INACTIVE
        self.produtos[0].save()
        assert len(self._nomes()) == 4

    def test_zerado_sob_encomenda_continua(self):
        p = self.produtos[0]
        p.stock_quantity = 0
        p.allow_backorder = True
        p.save()
        assert p.name in self._nomes(somente_disponiveis=True)
