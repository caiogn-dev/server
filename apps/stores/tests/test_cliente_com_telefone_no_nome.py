"""05/10 — Marleny sumiu do Novo pedido.

O cadastro dela (UnifiedUser) nasceu no login por código do WhatsApp com o
TELEFONE no lugar do nome ("63981275718"). A busca do Novo pedido procura só em
UnifiedUser.name/phone_number, então digitar "Marleny" dava "cliente novo" —
mesmo com 3 pedidos "Marleny Barros" e 2 endereços salvos na loja.

E o nome nunca se corrigia: um nome só de números contava como nome real, então
o "Marleny Barros" dos pedidos seguintes não entrava.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APITestCase

from apps.core.services.customer_identity import CustomerIdentityService
from apps.stores.models import Store, StoreOrder
from apps.users.models import UnifiedUser, UserAddress

User = get_user_model()


class NomeQueEhTelefoneTests(TestCase):
    def test_telefone_no_nome_e_provisorio(self):
        for nome in ('63981275718', '5563981275718', '+55 (63) 98127-5718'):
            self.assertTrue(CustomerIdentityService.is_placeholder_name(nome), nome)

    def test_nome_de_verdade_continua_real(self):
        for nome in ('Marleny Barros', 'Ana', 'Apto 101'):
            self.assertFalse(CustomerIdentityService.is_placeholder_name(nome), nome)

    def test_pedido_com_nome_real_corrige_o_cadastro(self):
        user = UnifiedUser.objects.create(phone_number='5563981275718', name='63981275718')
        UnifiedUser._maybe_update(user, name='Marleny Barros')
        user.refresh_from_db()
        self.assertEqual(user.name, 'Marleny Barros')


class BuscaDoNovoPedidoTests(APITestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='ow-marleny', email='ow-m@t.com', password='x')
        self.store = Store.objects.create(name='Loja M', slug='loja-m', owner=self.owner, status='active')
        self.dj = User.objects.create_user(username='5563981275718', password='x',
                                           first_name='63981275718', last_name='Barros')
        self.cliente = UnifiedUser.objects.create(
            phone_number='5563981275718', name='63981275718', django_user=self.dj,
        )
        UserAddress.objects.create(unified_user=self.cliente, tenant=self.store,
                                   street='407 Norte Alameda 7', number='58', city='Palmas', state='TO')
        StoreOrder.objects.create(
            store=self.store, customer=self.dj, customer_name='Marleny Barros',
            customer_phone='5563981275718', subtotal=Decimal('40'), total=Decimal('40'),
        )
        self.client.force_authenticate(self.owner)

    def _buscar(self, q):
        url = f'/api/v1/stores/{self.store.slug}/crm/customers/search/'
        resp = self.client.get(url, {'q': q})
        self.assertEqual(resp.status_code, 200, resp.content)
        return resp.json()

    def test_acha_pelo_nome_usado_nos_pedidos(self):
        achados = self._buscar('marleny')
        self.assertEqual([c['id'] for c in achados], [str(self.cliente.id)])
        self.assertEqual(len(achados[0]['addresses']), 1)

    def test_mostra_o_nome_dos_pedidos_quando_o_cadastro_so_tem_telefone(self):
        achados = self._buscar('marleny')
        self.assertEqual(achados[0]['name'], 'Marleny Barros')

    def test_acha_pelo_telefone_digitado_com_mascara(self):
        achados = self._buscar('(63) 98127-5718')
        self.assertEqual([c['id'] for c in achados], [str(self.cliente.id)])

    def test_pedido_de_outra_loja_nao_vaza(self):
        outra = Store.objects.create(name='Outra', slug='outra-m', owner=self.owner, status='active')
        dj2 = User.objects.create_user(username='x2', password='x')
        UnifiedUser.objects.create(phone_number='5563900000000', name='63900000000', django_user=dj2)
        StoreOrder.objects.create(store=outra, customer=dj2, customer_name='Marleny Outra',
                                  customer_phone='5563900000000', subtotal=Decimal('1'), total=Decimal('1'))
        achados = self._buscar('marleny')
        self.assertEqual([c['id'] for c in achados], [str(self.cliente.id)])


class PedidoDoPdvComTelefoneNoNomeTests(APITestCase):
    """05/10 13:13 — CE-2610052174 saiu com '63981275718' no nome mesmo com o
    cadastro já corrigido: o painel manda o nome que tinha na tela. O backend
    não pode aceitar telefone como nome quando conhece o nome de verdade."""

    def setUp(self):
        self.owner = User.objects.create_user(username='ow-pdv-m', email='ow-pdv@t.com', password='x')
        self.store = Store.objects.create(name='Loja P', slug='loja-p', owner=self.owner, status='active')
        self.dj = User.objects.create_user(username='5563981275718', password='x',
                                           first_name='Marleny', last_name='Barros')
        UnifiedUser.objects.create(phone_number='5563981275718', name='Marleny Barros', django_user=self.dj)

    def test_nome_que_e_telefone_vira_o_nome_do_cadastro(self):
        from apps.core.services.customer_identity import CustomerIdentityService
        nome = CustomerIdentityService.nome_para_pedido('63981275718', phone='5563981275718', user=self.dj)
        self.assertEqual(nome, 'Marleny Barros')

    def test_nome_real_digitado_e_respeitado(self):
        from apps.core.services.customer_identity import CustomerIdentityService
        nome = CustomerIdentityService.nome_para_pedido('Marleny B.', phone='5563981275718', user=self.dj)
        self.assertEqual(nome, 'Marleny B.')

    def test_sem_nome_conhecido_mantem_o_que_veio(self):
        from apps.core.services.customer_identity import CustomerIdentityService
        nome = CustomerIdentityService.nome_para_pedido('63900001111', phone='5563900001111', user=None)
        self.assertEqual(nome, '63900001111')


class BuscaAchaQuemSoConversouTests(APITestCase):
    """05/10 — Daniella conversa com a loja pelo WhatsApp desde 06/08, nunca
    pediu. A busca do Novo pedido só via quem tinha pedido, endereço ou
    StoreCustomer: 555 cadastros ficavam invisíveis. Quem conversa com o
    WhatsApp DESTA loja é cliente dela."""

    def setUp(self):
        from apps.conversations.models import Conversation
        from apps.whatsapp.models import WhatsAppAccount
        self.owner = User.objects.create_user(username='ow-dani', email='ow-dani@t.com', password='x')
        self.store = Store.objects.create(name='Loja D', slug='loja-d', owner=self.owner, status='active')
        conta = WhatsAppAccount.objects.create(
            name='Conta D', phone_number_id='pn-d', waba_id='wa-d', phone_number='+5563900000001',
            display_phone_number='+5563900000001', access_token_encrypted='x', webhook_verify_token='x', owner=self.owner,
        )
        self.store.whatsapp_account = conta
        self.store.save()
        # wa_id sem o nono dígito no cadastro, com ele na conversa — como em produção.
        self.dani = UnifiedUser.objects.create(phone_number='556399410086', name='Daniella')
        Conversation.objects.create(account=conta, phone_number='5563999410086', contact_name='Daniella')
        self.outro = UnifiedUser.objects.create(phone_number='556381112222', name='Cliente')
        Conversation.objects.create(account=conta, phone_number='5563981112222', contact_name='Dani Souza')

        outro_dono = User.objects.create_user(username='ow-x', email='ow-x@t.com', password='x')
        conta_x = WhatsAppAccount.objects.create(
            name='Conta X', phone_number_id='pn-x', waba_id='wa-x', phone_number='+5563900000002',
            display_phone_number='+5563900000002', access_token_encrypted='x', webhook_verify_token='x', owner=outro_dono,
        )
        UnifiedUser.objects.create(phone_number='556387776666', name='Daniella de Outra Loja')
        Conversation.objects.create(account=conta_x, phone_number='5563987776666', contact_name='Daniella de Outra Loja')
        self.client.force_authenticate(self.owner)

    def _buscar(self, q):
        resp = self.client.get(f'/api/v1/stores/{self.store.slug}/crm/customers/search/', {'q': q})
        self.assertEqual(resp.status_code, 200, resp.content)
        return resp.json()

    def test_acha_quem_so_conversou_pelo_whatsapp(self):
        ids = [c['id'] for c in self._buscar('daniella')]
        self.assertIn(str(self.dani.id), ids)

    def test_acha_pelo_nome_do_contato_no_whatsapp(self):
        achados = self._buscar('souza')
        self.assertEqual([c['id'] for c in achados], [str(self.outro.id)])

    def test_conversa_de_outra_loja_nao_vaza(self):
        nomes = [c['name'] for c in self._buscar('daniella')]
        self.assertNotIn('Daniella de Outra Loja', nomes)
