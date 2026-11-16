"""
Combo pode morar dentro de uma categoria do cardápio.

Ivoneth (15/11): "Monte seu Coffee Break" é um combo dinâmico, mas o cliente
procura em "Coffee Break" — não numa seção "Combos" solta no topo. O combo
ganha uma categoria opcional; sem ela, continua na seção de combos.
"""
from django.test import TestCase

from apps.stores.api.serializers import PublicComboSerializer, StoreComboSerializer
from apps.stores.models import StoreCategory
from apps.stores.tests.factories import make_combo_with_groups


class ComboNaCategoriaTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.store, cls.combo = make_combo_with_groups(groups=1, variants=0, options=1)
        cls.categoria = StoreCategory.objects.create(
            store=cls.store, name='Coffee Break', slug='coffee-break',
        )

    def test_sem_categoria_vem_nulo(self):
        assert PublicComboSerializer(self.combo).data['category'] is None

    def test_com_categoria_expoe_o_id(self):
        self.combo.category = self.categoria
        self.combo.save(update_fields=['category'])
        assert PublicComboSerializer(self.combo).data['category'] == str(self.categoria.id)

    def test_painel_grava_a_categoria(self):
        s = StoreComboSerializer(self.combo, data={'category': str(self.categoria.id)}, partial=True)
        assert s.is_valid(), s.errors
        s.save()
        self.combo.refresh_from_db()
        assert self.combo.category_id == self.categoria.id

    def test_painel_recusa_categoria_de_outra_loja(self):
        _, outro_combo = make_combo_with_groups(groups=1, variants=0, options=1)
        alheia = StoreCategory.objects.create(store=outro_combo.store, name='X', slug='x')
        s = StoreComboSerializer(self.combo, data={'category': str(alheia.id)}, partial=True)
        assert not s.is_valid()
        assert 'category' in s.errors

    def test_apagar_a_categoria_devolve_o_combo_para_combos(self):
        self.combo.category = self.categoria
        self.combo.save(update_fields=['category'])
        self.categoria.delete()
        self.combo.refresh_from_db()
        assert self.combo.category_id is None


class ComboPassoAPassoTest(TestCase):
    """Montador em passos (Ivoneth 16/11) é escolha do combo, não regra geral:
    o Combo Família da Pastita segue na lista de sempre."""

    @classmethod
    def setUpTestData(cls):
        cls.store, cls.combo = make_combo_with_groups(groups=1, variants=0, options=1)

    def test_padrao_e_lista(self):
        assert PublicComboSerializer(self.combo).data['passo_a_passo'] is False

    def test_ligado_no_metadata(self):
        self.combo.metadata = {**(self.combo.metadata or {}), 'passo_a_passo': True}
        self.combo.save(update_fields=['metadata'])
        assert PublicComboSerializer(self.combo).data['passo_a_passo'] is True
