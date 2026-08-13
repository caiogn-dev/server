"""Pedir um produto no fim do checkout não é "observação".

13/ago, conversa real da Yeda com a Cê Saladas. O bot já tinha o resumo na tela
e estava esperando observação. Ela escreveu **"Quero salada"** — um pedido de
produto — e recebeu:

    ✅ _Anotado: Quero salada_
    💳 Como prefere pagar?

O carrinho continuou com 1 suco de R$ 12. O PIX saiu de R$ 20,00. A dona teve
que **cancelar o pedido #CE-2608135397** e refazer na mão um de **R$ 100,01**,
por áudio, com link de pagamento manual.

Causa: `_handle_notes_input` tinha uma lista de palavras que significam "sem
observação" e tratava TODO o resto como nota — inclusive nome de produto do
próprio catálogo.

Contrato: no estado de observação, texto que nomeia produto do catálogo NÃO
vira nota. Observação de verdade continua virando nota, e as palavras de pular
continuam pulando.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.automation.models import CompanyProfile
from apps.conversations.models import Conversation
from apps.stores.models import Store, StoreProduct
from apps.whatsapp.intents.handlers.interactive import InteractiveReplyHandler
from apps.whatsapp.models import WhatsAppAccount

User = get_user_model()
PHONE = '5563999619019'


class NotaNaoEngolePedidoTest(TestCase):
    def setUp(self):
        owner = User.objects.create_user(username='dona-ce', password='x')
        self.store = Store.objects.create(
            billing_exempt=True, name='Cê Saladas', slug='ce-saladas-nota', owner=owner,
        )
        self.account = WhatsAppAccount.objects.create(
            name='CeNota', phone_number_id='PHNOTA', waba_id='WNOTA',
        )
        self.store.whatsapp_account = self.account
        self.store.save(update_fields=['whatsapp_account'])
        self.profile = CompanyProfile.objects.get(store=self.store)
        self.profile.account = self.account
        CompanyProfile.objects.filter(account=self.account).exclude(pk=self.profile.pk).delete()
        self.profile.save()
        self.conversation = Conversation.objects.create(
            account=self.account, phone_number=PHONE,
        )
        for nome in ('Salada Caesar', 'Salada de Frango', 'Suco de laranja 400ml'):
            StoreProduct.objects.create(
                store=self.store, name=nome, slug=nome.lower().replace(' ', '-'),
                price=25, is_active=True,
            )

    def _handler(self):
        return InteractiveReplyHandler(self.account, self.conversation, self.profile)

    def _nota(self, texto):
        return self._handler()._handle_notes_input(texto)

    @staticmethod
    def _texto(resultado):
        """O corpo do interativo vem PRIMEIRO.

        `HandlerResult.buttons` preenche response_text com a sentinela
        "BUTTONS_SENT" — ler response_text antes devolve a sentinela e o teste
        passa sem olhar nada.
        """
        if resultado.use_interactive:
            return (resultado.interactive_data or {}).get('body') or ''
        return resultado.response_text or ''

    # --- o caso da Yeda -------------------------------------------------

    def test_quero_salada_nao_vira_observacao(self):
        resultado = self._nota('Quero salada')

        assert 'Anotado' not in self._texto(resultado), self._texto(resultado)

    def test_quero_salada_oferece_adicionar_ao_pedido(self):
        """Não basta não anotar: tem que abrir caminho pro produto."""
        resultado = self._nota('Quero salada')

        assert 'salada' in self._texto(resultado).lower(), self._texto(resultado)

    def test_nome_exato_de_produto_tambem_nao_vira_nota(self):
        texto = self._texto(self._nota('Suco de laranja 400ml'))
        assert 'Anotado' not in texto

    # --- o que NÃO pode regredir ---------------------------------------

    def test_observacao_de_verdade_continua_virando_nota(self):
        resultado = self._nota('sem cebola')

        assert 'Anotado' in self._texto(resultado), self._texto(resultado)

    def test_palavra_de_pular_continua_pulando(self):
        texto = self._texto(self._nota('não'))
        assert 'Anotado' not in texto

    def test_produto_de_outra_loja_nao_conta(self):
        """Casar catálogo alheio faria observação legítima sumir."""
        outra_dona = User.objects.create_user(username='outra-dona', password='x')
        outra = Store.objects.create(name='Outra', slug='outra-nota', owner=outra_dona)
        StoreProduct.objects.create(
            store=outra, name='Estrogonofe', slug='estrogonofe', price=30, is_active=True,
        )

        texto = self._texto(self._nota('Estrogonofe'))

        assert 'Anotado' in texto, texto

    def test_produto_inativo_nao_conta(self):
        StoreProduct.objects.create(
            store=self.store, name='Torta antiga', slug='torta-antiga',
            price=10, is_active=False,
        )
        texto = self._texto(self._nota('Torta antiga'))
        assert 'Anotado' in texto

    # --- negação manda, sempre ------------------------------------------

    def test_sem_ingrediente_e_observacao_mesmo_existindo_o_produto(self):
        """A Cê Saladas vende ingrediente avulso: "Cebola roxa" é produto.

        Sem esta regra, "sem cebola" — o exemplo que o PRÓPRIO bot dá ao pedir
        observação — casaria com o produto e deixaria de ser anotado. Trocaria
        um bug por outro pior.
        """
        StoreProduct.objects.create(
            store=self.store, name='Cebola roxa', slug='cebola-roxa',
            price=2, is_active=True,
        )

        assert 'Anotado' in self._texto(self._nota('sem cebola'))

    def test_tirar_o_ingrediente_tambem_e_observacao(self):
        StoreProduct.objects.create(
            store=self.store, name='Tomate', slug='tomate', price=2, is_active=True,
        )
        for frase in ('tirar o tomate', 'sem tomate por favor', 'retirar tomate',
                      'nada de tomate', 'não quero tomate'):
            assert 'Anotado' in self._texto(self._nota(frase)), frase

    def test_pedir_o_mesmo_ingrediente_sem_negacao_continua_sendo_produto(self):
        StoreProduct.objects.create(
            store=self.store, name='Tomate', slug='tomate2', price=2, is_active=True,
        )
        assert 'Anotado' not in self._texto(self._nota('quero tomate'))
