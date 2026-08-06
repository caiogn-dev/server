"""
Regressão para CashHistoryReportView — N+1 queries em movimentos de caixa [P2].

Problema (antes do fix):
  O loop sobre sessions chamava `s.movements.aggregate(...)` a cada iteração,
  gerando 1 + N queries ao banco (N = sessões, até 100) em vez de 1 query com
  conditional aggregation via annotate().

Correção: .annotate(total_reinforcement=..., total_withdrawal=...) na queryset.

SimpleTestCase — sem DB / Docker / psycopg2.
"""
import inspect

from django.test import SimpleTestCase


def _src():
    from apps.stores.api.analytics_views import CashHistoryReportView
    return inspect.getsource(CashHistoryReportView.get)


class CashHistoryN1EliminadoTest(SimpleTestCase):

    def test_movements_aggregate_removido_do_loop(self):
        """s.movements.aggregate() foi removido — era a causa do N+1."""
        self.assertNotIn('movements.aggregate', _src())

    def test_queryset_usa_annotate(self):
        """A queryset agrupa movimentos via .annotate() em vez de loop."""
        self.assertIn('.annotate(', _src())

    def test_annotation_total_reinforcement(self):
        """Campo total_reinforcement presente no annotate."""
        self.assertIn('total_reinforcement', _src())

    def test_annotation_total_withdrawal(self):
        """Campo total_withdrawal presente no annotate."""
        self.assertIn('total_withdrawal', _src())

    def test_filtro_usa_movements_kind_reinforcement(self):
        """Filtro condicional usa movements__kind='reinforcement'."""
        self.assertIn("movements__kind='reinforcement'", _src())

    def test_filtro_usa_movements_kind_withdrawal(self):
        """Filtro condicional usa movements__kind='withdrawal'."""
        self.assertIn("movements__kind='withdrawal'", _src())

    def test_total_difference_acumulado_no_loop(self):
        """total_difference é acumulado dentro do for (não segunda iteração)."""
        self.assertIn('total_difference +=', _src())

    def test_sem_aggregate_apos_inicio_do_loop(self):
        """Nenhuma chamada .aggregate() no corpo do for sobre sessions."""
        src = _src()
        loop_start = src.find('for s in sessions')
        self.assertGreater(loop_start, 0, "Loop 'for s in sessions' não encontrado")
        self.assertNotIn('.aggregate(', src[loop_start:])

    def test_row_usa_campo_anotado_nao_dict(self):
        """Row lê s.total_reinforcement (annotate), não movements['reinforcement']."""
        src = _src()
        self.assertIn('s.total_reinforcement', src)
        self.assertIn('s.total_withdrawal', src)
        self.assertNotIn("movements['reinforcement']", src)
        self.assertNotIn("movements['withdrawal']", src)

    def test_chaves_de_resposta_inalteradas(self):
        """Chaves 'reinforcement' e 'withdrawal' continuam presentes no row."""
        src = _src()
        self.assertIn("'reinforcement':", src)
        self.assertIn("'withdrawal':", src)
