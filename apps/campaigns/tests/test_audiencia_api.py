"""O endpoint que o painel usa para escolher a audiência.

Antes desta entrega o painel chamava `/system-contacts/?source=all` com o
`source` fixo no código e recebia uma lista crua: sem segmento, sem contagem
por balde e sem saber quem já tinha pedido para sair.
"""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.campaigns.services.optout import registrar_saida
from apps.stores.models import Store, StoreOrder
from apps.whatsapp.models import WhatsAppAccount

User = get_user_model()


class AudienciaTests(TestCase):
    def setUp(self):
        self.dono = User.objects.create_user(username='dono', password='x')
        self.conta = WhatsAppAccount.objects.create(
            name='Cê', phone_number_id='PH1', waba_id='W1'
        )
        self.loja = Store.objects.create(
            name='Cê Saladas', slug='ce-saladas', owner=self.dono,
            whatsapp_account=self.conta,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.dono)

        # VIP e recente: 5 pedidos, o último hoje.
        for _ in range(5):
            self._pedido('556391110001', 'Vip', dias=1, total=100)
        # Novo e sumido: 1 pedido há 60 dias.
        self._pedido('556391110002', 'Sumido', dias=60, total=30)
        # Cancelado não faz de ninguém cliente.
        self._pedido('556391110003', 'Cancelou', dias=2, total=80, status='cancelled')

    def _pedido(self, telefone, nome, dias, total, status='delivered'):
        pedido = StoreOrder.objects.create(
            store=self.loja, customer_phone=telefone, customer_name=nome,
            status=status, payment_status='paid',
            subtotal=total, delivery_fee=0, total=total,
        )
        StoreOrder.objects.filter(pk=pedido.pk).update(
            created_at=timezone.now() - timedelta(days=dias)
        )
        return pedido

    def _get(self, **params):
        return self.client.get('/api/v1/campaigns/system-contacts/', params)

    def test_sem_filtro_devolve_todos_e_diz_isso(self):
        r = self._get()
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['descricao'], 'Todos os contatos')
        telefones = {c['phone'] for c in r.data['results']}
        self.assertIn('556391110001', telefones)
        self.assertIn('556391110002', telefones)

    def test_filtro_de_vip_deixa_so_o_vip(self):
        r = self._get(frequencia='vip')
        self.assertEqual([c['phone'] for c in r.data['results']], ['556391110001'])
        self.assertIn('VIP', r.data['descricao'])

    def test_filtro_de_inativo_deixa_so_quem_sumiu(self):
        r = self._get(recencia='inativo')
        self.assertEqual([c['phone'] for c in r.data['results']], ['556391110002'])

    def test_quem_so_cancelou_nao_conta_como_cliente(self):
        # Ele aparece na lista (é um contato), mas como "nunca comprou" —
        # nunca como ativo, senão receberia oferta de recompra sem ter comprado.
        r = self._get()
        cancelou = [c for c in r.data['results'] if c['phone'] == '556391110003']
        if cancelou:
            self.assertEqual(cancelou[0]['recencia'], 'nunca_comprou')
            self.assertEqual(cancelou[0]['pedidos'], 0)

    def test_resumo_conta_cada_balde_antes_do_filtro(self):
        # O resumo serve para ESCOLHER; se ele já obedecesse o filtro só saberia
        # repetir o que foi escolhido.
        r = self._get(frequencia='vip')
        por_valor = {b['valor']: b['total'] for b in r.data['resumo']['frequencia']}
        self.assertEqual(por_valor['vip'], 1)
        self.assertEqual(por_valor['novo'], 1)

    def test_filtrar_por_conta_nao_some_com_quem_comprou(self):
        """Regressão: filtrar por conta apagava todo cliente vindo de pedido.

        A view só reconhecia a ligação loja↔número via `StoreIntegration`, e em
        28/ago/2026 nenhuma das quatro lojas reais tinha uma: Cê Saladas e
        Pastita usam `Store.whatsapp_account`. Com `account_id` na query, a
        lista perdia exatamente as pessoas que já compraram — que são as únicas
        segmentáveis por comportamento.
        """
        sem_conta = self._get()
        com_conta = self._get(account_id=str(self.conta.id))

        telefones_sem = {c['phone'] for c in sem_conta.data['results']}
        telefones_com = {c['phone'] for c in com_conta.data['results']}

        self.assertIn('556391110001', telefones_sem)
        self.assertIn('556391110001', telefones_com)

    def test_quem_pediu_para_sair_nao_aparece_e_e_contado(self):
        registrar_saida(self.conta, '556391110001', 'Parar promoções', 'button')
        r = self._get(account_id=str(self.conta.id))
        telefones = {c['phone'] for c in r.data['results']}
        self.assertNotIn('556391110001', telefones)
        self.assertEqual(r.data['excluidos_por_optout'], 1)

    def test_filtro_desconhecido_nao_derruba_a_tela(self):
        # Painel antigo mandando segmento que não existe mais precisa ver
        # "todos", não um 400 que quebra a página inteira.
        r = self._get(recencia='balde_que_nao_existe')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['descricao'], 'Todos os contatos')

    def test_ticket_minimo_exclui_quem_gasta_pouco(self):
        r = self._get(ticket_min='50')
        self.assertEqual([c['phone'] for c in r.data['results']], ['556391110001'])

    def test_opcoes_listam_o_que_da_para_escolher(self):
        r = self.client.get('/api/v1/campaigns/audiencia/opcoes/')
        self.assertEqual(r.status_code, 200)
        self.assertTrue(any(o['valor'] == 'vip' for o in r.data['frequencia']))
        self.assertTrue(any(o['valor'] == 'inativo' for o in r.data['recencia']))
