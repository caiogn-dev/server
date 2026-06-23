"""
Test: build_combo_groups deve ser O(1) queries quando o queryset vem com prefetch.

Provar O(1) exige DOIS data points: um combo pequeno (3 grupos) e um grande
(6 grupos). Se houvesse N+1 sobre grupos, o grande dispararia mais queries que o
pequeno (count_large > count_small). Como ambos têm o MESMO número de queries
(batch IN do prefetch_related), provamos constância em relação ao número de
grupos G — um único data point não distinguiria O(1) de O(G).
"""
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.db import connection
from apps.stores.api.serializers import StoreComboSerializer
from apps.stores.api.views.product_views import StoreComboViewSet
from apps.stores.tests.factories import make_combo_with_groups


def _serialize_and_count(combo):
    """Serializa um combo (queryset com prefetch) e conta as queries disparadas.

    Força a avaliação completa dos grupos aninhados (variants + options) dentro
    do bloco de captura, senão o prefetch lazy não dispara.
    """
    qs = StoreComboViewSet.queryset_for_test(store=combo.store).filter(id=combo.id)
    with CaptureQueriesContext(connection) as ctx:
        data = StoreComboSerializer(qs, many=True).data
        for c in data:
            for g in c["groups"]:
                # tocar nas listas aninhadas garante avaliação do prefetch
                list(g["variant_limits"])
                list(g["product_options"])
    return len(ctx.captured_queries)


class ComboQueryCountTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        # Mesmo store, dois combos de tamanhos diferentes.
        cls.store, cls.combo_small = make_combo_with_groups(
            groups=3, variants=2, options=2
        )
        _, cls.combo_large = make_combo_with_groups(
            groups=6, variants=2, options=2, store=cls.store
        )

    def test_combo_serialization_is_constant_in_number_of_groups(self):
        count_small = _serialize_and_count(self.combo_small)
        count_large = _serialize_and_count(self.combo_large)

        # PROVA O(1): dobrar o número de grupos NÃO muda a contagem de queries.
        assert count_small == count_large, (
            f"N+1 sobre grupos: combo de 3 grupos = {count_small} queries, "
            f"combo de 6 grupos = {count_large} queries. Esperado idêntico."
        )

        # Teto absoluto. Breakdown esperado das 8 queries (batch IN, constante):
        #   1. SELECT store_combos
        #   2. SELECT combo_product_groups            (prefetch groups)
        #   3. SELECT store_products (âncora)         (prefetch groups__product)
        #   4. SELECT combo_product_group_variant_limits
        #   5. SELECT store_product_variants
        #   6. SELECT store_products (variante)       (__variant__product)
        #   7. SELECT combo_product_group_product_options
        #   8. SELECT store_products (opção)          (product_options__product)
        # 8 medido → teto 9 deixa 1 de folga sem mascarar um N+1.
        assert count_large <= 9, (
            f"Esperado ≤9 queries (constante), obtido {count_large}."
        )
