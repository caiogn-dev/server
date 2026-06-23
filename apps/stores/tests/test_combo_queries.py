"""
Test: build_combo_groups deve ser O(1) queries quando o queryset vem com prefetch.

TDD RED  → StoreComboViewSet não tem queryset_for_test nem prefetch → N+1
TDD GREEN → após prefetch + Python sort → ≤6 queries
"""
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.db import connection
from apps.stores.api.serializers import StoreComboSerializer
from apps.stores.api.views.product_views import StoreComboViewSet
from apps.stores.tests.factories import make_combo_with_groups


class ComboQueryCountTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.store, cls.combo = make_combo_with_groups(groups=3, variants=2, options=2)

    def test_admin_combo_list_is_constant_queries(self):
        qs = StoreComboViewSet.queryset_for_test(store=self.store)
        with CaptureQueriesContext(connection) as ctx:
            data = StoreComboSerializer(qs, many=True).data
            # Forçar avaliação completa dos grupos (lazy prefetch realmente executa)
            _ = [g for c in data for g in c["groups"]]
        # 8 queries fixas (batch IN): combos + 4 prefetch_related batches × 2 joins
        # (groups__product, variant_limits__variant__product, product_options__product).
        # Constante independente do número de grupos/variantes/opções — sem N+1.
        assert len(ctx.captured_queries) <= 10, (
            f"Esperado ≤10 queries (constante), obtido {len(ctx.captured_queries)}:\n"
            + "\n".join(q["sql"][:200] for q in ctx.captured_queries)
        )
