"""Pedido pelo catálogo do WhatsApp não pode morrer em silêncio.

06/ago, pedido da Margô: o payload veio com `product_retailer_id: "kqvvc3txuf"`
— id gerado pela Meta num catálogo montado À MÃO, sem relação nenhuma com os
nossos produtos. O resolvedor só entendia `cs-<uuid>`, não casou nada, e o bot
respondeu:

    "Recebi seu pedido pelo catalogo, mas nao encontrei esses itens no
     sistema. Vou chamar um atendente para conferir."

E não chamou ninguém: era só texto, `switch_to_human` não era invocado em lugar
nenhum. A conversa ficou em modo `auto`, o bot seguiu respondendo por cima do
dono, e a venda de R$ 39,99 se perdeu.

Não dá para descobrir o produto por código — o id não carrega informação. Dá
para não perder o cliente.
"""
from decimal import Decimal
from unittest.mock import MagicMock

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.conversations.models import Conversation
from apps.stores.models import Store, StoreCategory, StoreProduct
from apps.whatsapp.models import Message, WhatsAppAccount
from apps.whatsapp.services.webhook_service import (
    WebhookService,
    resolve_catalog_products,
)

User = get_user_model()


class ResolveCatalogProductsTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username='dono-cat', password='x', email='dono-cat@real.com',
        )
        self.store = Store.objects.create(
            name='Loja Catalogo', slug='loja-catalogo', owner=self.owner, status='active',
        )
        self.cat = StoreCategory.objects.create(
            store=self.store, name='Saladas', slug='saladas-cat',
        )
        self.produto = StoreProduct.objects.create(
            store=self.store, category=self.cat, name='Especial Filé de Frango',
            slug='especial-file-cat', price=Decimal('39.99'), is_active=True,
            sku='CS-FRA', track_stock=False,
        )

    def test_casa_pelo_uuid_do_feed_autogerado(self):
        rid = f'cs-{self.produto.id}'
        self.assertEqual(
            resolve_catalog_products(self.store, [rid]), {rid: self.produto},
        )

    def test_casa_pelo_sku(self):
        """O catálogo pode ser montado com o SKU — antes isso não resolvia."""
        self.assertEqual(
            resolve_catalog_products(self.store, ['CS-FRA']), {'CS-FRA': self.produto},
        )

    def test_sku_ignora_caixa(self):
        """O Commerce Manager normaliza a caixa do id."""
        self.assertEqual(
            resolve_catalog_products(self.store, ['cs-fra']), {'cs-fra': self.produto},
        )

    def test_id_arbitrario_da_meta_nao_casa_nada(self):
        """`kqvvc3txuf` não carrega informação — tem que devolver vazio, não erro."""
        self.assertEqual(resolve_catalog_products(self.store, ['kqvvc3txuf']), {})

    def test_lista_vazia_nao_quebra(self):
        self.assertEqual(resolve_catalog_products(self.store, []), {})

    def test_produto_de_outra_loja_nao_vaza(self):
        outro_dono = User.objects.create_user(
            username='dono-cat2', password='x', email='dono-cat2@real.com',
        )
        outra = Store.objects.create(
            name='Outra', slug='outra-catalogo', owner=outro_dono, status='active',
        )
        self.assertEqual(resolve_catalog_products(outra, ['CS-FRA']), {})


class CatalogoSemCorrespondenciaTests(TestCase):
    """O caso da Margô: id irreconhecível não pode virar beco sem saída."""

    def setUp(self):
        self.service = WebhookService()
        self.owner = User.objects.create_user(
            username='dono-margo', password='x', email='dono-margo@real.com',
        )
        self.store = Store.objects.create(
            name='Loja Margo', slug='loja-margo', owner=self.owner, status='active',
        )
        self.account = WhatsAppAccount.objects.create(
            name='Conta Margo', phone_number_id='9001', waba_id='9002',
            access_token='t', phone_number='5563000000020',
        )
        self.conversa = Conversation.objects.create(
            account=self.account, phone_number='556781081742', contact_name='Margô',
        )
        self.message = Message.objects.create(
            account=self.account, conversation=self.conversa,
            whatsapp_message_id='wamid-catalogo-margo',
            direction='inbound', message_type='order', status='received',
            from_number='556781081742', to_number='5563000000020',
            content={'order': {'catalog_id': '2225244024964866', 'product_items': [
                {'product_retailer_id': 'kqvvc3txuf', 'quantity': 1,
                 'item_price': 39.99, 'currency': 'BRL'},
            ]}},
        )
        self.event = MagicMock()
        self.event.account = self.account

    def _responder(self):
        return self.service._build_catalog_order_response(
            self.event, self.message, company_profile=None, store=self.store,
        )

    def test_conversa_vai_para_humano_de_verdade(self):
        self._responder()
        self.conversa.refresh_from_db()
        self.assertEqual(
            self.conversa.mode, Conversation.ConversationMode.HUMAN,
            'prometia atendente e deixava a conversa em modo automático',
        )

    def test_resposta_nao_diz_que_o_pedido_falhou(self):
        r = self._responder()
        texto = (r.content or '').lower()
        self.assertNotIn('nao encontrei', texto)
        self.assertNotIn('não encontrei', texto)
        self.assertIn('recebi seu pedido', texto)

    def test_resposta_mostra_o_valor_para_o_atendente_fechar(self):
        r = self._responder()
        self.assertIn('39.99', (r.content or ''))

    def test_metadata_sinaliza_handoff(self):
        r = self._responder()
        self.assertTrue(r.metadata.get('handoff'))
        self.assertEqual(r.metadata.get('missing_items'), ['kqvvc3txuf'])

    def test_sem_loja_tambem_faz_handoff(self):
        r = self.service._build_catalog_order_response(
            self.event, self.message, company_profile=None, store=None,
        )
        self.conversa.refresh_from_db()
        self.assertEqual(self.conversa.mode, Conversation.ConversationMode.HUMAN)
        self.assertTrue(r.metadata.get('handoff'))
