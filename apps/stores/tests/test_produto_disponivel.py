"""Produto desativado pelo dono não pode ser oferecido pelo bot.

13/ago, apontado pelo dono: o "suco 1" estava desativado no painel e mesmo
assim aparecia. O motivo são DOIS campos que discordam:

    suco 1 →  is_active = True      status = 'inactive'

`status` é o campo real — é nele que o painel escreve. `is_active` vem de uma
classe base com `default=True` que ninguém nunca seta, então ele é True em
praticamente tudo. E **19 lugares do código filtram pelo campo errado**.

Medido em produção: 24 produtos que o dono desativou continuam sendo tratados
como ativos — 12 na Ivoneth, 6 na Cê Saladas, 4 na Pastita.

Contrato: existe UMA pergunta sobre disponibilidade, e ela olha os dois campos.
"""
from django.test import TestCase
from django.utils import timezone

from apps.stores.models import StoreProduct
from apps.stores.tests.factories import make_store


class ProdutoDisponivelTest(TestCase):
    def setUp(self):
        self.store = make_store(name='Cê Saladas')

    def _p(self, nome, **kw):
        return StoreProduct.objects.create(
            store=self.store, name=nome, slug=nome.lower().replace(' ', '-'),
            price=10, **kw,
        )

    def test_status_inactive_nao_esta_disponivel(self):
        """O caso do 'suco 1': o painel desativou, is_active ficou True."""
        p = self._p('suco 1', is_active=True, status='inactive')

        assert StoreProduct.disponiveis().filter(pk=p.pk).exists() is False

    def test_is_active_false_tambem_nao(self):
        p = self._p('velho', is_active=False, status='active')

        assert StoreProduct.disponiveis().filter(pk=p.pk).exists() is False

    def test_produto_normal_esta_disponivel(self):
        p = self._p('Salada Caesar', is_active=True, status='active')

        assert StoreProduct.disponiveis().filter(pk=p.pk).exists() is True

    def test_pausado_ate_o_futuro_nao_esta_disponivel(self):
        """Pausa rápida de item esgotado — o dono usa isso no meio do expediente."""
        p = self._p('Esgotado', is_active=True, status='active',
                    paused_until=timezone.now() + timezone.timedelta(hours=2))

        assert StoreProduct.disponiveis().filter(pk=p.pk).exists() is False

    def test_pausa_vencida_volta_a_valer(self):
        p = self._p('Voltou', is_active=True, status='active',
                    paused_until=timezone.now() - timezone.timedelta(hours=1))

        assert StoreProduct.disponiveis().filter(pk=p.pk).exists() is True


class BuscaNaoOfereceDesativadoTest(TestCase):
    """A trava tem que valer no caminho que o cliente usa."""

    def setUp(self):
        self.store = make_store(name='Cê Saladas')

    def test_casador_ignora_produto_desativado(self):
        from apps.stores.services.busca_de_produto import candidatos_de_produto

        StoreProduct.objects.create(
            store=self.store, name='Suco de Caju 400ml', slug='caju',
            price=12, is_active=True, status='inactive',
        )

        assert candidatos_de_produto(self.store, 'suco de caju') == []

    def test_casador_acha_o_ativo(self):
        from apps.stores.services.busca_de_produto import candidatos_de_produto

        StoreProduct.objects.create(
            store=self.store, name='Suco de laranja 400ml', slug='laranja',
            price=12, is_active=True, status='active',
        )

        achados = candidatos_de_produto(self.store, 'suco de laranja')
        assert [p.name for p in achados] == ['Suco de laranja 400ml']
