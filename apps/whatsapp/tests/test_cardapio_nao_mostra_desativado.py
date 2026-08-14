"""O cardápio do WhatsApp não pode oferecer o que o dono desativou.

13/ago, apontado pelo dono: o "suco 1" estava desativado no painel e o bot
oferecia. A raiz são dois campos que discordam — `status` (o que o painel
escreve) e `is_active` (de BaseModel, default=True, quase ninguém seta).

A vitrine pública SEMPRE usou `status` corretamente. Quem filtrava pelo campo
errado era só o caminho do bot — então o site escondia e o WhatsApp oferecia o
mesmo produto.

Medido: 24 produtos assim em produção, 6 deles na Cê Saladas, entre eles dois
sucos de R$ 12.
"""
from django.test import TestCase

from apps.automation.models import CompanyProfile
from apps.conversations.models import Conversation
from apps.stores.models import StoreProduct
from apps.stores.tests.factories import make_store
from apps.whatsapp.models import WhatsAppAccount


class CardapioNaoMostraDesativadoTest(TestCase):
    def setUp(self):
        self.store = make_store(name='Cê Saladas')
        self.store.billing_exempt = True
        self.store.save(update_fields=['billing_exempt'])
        self.account = WhatsAppAccount.objects.create(
            name='CE', phone_number_id='PHCARD', waba_id='WCARD',
        )
        self.store.whatsapp_account = self.account
        self.store.save(update_fields=['whatsapp_account'])
        CompanyProfile.objects.filter(store=self.store).exclude(account=self.account).delete()
        self.profile = CompanyProfile.objects.get(account=self.account)
        self.profile.store = self.store
        self.profile.save(update_fields=['store'])
        self.conversation = Conversation.objects.create(
            account=self.account, phone_number='5563900000009',
        )
        self.ativo = StoreProduct.objects.create(
            store=self.store, name='Suco de Acerola 400ml', slug='acerola',
            price=12, is_active=True, status='active',
        )
        self.desativado = StoreProduct.objects.create(
            store=self.store, name='Suco de laranja 400ml', slug='laranja',
            price=12, is_active=True, status='inactive',
        )

    def test_produto_desativado_fica_fora_do_cardapio(self):
        from apps.whatsapp.intents.handlers.catalog import MenuRequestHandler

        h = MenuRequestHandler(self.account, self.conversation, self.profile)
        h.store = self.store
        resultado = h.handle({'original_message': 'cardapio'})

        texto = str(resultado.response_text or '') + str(resultado.interactive_data or '')
        assert 'Suco de laranja' not in texto, texto[:400]

    def test_produto_ativo_continua_no_cardapio(self):
        """A trava não pode esvaziar o cardápio."""
        from apps.whatsapp.intents.handlers.catalog import MenuRequestHandler

        h = MenuRequestHandler(self.account, self.conversation, self.profile)
        h.store = self.store
        resultado = h.handle({'original_message': 'cardapio'})

        texto = str(resultado.response_text or '') + str(resultado.interactive_data or '')
        assert 'Acerola' in texto or 'catálogo' in texto.lower(), texto[:400]
