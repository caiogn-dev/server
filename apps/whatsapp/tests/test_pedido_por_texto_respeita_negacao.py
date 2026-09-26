"""Pedido digitado: "sem X" tira, não pede — e a observação não se perde.

25/09, conversa real com a Cê Saladas (pedido CE-2609251646). A cliente
escreveu:

    Vou querer uma espécie filé de frango, sem tomate cereja e sem cebola
    roxa, se poder acrescentar cenoura ralada no lugar eu agradeço

O bot pôs no carrinho **1x Cebola roxa — R$ 2,99** (o complemento que ela
pediu para TIRAR), ignorou a salada de R$ 39,99 e jogou fora as três
observações. O PIX saiu de R$ 22,29; a atendente recalculou na mão.

Causa: `_parse_items_from_text_dynamic` devolvia o primeiro produto cujo nome
aparecesse no texto, sem olhar se estava dentro de "sem …". A regra de negação
já existia em `busca_de_produto` — este caminho é que não a usava.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.automation.models import CompanyProfile
from apps.automation.services import get_session_manager
from apps.conversations.models import Conversation
from apps.stores.models import Store, StoreProduct
from apps.stores.services.busca_de_produto import separar_negacoes
from apps.whatsapp.intents.handlers.base import _parse_items_from_text_dynamic
from apps.whatsapp.intents.handlers.order import CreateOrderHandler
from apps.whatsapp.models import WhatsAppAccount

User = get_user_model()
PHONE = '5563981545075'
FRASE = (
    'Vou querer uma espécie filé de frango, sem tomate cereja e sem cebola roxa , '
    'se poder acrescentar cenoura ralada no lugar eu agradeço 🥹'
)


class SepararNegacoesTest(TestCase):
    def test_tira_os_trechos_negados_e_devolve_os_dois_lados(self):
        pedido, negados = separar_negacoes(FRASE)
        self.assertIn('espécie filé de frango', pedido.lower())
        self.assertNotIn('cebola', pedido.lower())
        self.assertNotIn('tomate', pedido.lower())
        self.assertEqual([n.lower() for n in negados], ['sem tomate cereja', 'sem cebola roxa'])

    def test_sem_negacao_devolve_a_frase_inteira(self):
        pedido, negados = separar_negacoes('quero 2 combos de 5 saladas')
        self.assertEqual(pedido, 'quero 2 combos de 5 saladas')
        self.assertEqual(negados, [])

    def test_sempre_nao_e_negacao(self):
        pedido, negados = separar_negacoes('quero o de sempre')
        self.assertEqual(negados, [])


class PedidoPorTextoTest(TestCase):
    def setUp(self):
        owner = User.objects.create_user(username='dona-ce-neg', password='x')
        self.store = Store.objects.create(
            billing_exempt=True, name='Cê Saladas', slug='ce-saladas-neg', owner=owner,
        )
        self.account = WhatsAppAccount.objects.create(name='CeNeg', phone_number_id='PHNEG', waba_id='WNEG')
        self.store.whatsapp_account = self.account
        self.store.save(update_fields=['whatsapp_account'])
        self.profile = CompanyProfile.objects.get(store=self.store)
        self.profile.account = self.account
        CompanyProfile.objects.filter(account=self.account).exclude(pk=self.profile.pk).delete()
        self.profile.save()
        self.conversation = Conversation.objects.create(account=self.account, phone_number=PHONE)
        self.produtos = {}
        for nome, preco in (('Especial Filé de Frango', 39.99), ('Cebola roxa', 2.99),
                            ('Frango em pedaços', 14.99), ('Tomate cereja', 3.5)):
            self.produtos[nome] = StoreProduct.objects.create(
                store=self.store, name=nome, slug=nome.lower().replace(' ', '-'), price=preco, is_active=True,
            )

    def _itens(self, texto):
        return [(StoreProduct.objects.get(id=i['product_id']).name, i['quantity'])
                for i in _parse_items_from_text_dynamic(texto, self.store)]

    # --- o caso de 25/09 -------------------------------------------------

    def test_frase_da_cliente_vira_a_salada_e_nao_a_cebola(self):
        self.assertEqual(self._itens(FRASE), [('Especial Filé de Frango', 1)])

    def test_produto_negado_nunca_entra(self):
        self.assertEqual(self._itens('quero um frango em pedaços sem cebola roxa'), [('Frango em pedaços', 1)])
        self.assertEqual(self._itens('sem cebola roxa'), [])

    def test_ganha_quem_casa_mais_palavras_e_nao_quem_aparece_primeiro(self):
        # "Frango em pedaços" casa 1 palavra; "Especial Filé de Frango" casa 2.
        self.assertEqual(self._itens('me vê um file de frango especial'), [('Especial Filé de Frango', 1)])

    # --- o que NÃO pode regredir ----------------------------------------

    def test_quantidade_e_produto_avulso_continuam_funcionando(self):
        self.assertEqual(self._itens('2 cebola roxa'), [('Cebola roxa', 2)])
        self.assertEqual(self._itens('quero tomate cereja'), [('Tomate cereja', 1)])


class CreateOrderGuardaObservacaoTest(PedidoPorTextoTest):
    def test_as_observacoes_da_frase_vao_para_o_pedido(self):
        handler = CreateOrderHandler(self.account, self.conversation, self.profile)
        resultado = handler.handle({'original_message': FRASE})

        self.assertTrue(resultado.use_interactive)
        sessao = get_session_manager(self.profile, self.conversation.phone_number)
        itens = sessao.get_pending_order_items()
        self.assertEqual([i['product_id'] for i in itens], [str(self.produtos['Especial Filé de Frango'].id)])
        notas = sessao.get_customer_notes().lower()
        self.assertIn('sem tomate cereja', notas)
        self.assertIn('sem cebola roxa', notas)
        self.assertIn('cenoura ralada', notas)

    def test_frase_sem_observacao_nao_inventa_nota(self):
        handler = CreateOrderHandler(self.account, self.conversation, self.profile)
        handler.handle({'original_message': 'quero 2 cebola roxa'})
        sessao = get_session_manager(self.profile, self.conversation.phone_number)
        self.assertEqual(sessao.get_customer_notes(), '')
