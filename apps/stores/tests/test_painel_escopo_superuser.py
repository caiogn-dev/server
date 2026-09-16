"""Nenhuma rota do painel entrega dado de loja alheia por ser superuser.

Complemento de test_superuser_nao_ve_loja_de_cliente: lá o alvo eram as três
funções de vínculo; aqui são as rotas que repetiam a regra na mão, cada uma com
seu próprio `if user.is_superuser`. São exatamente as rotas de DINHEIRO —
insights, exportação de faturamento, caixa, assinatura e fidelidade — que é o
que o dono de uma loja entende por "os meus números".

Cada caso é ancorado na loja própria: se a rota respondesse erro para TODA
loja, o assert de bloqueio passaria vazio e nunca acusaria vazamento.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from apps.stores.models import Store

User = get_user_model()

BLOQUEADO = {401, 403, 404}


class PainelEscopoSuperuserTest(TestCase):
    def setUp(self):
        self.plataforma = User.objects.create_superuser(
            username='dono_plataforma2', email='dono2@plataforma.com', password='x'
        )
        self.propria = Store.objects.create(
            name='Minha Loja', slug='minha-loja', owner=self.plataforma, status='active'
        )
        self.cliente = User.objects.create_user(
            username='cliente2', email='cliente2@loja.com', password='x'
        )
        self.alheia = Store.objects.create(
            name='Loja Alheia', slug='loja-alheia', owner=self.cliente, status='active'
        )
        self.api = APIClient()
        self.api.force_authenticate(user=self.plataforma)

    def _par(self, url_propria, url_alheia):
        """Devolve (status_propria, status_alheia)."""
        return (
            self.api.get(url_propria).status_code,
            self.api.get(url_alheia).status_code,
        )

    def test_insights_de_ia_nao_le_loja_alheia(self):
        base = reverse('stores:ai-daily-summary')
        propria, alheia = self._par(
            f'{base}?store={self.propria.slug}', f'{base}?store={self.alheia.slug}'
        )
        self.assertNotIn(propria, BLOQUEADO, 'âncora: a loja própria tem que passar')
        self.assertIn(alheia, BLOQUEADO)

    def test_export_de_faturamento_nao_le_loja_alheia(self):
        base = reverse('stores:revenue-export')
        propria, alheia = self._par(
            f'{base}?store={self.propria.slug}', f'{base}?store={self.alheia.slug}'
        )
        self.assertNotIn(propria, BLOQUEADO, 'âncora: a loja própria tem que passar')
        self.assertIn(alheia, BLOQUEADO)

    def test_gate_do_caixa_recusa_loja_alheia(self):
        """A rota do caixa responde 404 legítimo sem sessão aberta, então o
        alvo aqui é o gate, não o status HTTP."""
        from apps.stores.api.views.cash_views import _gate

        req = type('Req', (), {'user': self.plataforma})()
        self.assertTrue(_gate(req, self.propria))
        self.assertFalse(_gate(req, self.alheia))

    def test_gate_da_assinatura_recusa_loja_alheia(self):
        """Idem: sem StoreSubscription a rota dá 404 por falta de dado."""
        from apps.stores.api.views.subscription_views import _can_manage

        self.assertTrue(_can_manage(self.propria, self.plataforma))
        self.assertFalse(_can_manage(self.alheia, self.plataforma))

    def test_contas_de_fidelidade_de_loja_alheia_nao_sao_legiveis(self):
        propria, alheia = self._par(
            reverse('stores:store-loyalty-accounts', kwargs={'store_slug': self.propria.slug}),
            reverse('stores:store-loyalty-accounts', kwargs={'store_slug': self.alheia.slug}),
        )
        self.assertNotIn(propria, BLOQUEADO, 'âncora: a loja própria tem que passar')
        self.assertIn(alheia, BLOQUEADO)

    def test_agentes_de_impressao_nao_listam_loja_alheia(self):
        from apps.stores.models import StorePrintAgent

        StorePrintAgent.objects.create(
            store=self.propria, name='Impressora minha', api_key_prefix='pfx_minha'
        )
        StorePrintAgent.objects.create(
            store=self.alheia, name='Impressora alheia', api_key_prefix='pfx_alheia'
        )

        resp = self.api.get(reverse('stores:print-agent-list'))
        self.assertEqual(resp.status_code, 200)
        dados = resp.json()
        itens = dados.get('results', dados) if isinstance(dados, dict) else dados
        nomes = {item.get('name') for item in itens}
        self.assertIn('Impressora minha', nomes, 'âncora: a própria tem que aparecer')
        self.assertNotIn('Impressora alheia', nomes)
