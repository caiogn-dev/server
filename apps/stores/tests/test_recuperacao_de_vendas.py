"""O painel do recuperador: quanto ficou no carrinho e quanto voltou.

Os lembretes de carrinho rodam desde sempre e NINGUÉM vê o resultado. Sem
esses números a loja não sabe se o recurso paga o incômodo — e "oportunidade
perdida em reais" é o número que faz o dono agir.

Regra de recuperação: o carrinho conta como recuperado quando a MESMA pessoa
faz um pedido DEPOIS do abandono. Sem o "depois", qualquer pedido do dia
contaria e o painel viraria propaganda enganosa.
"""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.stores.services.recuperacao import painel_de_recuperacao
from apps.stores.tests.factories import make_store


@pytest.fixture
def loja(db):
    return make_store()


def _carrinho(loja, telefone, quando, itens=None):
    from apps.stores.models.cart import StoreCart

    carrinho = StoreCart.objects.create(
        store=loja, is_active=True,
        metadata={'customer_phone': telefone, 'reminder_30min_sent': quando.isoformat()},
    )
    StoreCart.objects.filter(pk=carrinho.pk).update(updated_at=quando, created_at=quando)
    carrinho.refresh_from_db()
    return carrinho


def _pedido(loja, telefone, quando, total='50.00'):
    from apps.stores.models.order import StoreOrder

    pedido = StoreOrder.objects.create(
        store=loja, customer_phone=telefone, customer_name='Cliente',
        total=Decimal(total), subtotal=Decimal(total),
        status='delivered', payment_status='paid',
    )
    StoreOrder.objects.filter(pk=pedido.pk).update(created_at=quando)
    return pedido


class TestPainel:
    def test_carrinho_sem_pedido_depois_conta_como_perdido(self, loja):
        ontem = timezone.now() - timedelta(days=1)
        _carrinho(loja, '5563911110001', ontem)

        p = painel_de_recuperacao([loja.id], dias=7)

        assert p['abandonados'] == 1
        assert p['recuperados'] == 0

    def test_pedido_depois_do_abandono_conta_como_recuperado(self, loja):
        ontem = timezone.now() - timedelta(days=1)
        _carrinho(loja, '5563911110002', ontem)
        _pedido(loja, '5563911110002', ontem + timedelta(hours=2), '80.00')

        p = painel_de_recuperacao([loja.id], dias=7)

        assert p['recuperados'] == 1
        assert p['valor_recuperado'] == 80.0

    def test_pedido_ANTES_do_abandono_nao_conta(self, loja):
        """Senão o painel vira propaganda: qualquer pedido do dia 'recupera'."""
        ontem = timezone.now() - timedelta(days=1)
        _carrinho(loja, '5563911110003', ontem)
        _pedido(loja, '5563911110003', ontem - timedelta(hours=3))

        p = painel_de_recuperacao([loja.id], dias=7)

        assert p['recuperados'] == 0

    def test_o_mesmo_numero_em_outro_formato_ainda_e_a_mesma_pessoa(self, loja):
        ontem = timezone.now() - timedelta(days=1)
        _carrinho(loja, '5563911110004', ontem)
        _pedido(loja, '63911110004', ontem + timedelta(hours=1))

        p = painel_de_recuperacao([loja.id], dias=7)

        assert p['recuperados'] == 1

    def test_fora_do_periodo_nao_entra(self, loja):
        _carrinho(loja, '5563911110005', timezone.now() - timedelta(days=40))

        p = painel_de_recuperacao([loja.id], dias=7)

        assert p['abandonados'] == 0

    def test_oportunidade_perdida_e_o_que_sobrou(self, loja):
        ontem = timezone.now() - timedelta(days=1)
        c1 = _carrinho(loja, '5563911110006', ontem)
        c2 = _carrinho(loja, '5563911110007', ontem)
        _pedido(loja, '5563911110006', ontem + timedelta(hours=1), '30.00')

        p = painel_de_recuperacao([loja.id], dias=7)

        assert p['abandonados'] == 2
        assert p['recuperados'] == 1
        assert p['oportunidade_perdida'] == p['valor_abandonado'] - p['valor_recuperado']

    def test_sem_carrinho_nenhum_devolve_zeros_sem_quebrar(self, loja):
        p = painel_de_recuperacao([loja.id], dias=7)

        assert p['abandonados'] == 0
        assert p['taxa_de_recuperacao'] == 0
        assert p['mensagens_enviadas'] == 0

    def test_conta_as_mensagens_de_lembrete_do_periodo(self, loja):
        from apps.whatsapp.models import Message, WhatsAppAccount
        from apps.conversations.models import Conversation

        conta = WhatsAppAccount.objects.create(
            name='L', phone_number_id='PH-REC', waba_id='WABA-REC',
        )
        conversa = Conversation.objects.create(account=conta, phone_number='5563911110008')
        m = Message.objects.create(
            conversation=conversa, account=conta, direction='outbound',
            message_type='text', content='volta pro carrinho',
            metadata={'automatico': True, 'evento': 'cart_reminder'},
        )
        Message.objects.filter(pk=m.pk).update(created_at=timezone.now() - timedelta(days=1))

        p = painel_de_recuperacao([loja.id], dias=7, account_ids=[conta.id])

        assert p['mensagens_enviadas'] == 1


class TestApi:
    def _cliente(self, user):
        from rest_framework.test import APIClient

        c = APIClient()
        c.force_authenticate(user=user)
        return c

    def test_o_dono_ve_o_painel(self, loja):
        r = self._cliente(loja.owner).get(f'/api/v1/stores/{loja.slug}/recuperacao/?dias=7')

        assert r.status_code == 200
        assert r.data['dias'] == 7
        assert 'oportunidade_perdida' in r.data

    def test_loja_alheia_responde_nao_encontrada(self, loja, db):
        from django.contrib.auth import get_user_model

        vizinho = get_user_model().objects.create_user(username='vizinho-rec', password='x')

        r = self._cliente(vizinho).get(f'/api/v1/stores/{loja.slug}/recuperacao/')

        assert r.status_code == 404

    def test_periodo_absurdo_nao_derruba(self, loja):
        r = self._cliente(loja.owner).get(f'/api/v1/stores/{loja.slug}/recuperacao/?dias=abc')

        assert r.status_code == 200
        assert r.data['dias'] == 30
