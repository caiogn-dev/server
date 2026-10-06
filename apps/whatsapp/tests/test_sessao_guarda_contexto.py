"""A sessão do cliente precisa lembrar o que o bot acabou de oferecer.

MEDIDO (logs do celery, 06/10): 50× "[unified] montagem de combo falhou:
'CustomerSession' object has no attribute 'context'". Três recursos chamavam
`session.context` / `session.update_context(...)` — que só existem na sessão
de FLUXO, não na do cliente — e o erro era engolido:

1. Produto mencionado ("🥗 Magnífico Camarão") + cliente responde "2": o
   produto pendente nunca era guardado, a quantidade caía em "Como posso te
   ajudar? 👇" (28/09, "2 unidades").
2. Montagem de combo pelo chat (14/08): nunca começava.
3. A continuação da montagem rodava em TODA mensagem e estourava.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.automation.models import CompanyProfile, CustomerSession
from apps.conversations.models import Conversation
from apps.stores.models import Store, StoreProduct
from apps.whatsapp.intents.handlers.fallback import UnknownHandler
from apps.whatsapp.models import WhatsAppAccount

User = get_user_model()
PHONE = '5563985076235'


class _Base(TestCase):
    def setUp(self):
        dono = User.objects.create_user(username='dono-ctx', email='c@ctx.com', password='x')
        self.store = Store.objects.create(billing_exempt=True, name='Cê Ctx', slug='ce-ctx', owner=dono)
        self.account = WhatsAppAccount.objects.create(name='Ctx', phone_number_id='PHCTX', waba_id='WCTX')
        self.store.whatsapp_account = self.account
        self.store.save(update_fields=['whatsapp_account'])
        self.profile = CompanyProfile.objects.get(store=self.store)
        self.profile.account = self.account
        CompanyProfile.objects.filter(account=self.account).exclude(pk=self.profile.pk).delete()
        self.profile.save()
        self.conversation = Conversation.objects.create(account=self.account, phone_number=PHONE)
        self.camarao = StoreProduct.objects.create(
            store=self.store, name='Magnífico Camarão', slug='camarao', price=36.74, is_active=True,
        )

    def _unknown(self):
        return UnknownHandler(self.account, self.conversation, self.profile)

    def _sessao(self):
        return self._unknown()._get_session_manager().get_or_create_session()


class SessaoGuardaContextoTest(_Base):
    def test_update_context_persiste_e_le_de_volta(self):
        sessao = self._sessao()
        sessao.update_context('pending_product_id', str(self.camarao.id))
        fresca = CustomerSession.objects.get(pk=sessao.pk)
        self.assertEqual(fresca.context.get('pending_product_id'), str(self.camarao.id))

    def test_update_context_nao_apaga_o_carrinho(self):
        sm = self._unknown()._get_session_manager()
        sm.save_pending_order_items([{'product_id': str(self.camarao.id), 'quantity': 1, 'price': 36.74}])
        sm.get_or_create_session().update_context('pending_product_id', 'x')
        self.assertTrue(self._unknown()._get_session_manager().get_pending_order_items())


class QuantidadeDepoisDoProdutoTest(_Base):
    def _oferecer_camarao(self, minutos_atras=1):
        from datetime import timedelta
        from django.utils import timezone
        sessao = self._sessao()
        sessao.update_context('pending_product_id', str(self.camarao.id))
        sessao.update_context('pending_product_at', (timezone.now() - timedelta(minutes=minutos_atras)).isoformat())

    def _responder(self, texto):
        return self._unknown().handle({'original_message': texto, 'llm_available': False})

    def test_numero_sozinho_vira_quantidade_do_produto_oferecido(self):
        self._oferecer_camarao()
        self._responder('2')
        itens = self._unknown()._get_session_manager().get_pending_order_items()
        self.assertEqual([(i['product_id'], i['quantity']) for i in itens], [(str(self.camarao.id), 2)])

    def test_2_unidades_tambem(self):
        self._oferecer_camarao()
        self._responder('2 unidades')
        itens = self._unknown()._get_session_manager().get_pending_order_items()
        self.assertEqual([i['quantity'] for i in itens], [2])

    def test_duas_por_extenso(self):
        self._oferecer_camarao()
        self._responder('quero duas')
        itens = self._unknown()._get_session_manager().get_pending_order_items()
        self.assertEqual([i['quantity'] for i in itens], [2])

    def test_oferta_de_mais_de_30_min_nao_captura_o_numero(self):
        self._oferecer_camarao(minutos_atras=45)
        self._responder('2')
        self.assertEqual(self._unknown()._get_session_manager().get_pending_order_items(), [])


class SimDepoisDaPerguntaDaIATest(_Base):
    """05/10: a IA ofereceu "Magnífico Camarão… Quer que eu adicione no seu
    pedido?", o cliente disse "Isso" e recebeu o menu genérico "Claro! O que
    você gostaria de fazer?" — o handler fixo não enxerga o que a IA perguntou."""

    def _sim(self, llm):
        from apps.whatsapp.intents.handlers.fallback import AffirmativeHandler
        return AffirmativeHandler(self.account, self.conversation, self.profile).handle(
            {'original_message': 'Isso', 'llm_available': llm},
        )

    def test_sem_estado_fixo_o_sim_volta_para_a_ia(self):
        resultado = self._sim(llm=True)
        self.assertTrue(resultado.requires_llm)

    def test_sem_ia_continua_oferecendo_os_atalhos(self):
        resultado = self._sim(llm=False)
        self.assertIn('Cardápio', str(resultado.interactive_data))
