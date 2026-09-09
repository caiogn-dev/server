"""Resgate de brinde registrado À MÃO pelo painel.

Até 09/09/2026 o único caminho que gravava resgate era o checkout com o brinde
aplicado (`CheckoutService`). Em produção: 137 contas, 161 transações `earn` e
ZERO `redeem`. Quem entrega a salada grátis pelo WhatsApp ou no balcão nunca
conseguia baixar o crédito — o painel (e o storefront, que lê o mesmo status)
seguia oferecendo o brinde já entregue.
"""
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.stores.models import Store, StoreLoyaltyAccount
from apps.stores.models.loyalty import StoreLoyaltyTransaction

User = get_user_model()


class ResgateManualTest(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='dono-rm', password='x')
        self.other = User.objects.create_user(username='intruso-rm', password='x')
        self.cliente = User.objects.create_user(
            username='cli-rm', password='x', email='c@x.com', first_name='Aline')
        self.store = Store.objects.create(
            name='Loja RM', slug='loja-rm', owner=self.owner, status='active',
            metadata={'loyalty_salads_required': 10},
        )
        # 32 qualificadas = 3 brindes ganhos, nenhum baixado (o caso da Aline).
        self.conta = StoreLoyaltyAccount.objects.create(
            store=self.store, user=self.cliente, qualified_count=32, redeemed_count=0)
        self.url = (
            f'/api/v1/stores/{self.store.slug}/loyalty/accounts/'
            f'{self.cliente.id}/resgatar/'
        )

    def test_dono_marca_resgate_e_o_saldo_cai(self):
        self.client.force_authenticate(user=self.owner)
        resp = self.client.post(self.url, {'quantidade': 2, 'motivo': 'entregues no WhatsApp'},
                                format='json')
        assert resp.status_code == 200, resp.content
        self.conta.refresh_from_db()
        assert self.conta.redeemed_count == 2
        assert resp.json()['available_rewards'] == 1
        assert resp.json()['redeemed_count'] == 2

    def test_resgate_vira_transacao_com_o_motivo(self):
        self.client.force_authenticate(user=self.owner)
        self.client.post(self.url, {'quantidade': 1, 'motivo': 'balcão'}, format='json')
        tx = StoreLoyaltyTransaction.objects.get(account=self.conta)
        assert tx.kind == StoreLoyaltyTransaction.Kind.REDEEM
        assert tx.quantity == 1
        assert tx.order_id is None
        assert 'balcão' in tx.note

    def test_sem_saldo_recusa_e_nao_grava(self):
        self.client.force_authenticate(user=self.owner)
        resp = self.client.post(self.url, {'quantidade': 4}, format='json')
        assert resp.status_code == 400, resp.content
        self.conta.refresh_from_db()
        assert self.conta.redeemed_count == 0
        assert StoreLoyaltyTransaction.objects.filter(account=self.conta).count() == 0

    def test_desfazer_devolve_o_brinde(self):
        """Clique errado precisa ter volta — senão o dono fica com medo do botão."""
        self.client.force_authenticate(user=self.owner)
        self.client.post(self.url, {'quantidade': 1}, format='json')
        resp = self.client.post(self.url, {'quantidade': -1, 'motivo': 'cliquei errado'},
                                format='json')
        assert resp.status_code == 200, resp.content
        self.conta.refresh_from_db()
        assert self.conta.redeemed_count == 0
        assert resp.json()['available_rewards'] == 3

    def test_desfazer_nao_deixa_resgate_negativo(self):
        self.client.force_authenticate(user=self.owner)
        resp = self.client.post(self.url, {'quantidade': -1}, format='json')
        assert resp.status_code == 400, resp.content
        self.conta.refresh_from_db()
        assert self.conta.redeemed_count == 0

    def test_quantidade_zero_e_recusada(self):
        self.client.force_authenticate(user=self.owner)
        assert self.client.post(self.url, {'quantidade': 0}, format='json').status_code == 400

    def test_nao_dono_recebe_403(self):
        self.client.force_authenticate(user=self.other)
        assert self.client.post(self.url, {'quantidade': 1}, format='json').status_code == 403
        self.conta.refresh_from_db()
        assert self.conta.redeemed_count == 0

    def test_anonimo_recebe_401(self):
        assert self.client.post(self.url, {'quantidade': 1}, format='json').status_code == 401

    def test_conta_de_outra_loja_nao_e_alcancavel(self):
        """O user_id vem da URL: sem filtrar por loja, o dono A baixaria o
        brinde do cliente da loja B."""
        outra = Store.objects.create(
            name='Outra', slug='outra-rm', owner=self.other, status='active',
            metadata={'loyalty_salads_required': 10})
        StoreLoyaltyAccount.objects.create(
            store=outra, user=self.cliente, qualified_count=50, redeemed_count=0)
        self.client.force_authenticate(user=self.owner)
        resp = self.client.post(self.url, {'quantidade': 3}, format='json')
        assert resp.status_code == 200, resp.content
        self.conta.refresh_from_db()
        assert self.conta.redeemed_count == 3          # a conta DESTA loja
        assert StoreLoyaltyAccount.objects.get(store=outra, user=self.cliente).redeemed_count == 0
