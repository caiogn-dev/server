"""Resposta aos botões de avaliação pós-entrega (rating_{n}_{order_id}).

O request_feedback já enviava os botões de estrela 30min após a entrega,
mas NENHUM handler tratava o clique — o voto se perdia. Contrato:

- rating_5_{id} → cria StoreReview(rating=5) do pedido, agradece e manda o
  link da página do pedido para avaliar prato a prato.
- rating_1_{id} → cria a review e responde pedindo desculpas (sem link de
  divulgação).
- Clique repetido atualiza a nota (StoreReview é 1:1 com o pedido).
- Pedido de OUTRO telefone → não cria nada (IDOR via id chutado).
"""
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.automation.models import CompanyProfile
from apps.conversations.models import Conversation
from apps.stores.models import Store, StoreOrder, StoreReview
from apps.whatsapp.intents.handlers.interactive import InteractiveReplyHandler
from apps.whatsapp.models import WhatsAppAccount

User = get_user_model()

PHONE = '5563977770000'


class FeedbackRatingTest(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username='dono-fb', email='fb@loja.com', password='x')
        self.store = Store.objects.create(
            billing_exempt=True, name='Loja FB', slug='loja-fb', owner=self.owner,
        )
        self.account = WhatsAppAccount.objects.create(
            name='ContaFB', phone_number_id='PHFB', waba_id='WFB',
        )
        self.store.whatsapp_account = self.account
        self.store.save(update_fields=['whatsapp_account'])
        self.profile = CompanyProfile.objects.get(store=self.store)
        self.profile.account = self.account
        CompanyProfile.objects.filter(account=self.account).exclude(pk=self.profile.pk).delete()
        self.profile.save()
        self.conversation = Conversation.objects.create(account=self.account, phone_number=PHONE)
        self.order = StoreOrder.objects.create(
            store=self.store, customer_name='Clara', customer_phone=PHONE,
            subtotal=50, total=50, status='delivered', payment_status='paid',
        )

    def _click(self, reply_id):
        handler = InteractiveReplyHandler(self.account, self.conversation, self.profile)
        return handler.handle({'reply_id': reply_id, 'reply_title': '', 'original_message': ''})

    def test_rating_5_cria_review_e_agradece_com_link(self):
        result = self._click(f'rating_5_{self.order.id}')
        review = StoreReview.objects.get(order=self.order)
        self.assertEqual(review.rating, 5)
        self.assertEqual(review.store_id, self.store.id)
        body = result.interactive_data.get('body', '')
        self.assertIn('brigad', body.lower())
        self.assertIn(str(self.order.access_token), body)
        button_ids = [b['id'] for b in result.interactive_data.get('buttons', [])]
        self.assertIn(f'refer_friend_{self.order.id}', button_ids)

    def test_refer_friend_entrega_o_codigo_fixo_da_loja(self):
        """Era um INDICA-XXXX por pessoa. Virou INDICA10, igual para todos.

        O código pessoal existia para atribuir a indicação; a atribuição agora
        é o cashback de quem indicou, então o código pode ser ditável.
        """
        from apps.stores.models import StoreCoupon
        from apps.stores.services.cupons_fixos import CODIGO_DE_INDICACAO
        result = self._click(f'refer_friend_{self.order.id}')
        self.assertIn(CODIGO_DE_INDICACAO, result.response_text or '')
        coupon = StoreCoupon.objects.get(store=self.store, code=CODIGO_DE_INDICACAO)
        self.assertTrue(coupon.first_order_only)
        # Clique repetido não cria um segundo cupom
        self._click(f'refer_friend_{self.order.id}')
        self.assertEqual(
            StoreCoupon.objects.filter(store=self.store, code=CODIGO_DE_INDICACAO).count(), 1,
        )

    def test_nenhum_codigo_e_gerado_com_hash(self):
        """A regressão que este arquivo existe para impedir: 13 AVALIA5-XXXXXX
        criados em produção, ZERO usados."""
        from apps.stores.models import StoreCoupon
        self.store.metadata['google_review_url'] = 'https://g.page/r/ABC/review'
        self.store.save(update_fields=['metadata'])
        self._click(f'rating_5_{self.order.id}')
        self._click(f'review_done_{self.order.id}')
        self._click(f'refer_friend_{self.order.id}')
        for code in StoreCoupon.objects.filter(store=self.store).values_list('code', flat=True):
            self.assertFalse(
                code.startswith(('AVALIA5-', 'INDICA-', 'AMIGO5-')),
                f'cupom gerado com hash voltou: {code}',
            )

    def test_rating_1_cria_review_e_pede_desculpas(self):
        result = self._click(f'rating_1_{self.order.id}')
        self.assertEqual(StoreReview.objects.get(order=self.order).rating, 1)
        text = (result.response_text or '').lower()
        self.assertTrue('desculp' in text or 'sentimos' in text, text)

    def test_clique_repetido_atualiza_nota(self):
        self._click(f'rating_3_{self.order.id}')
        self._click(f'rating_5_{self.order.id}')
        # Escopado ao pedido: o count() global media resíduo de outras suítes
        # no banco de teste compartilhado e falhava sozinho (7 != 1).
        self.assertEqual(StoreReview.objects.filter(order=self.order).count(), 1)
        self.assertEqual(StoreReview.objects.get(order=self.order).rating, 5)

    def test_rating_5_com_google_url_oferece_botao_de_recompensa(self):
        self.store.metadata['google_review_url'] = 'https://g.page/r/ABC/review'
        self.store.save(update_fields=['metadata'])
        result = self._click(f'rating_5_{self.order.id}')
        self.assertEqual(StoreReview.objects.get(order=self.order).rating, 5)
        self.assertTrue(result.use_interactive, result.response_text)
        body = result.interactive_data.get('body', '')
        self.assertIn('g.page/r/ABC/review', body)
        button_ids = [b['id'] for b in result.interactive_data.get('buttons', [])]
        self.assertIn(f'review_done_{self.order.id}', button_ids)
        # 5★ TAMBÉM recebe o convite para indicar. Antes o ramo do Google
        # retornava antes e escondia esse botão de quem mais indicaria — e
        # como nenhuma das 42 avaliações da loja é 4★, ele nunca apareceu.
        self.assertIn(f'refer_friend_{self.order.id}', button_ids)

    def test_review_done_entrega_o_codigo_fixo_uma_vez(self):
        from apps.stores.models import StoreCoupon
        from apps.stores.services.cupons_fixos import CODIGO_DE_FEEDBACK
        self.store.metadata['google_review_url'] = 'https://g.page/r/ABC/review'
        self.store.save(update_fields=['metadata'])
        self._click(f'rating_5_{self.order.id}')

        result = self._click(f'review_done_{self.order.id}')
        coupon = StoreCoupon.objects.get(store=self.store, code=CODIGO_DE_FEEDBACK)
        self.assertEqual(coupon.discount_type, 'percentage')
        self.assertEqual(float(coupon.discount_value), 10.0)
        self.assertEqual(coupon.usage_limit, 1000)
        # O limite por pessoa saiu do código único e virou regra do cupom
        self.assertEqual(coupon.usage_limit_per_user, 1)
        self.assertIn(CODIGO_DE_FEEDBACK, result.response_text or '')

        # Segundo clique NÃO cria outro cupom; reapresenta o mesmo código
        result2 = self._click(f'review_done_{self.order.id}')
        self.assertEqual(
            StoreCoupon.objects.filter(store=self.store, code=CODIGO_DE_FEEDBACK).count(), 1,
        )
        self.assertIn(CODIGO_DE_FEEDBACK, result2.response_text or '')

    def test_review_done_de_outro_telefone_nao_gera_cupom(self):
        from apps.stores.models import StoreCoupon
        other = StoreOrder.objects.create(
            store=self.store, customer_name='Outro', customer_phone='5563900008888',
            subtotal=10, total=10, status='delivered',
        )
        self._click(f'review_done_{other.id}')
        self.assertEqual(StoreCoupon.objects.filter(store=self.store).count(), 0)

    def test_pedido_de_outro_telefone_nao_avalia(self):
        other = StoreOrder.objects.create(
            store=self.store, customer_name='Outro', customer_phone='5563900009999',
            subtotal=10, total=10, status='delivered',
        )
        result = self._click(f'rating_5_{other.id}')
        self.assertFalse(StoreReview.objects.filter(order=other).exists())
        self.assertTrue(result.response_text)


class RegraDeQuemVaiProGoogleTest(FeedbackRatingTest):
    """Decisão do dono (21/09): 4 ou 5 estrelas vão para o Google; 3 ou menos
    vêm para o formulário da casa.

    O formulário próprio existe para ENTENDER o que deu errado, e nota alta
    não tem o que explicar. Já pedir nota pública a quem acabou de reclamar é
    pedir uma nota ruim no Google.

    Antes só o 5★ recebia o convite do Google: a regra estava escrita para o
    número, não para a intenção — e a intenção é "cliente satisfeito".
    """

    def _com_google(self):
        self.store.metadata['google_review_url'] = 'https://g.page/r/ABC/review'
        self.store.save(update_fields=['metadata'])

    def test_nota_4_tambem_vai_para_o_google(self):
        self._com_google()

        resultado = self._click(f'rating_4_{self.order.id}')

        corpo = resultado.interactive_data.get('body', '')
        self.assertIn('g.page/r/ABC/review', corpo)

    def test_nota_3_vai_para_o_formulario_da_casa(self):
        self._com_google()

        resultado = self._click(f'rating_3_{self.order.id}')

        texto = resultado.response_text or ''
        self.assertNotIn('g.page', texto)
        self.assertIn(str(self.order.access_token), texto)
