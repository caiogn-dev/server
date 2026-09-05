"""A lista de cashback diz QUEM é a pessoa, não só o telefone.

O CASO REAL (04/09): "página de fidelidade não mostra o nome da cliente".

A lista é agrupada por telefone (o saldo mora em lotes por telefone, para
funcionar no checkout de convidado), e o agrupamento devolvia só o número. Na
tela ficava uma coluna de `(63) 99261-8115` sem um nome — o dono precisava
abrir outra página e procurar cada um para saber a quem estava prestes a
mandar mensagem.

A pergunta desta tela é "a quem eu falo hoje, antes do saldo vencer". Ela não
se responde com telefone.

O nome vem do PEDIDO mais recente daquele telefone: é o que a pessoa escreveu
no checkout, e é como o dono a reconhece. Cadastro pode estar vazio ou trazer
um placeholder interno (`cliente_5563...`), que na tela é pior que nada.
"""
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.stores.models import Store, StoreCashbackLot, StoreOrder

User = get_user_model()


class CashbackMostraONomeTest(TestCase):
    def setUp(self):
        self.dono = User.objects.create_user(username='dona-nome', password='x')
        self.store = Store.objects.create(
            billing_exempt=True, name='Cê Saladas', slug='ce-nome', owner=self.dono,
            store_type='food', status='active', metadata={'cashback_enabled': True},
        )
        self.client = APIClient()
        self.client.force_authenticate(self.dono)
        self.phone = '5563992618115'

    def _saldo(self, phone=None):
        return StoreCashbackLot.objects.create(
            store=self.store, phone=phone or self.phone,
            amount=Decimal('5'), remaining=Decimal('5'),
            origin=StoreCashbackLot.Origin.PURCHASE,
            expires_at=timezone.now() + timedelta(days=30),
        )

    def _pedido(self, nome, phone=None, dias_atras=0):
        pedido = StoreOrder.objects.create(
            store=self.store, customer_name=nome, customer_phone=phone or self.phone,
            subtotal=Decimal('50'), total=Decimal('50'),
            status='delivered', payment_status='paid',
        )
        if dias_atras:
            StoreOrder.objects.filter(pk=pedido.pk).update(
                created_at=timezone.now() - timedelta(days=dias_atras),
            )
        return pedido

    def _linhas(self):
        r = self.client.get(f'/api/v1/stores/{self.store.slug}/cashback/')
        self.assertEqual(r.status_code, 200, r.data)
        return r.data['results']

    def test_a_linha_traz_o_nome_da_cliente(self):
        self._pedido('Leani Rodrigues')
        self._saldo()

        self.assertEqual(self._linhas()[0]['nome'], 'Leani Rodrigues')

    def test_usa_o_nome_do_pedido_MAIS_RECENTE(self):
        """Ela mudou como se escreve; vale o último."""
        self._pedido('Leani', dias_atras=30)
        self._pedido('Leani Rodrigues Maciel')
        self._saldo()

        self.assertEqual(self._linhas()[0]['nome'], 'Leani Rodrigues Maciel')

    def test_quem_nunca_comprou_nao_fica_com_nome_falso(self):
        """Saldo de indicação existe antes da primeira compra."""
        self._saldo()

        self.assertEqual(self._linhas()[0]['nome'], '')

    def test_ignora_nome_placeholder_interno(self):
        """`cliente_5563...` na tela é pior que campo vazio."""
        self._pedido('cliente_5563992618115')
        self._saldo()

        self.assertEqual(self._linhas()[0]['nome'], '')

    def test_casa_o_nome_mesmo_com_o_telefone_em_outro_formato(self):
        """O pedido antigo pode ter ficado sem o DDI."""
        self._pedido('Leani Rodrigues', phone='63992618115')
        self._saldo()

        self.assertEqual(self._linhas()[0]['nome'], 'Leani Rodrigues')

    def test_uma_consulta_para_a_pagina_inteira(self):
        """50 clientes por página não podem virar 50 consultas de nome."""
        for i in range(6):
            tel = f'55639900000{i}0'
            self._pedido(f'Cliente {i}', phone=tel)
            self._saldo(phone=tel)

        from django.test.utils import CaptureQueriesContext
        from django.db import connection
        with CaptureQueriesContext(connection) as ctx:
            self._linhas()
        nomes = [q for q in ctx.captured_queries if 'customer_name' in q['sql']]

        self.assertLessEqual(len(nomes), 1, 'busca de nome virou N+1')


class CashbackDeUmClienteSoTest(TestCase):
    """A ficha do cliente pergunta o saldo DELE, não a lista inteira.

    O painel já tem o endpoint de cashback, escopado por dono e com o saldo
    COMPLETO (o público esconde a parte comprada de quem não comprovou o
    número — certo para a cliente, errado para o dono, que precisa ver o que
    ela tem). Faltava poder perguntar por uma pessoa.

    Filtro no endpoint que existe, e não um endpoint novo: são a mesma
    pergunta, com e sem recorte.
    """

    def setUp(self):
        self.dono = User.objects.create_user(username='dona-um-so', password='x')
        self.store = Store.objects.create(
            billing_exempt=True, name='Cê Saladas', slug='ce-um-so', owner=self.dono,
            store_type='food', status='active', metadata={'cashback_enabled': True},
        )
        self.client = APIClient()
        self.client.force_authenticate(self.dono)
        for tel, valor in [('5563992618115', '7.00'), ('5563984143551', '3.00')]:
            StoreCashbackLot.objects.create(
                store=self.store, phone=tel, amount=Decimal(valor), remaining=Decimal(valor),
                origin=StoreCashbackLot.Origin.PURCHASE,
                expires_at=timezone.now() + timedelta(days=30),
            )

    def _get(self, **params):
        return self.client.get(f'/api/v1/stores/{self.store.slug}/cashback/', params).data

    def test_filtra_por_telefone(self):
        dados = self._get(phone='5563992618115')

        self.assertEqual(len(dados['results']), 1)
        self.assertEqual(Decimal(dados['results'][0]['saldo']), Decimal('7.00'))

    def test_aceita_o_telefone_em_qualquer_formato(self):
        """O painel formata com parênteses; o cadastro guarda com DDI."""
        self.assertEqual(len(self._get(phone='(63) 99261-8115')['results']), 1)

    def test_sem_filtro_devolve_todo_mundo(self):
        self.assertEqual(len(self._get()['results']), 2)

    def test_quem_nao_tem_saldo_devolve_lista_vazia(self):
        self.assertEqual(self._get(phone='5511999999999')['results'], [])
