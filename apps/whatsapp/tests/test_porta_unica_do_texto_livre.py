"""Uma porta só para o texto livre que pede produto.

25/09, Cê Saladas (pedido CE-2609251646): "Vou querer uma espécie filé de
frango, sem tomate cereja e sem cebola roxa…" casou o regex `create_order`
("vou querer") e o extrator do próprio handler escolheu o item sozinho — pôs
1× Cebola roxa no carrinho. O 0c62340 consertou aquele extrator; este arquivo
prova que ele não existe mais como caminho paralelo: quem escolhe item em
texto livre é a triagem (`triar` → `ler_pedido`), para `create_order`,
`add_to_cart` e mensagem desconhecida. O regex continua decidindo saudação,
cardápio, rastrear, cancelar, atendente, horário e entrega.

Com mais de um produto empatado, o bot pergunta "qual destes?" em vez de
chutar.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.automation.models import CompanyProfile
from apps.automation.services import get_session_manager
from apps.automation.services.triagem import Intencao, triar
from apps.automation.services.unified_service import UnifiedService
from apps.conversations.models import Conversation
from apps.stores.models import Store, StoreProduct
from apps.stores.services.leitura_do_pedido import ler_pedido
from apps.whatsapp.models import WhatsAppAccount

User = get_user_model()
PHONE = '5563981545075'
FRASE = (
    'Vou querer uma espécie filé de frango, sem tomate cereja e sem cebola roxa , '
    'se poder acrescentar cenoura ralada no lugar eu agradeço 🥹'
)


class _Loja(TestCase):
    PRODUTOS = (
        ('Especial Filé de Frango', 39.99), ('Cebola roxa', 2.99),
        ('Frango em pedaços', 14.99), ('Tomate cereja', 3.5),
        ('Salada Caesar', 32.0), ('Monte sua Salada', 29.0), ('Suco de laranja', 9.0),
    )

    def setUp(self):
        owner = User.objects.create_user(username='dona-ce-porta', password='x')
        self.store = Store.objects.create(
            billing_exempt=True, name='Cê Saladas', slug='ce-saladas-porta', owner=owner,
        )
        self.account = WhatsAppAccount.objects.create(name='CePorta', phone_number_id='PHPORTA', waba_id='WPORTA')
        self.store.whatsapp_account = self.account
        self.store.save(update_fields=['whatsapp_account'])
        self.profile = CompanyProfile.objects.get(store=self.store)
        self.profile.account = self.account
        CompanyProfile.objects.filter(account=self.account).exclude(pk=self.profile.pk).delete()
        self.profile.save()
        self.conversation = Conversation.objects.create(account=self.account, phone_number=PHONE)
        self.p = {
            nome: StoreProduct.objects.create(
                store=self.store, name=nome, slug=nome.lower().replace(' ', '-'), price=preco, is_active=True,
            )
            for nome, preco in self.PRODUTOS
        }

    def _bot(self):
        return UnifiedService(self.account, self.conversation, use_llm=False)

    def _sessao(self):
        return get_session_manager(self.profile, PHONE)

    def _pendentes(self):
        return [(StoreProduct.objects.get(id=i['product_id']).name, i['quantity'])
                for i in self._sessao().get_pending_order_items()]

    @staticmethod
    def _botoes(resposta):
        return [b['id'] for b in (resposta.buttons or [])]


class FraseDe25DeSetembroTest(_Loja):
    def test_a_salada_entra_e_a_cebola_roxa_nao(self):
        self._bot().process_message(FRASE)

        self.assertEqual(self._pendentes(), [('Especial Filé de Frango', 1)])

    def test_as_observacoes_da_frase_seguem_com_o_pedido(self):
        self._bot().process_message(FRASE)

        notas = self._sessao().get_customer_notes().lower()
        self.assertIn('sem tomate cereja', notas)
        self.assertIn('sem cebola roxa', notas)
        self.assertIn('cenoura ralada', notas)


class EmpateViraPerguntaTest(_Loja):
    def test_dois_produtos_empatados_viram_qual_destes_sem_chutar(self):
        resposta = self._bot().process_message('quero pedir uma salada')

        ids = self._botoes(resposta)
        self.assertTrue(ids and all(i.startswith('qual_') for i in ids), ids)
        self.assertLessEqual(len(ids), 3)
        self.assertEqual(
            {i[len('qual_'):] for i in ids},
            {str(self.p['Salada Caesar'].id), str(self.p['Monte sua Salada'].id)},
        )
        self.assertIn('qual', resposta.content.lower())
        self.assertEqual(self._pendentes(), [], 'empate não pode pôr nada no carrinho')

    def test_escolher_no_botao_leva_o_produto_escolhido(self):
        self._bot().process_message('quero pedir uma salada sem cebola')
        escolhido = self.p['Salada Caesar']

        self._bot().process_message(
            '', interactive_reply={'id': f'qual_{escolhido.id}', 'title': 'Salada Caesar'},
        )

        self.assertEqual(self._pendentes(), [('Salada Caesar', 1)])
        self.assertIn('sem cebola', self._sessao().get_customer_notes().lower())


class RegexContinuaNoQueEleSabeTest(_Loja):
    def test_cardapio_continua_sendo_cardapio(self):
        resposta = self._bot().process_message('cardápio')

        self.assertFalse(any(i.startswith('qual_') for i in self._botoes(resposta)))
        self.assertEqual(self._pendentes(), [])

    def test_varios_itens_com_quantidade(self):
        self._bot().process_message('vou querer 2 frango em pedaços e 1 suco de laranja')

        self.assertEqual(
            sorted(self._pendentes()), [('Frango em pedaços', 2), ('Suco de laranja', 1)],
        )

    def test_pedido_sem_produto_mostra_o_cardapio(self):
        resposta = self._bot().process_message('quero fazer um pedido')

        self.assertEqual(resposta.interactive_type, 'catalog_message')
        self.assertEqual(self._pendentes(), [])


class TriagemComNegacaoTest(_Loja):
    def test_negacao_no_meio_da_frase_nao_apaga_o_pedido(self):
        d = triar(FRASE, store=self.store)

        self.assertIs(d.intencao, Intencao.ITEM)
        self.assertEqual(d.itens[0].name, 'Especial Filé de Frango')
        self.assertNotIn('Cebola roxa', [o.name for o in d.itens])

    def test_so_negacao_continua_nao_sendo_item(self):
        self.assertIsNot(triar('sem cebola roxa', store=self.store).intencao, Intencao.ITEM)


class LerPedidoTest(_Loja):
    """Os contratos que o extrator antigo (`_parse_items_from_text_dynamic`) garantia."""

    def _itens(self, texto):
        return [(o.name, q) for o, q in ler_pedido(self.store, texto).itens]

    def test_produto_negado_nunca_entra(self):
        self.assertEqual(self._itens('quero um frango em pedaços sem cebola roxa'), [('Frango em pedaços', 1)])
        self.assertEqual(self._itens('sem cebola roxa'), [])

    def test_ganha_quem_casa_mais_palavras(self):
        self.assertEqual(self._itens('me vê um file de frango especial'), [('Especial Filé de Frango', 1)])

    def test_quantidade_e_produto_avulso(self):
        self.assertEqual(self._itens('2 cebola roxa'), [('Cebola roxa', 2)])
        self.assertEqual(self._itens('quero tomate cereja'), [('Tomate cereja', 1)])
        self.assertEqual(self._itens('quero 3x suco de laranja'), [('Suco de laranja', 3)])

    def test_empate_vira_duvida_e_nao_item(self):
        leitura = ler_pedido(self.store, 'uma salada')
        self.assertEqual(leitura.itens, [])
        self.assertEqual({o.name for o in leitura.duvidas[0][0]}, {'Salada Caesar', 'Monte sua Salada'})
