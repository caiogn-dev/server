"""Um texto só para pedir a localização — e nenhum "alfinete".

Dono, 06/11: "a mensagem de localização para 'clicar no alfinete' deixa
subentendido, seja mais simples e claro". No WhatsApp não existe alfinete
para o cliente tocar: o caminho é o clipe 📎 (Android) ou o + (iPhone) →
Localização → Enviar localização atual. Cada handler e cada prompt do LLM
tinha a sua versão do pedido; agora todos usam `PEDIR_LOCALIZACAO`.
"""
import ast
from pathlib import Path
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.whatsapp.pedir_localizacao import PEDIR_LOCALIZACAO

APPS = Path(__file__).resolve().parents[2]
PROIBICAO = 'NUNCA use a palavra "alfinete"'


def test_texto_canonico_e_passo_a_passo_nas_duas_plataformas():
    t = PEDIR_LOCALIZACAO
    assert '📎' in t
    assert 'iPhone' in t and '+' in t
    assert '*Localização*' in t
    assert '*Enviar localização atual*' in t
    assert 'número e bairro' in t
    assert 'alfinete' not in t.lower()
    assert len(t) < 260


def _strings_do_codigo():
    for arquivo in APPS.rglob('*.py'):
        partes = arquivo.relative_to(APPS).parts
        if 'tests' in partes or 'migrations' in partes or arquivo.name.startswith('test_'):
            continue
        arvore = ast.parse(arquivo.read_text(encoding='utf-8'))
        # Docstring é documentação, não sai para o cliente.
        docstrings = {
            id(no.body[0].value) for no in ast.walk(arvore)
            if isinstance(no, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
            and no.body and isinstance(no.body[0], ast.Expr)
            and isinstance(no.body[0].value, ast.Constant)
        }
        for no in ast.walk(arvore):
            if id(no) in docstrings:
                continue
            if isinstance(no, ast.Constant) and isinstance(no.value, str):
                yield arquivo, no.lineno, no.value


def test_nenhum_texto_do_bot_fala_em_alfinete():
    achados = [
        f'{arquivo.relative_to(APPS)}:{linha}'
        for arquivo, linha, texto in _strings_do_codigo()
        if 'alfinete' in texto.lower() and PROIBICAO not in texto
    ]
    assert achados == []


def test_regra_do_llm_traz_o_texto_e_proibe_alfinete():
    from apps.agents.graph.nodes import REGRA_PEDIR_LOCALIZACAO
    from apps.whatsapp.pedir_localizacao import REGRA_LLM_PEDIR_LOCALIZACAO

    assert REGRA_PEDIR_LOCALIZACAO is REGRA_LLM_PEDIR_LOCALIZACAO
    assert PEDIR_LOCALIZACAO in REGRA_LLM_PEDIR_LOCALIZACAO
    assert PROIBICAO in REGRA_LLM_PEDIR_LOCALIZACAO


def test_prompt_do_grafo_leva_a_regra(db):
    from apps.agents.graph.nodes import _build_system_prompt
    from apps.agents.models import Agent
    from apps.stores.tests.factories import make_store
    from apps.whatsapp.pedir_localizacao import REGRA_LLM_PEDIR_LOCALIZACAO

    agent = Agent.objects.create(name='A', provider=Agent.AgentProvider.NVIDIA,
                                 system_prompt='', context_prompt='')
    state = {'store': make_store(), 'messages': [], 'store_context': 'x', 'delivery_info': 'x',
             'customer_context': '', 'knowledge_context': ''}
    prompt = _build_system_prompt(state, agent)
    assert REGRA_LLM_PEDIR_LOCALIZACAO in prompt
    assert 'alfinete' not in prompt.replace(PROIBICAO, '')


def test_prompt_do_langchain_leva_a_regra():
    fonte = (APPS / 'agents/services/langchain_service.py').read_text(encoding='utf-8')
    assert fonte.count('REGRA_LLM_PEDIR_LOCALIZACAO') >= 3  # import + 2 blocos de conduta


def test_info_de_entrega_sem_endereco_usa_o_texto():
    from apps.whatsapp.intents.handlers.base import IntentHandler

    class _H(IntentHandler):
        def handle(self, intent_data):  # pragma: no cover
            return None

    h = _H.__new__(_H)
    h.store = MagicMock(delivery_enabled=True, pickup_enabled=False, min_order_value=None,
                        address='', city='Palmas')
    sm = MagicMock()
    sm.get_delivery_address_info.return_value = {}
    h._get_session_manager = lambda: sm

    assert PEDIR_LOCALIZACAO in h._build_delivery_info_text()


def test_pedido_de_endereco_dos_botoes_usa_o_texto():
    from apps.whatsapp.intents.handlers.interactive import InteractiveReplyHandler

    assert PEDIR_LOCALIZACAO in InteractiveReplyHandler._ASK_ADDRESS_TEXT


def test_respostas_de_frete_do_agente_usam_o_texto():
    from apps.agents.services.langchain_service import LangchainService

    assert PEDIR_LOCALIZACAO in LangchainService._PECA_LOCALIZACAO

    svc = LangchainService.__new__(LangchainService)
    store = MagicMock(default_delivery_fee=0)
    with patch.object(LangchainService, '_match_fixed_delivery_zone_from_text', return_value=None), \
            patch.object(LangchainService, '_looks_like_delivery_address', return_value=False):
        resposta = svc._get_delivery_fee_runtime_reply('quanto é a taxa de entrega?', store=store)
    assert PEDIR_LOCALIZACAO in resposta

    with patch.object(LangchainService, '_match_fixed_delivery_zone_from_text', return_value=None), \
            patch.object(LangchainService, '_looks_like_delivery_address', return_value=True), \
            patch.object(LangchainService, '_cotar_endereco', side_effect=RuntimeError('geo fora')):
        resposta = svc._get_delivery_fee_runtime_reply('Quadra 110 Sul Alameda 3 entrega', store=store)
    assert PEDIR_LOCALIZACAO in resposta


User = get_user_model()
GEO_SUL = {'lat': -10.270231, 'lng': -48.3454664,
           'formatted_address': 'Alameda 19, 53 - 03 - Plano Diretor Sul, Palmas - TO, Brasil', 'address': {}}


class CaminhosDoCheckoutTest(TestCase):
    def setUp(self):
        from apps.automation.models import CompanyProfile
        from apps.conversations.models import Conversation
        from apps.stores.models import Store
        from apps.whatsapp.intents.handlers.interactive import InteractiveReplyHandler
        from apps.whatsapp.models import WhatsAppAccount

        owner = User.objects.create_user(username='dona-loc', password='x')
        store = Store.objects.create(billing_exempt=True, name='Loja Loc', slug='loja-loc',
                                     owner=owner, city='Palmas')
        account = WhatsAppAccount.objects.create(name='Loc', phone_number_id='PHLOC', waba_id='WLOC')
        store.whatsapp_account = account
        store.save(update_fields=['whatsapp_account'])
        profile = CompanyProfile.objects.get(store=store)
        profile.account = account
        CompanyProfile.objects.filter(account=account).exclude(pk=profile.pk).delete()
        profile.save()
        conversation = Conversation.objects.create(account=account, phone_number='5563900000001')
        self.handler = InteractiveReplyHandler(account, conversation, profile)

    @staticmethod
    def _texto(r):
        if r.use_interactive:
            return (r.interactive_data or {}).get('body') or ''
        return r.response_text or ''

    def test_endereco_de_outro_setor_pede_com_o_texto(self):
        with patch('apps.stores.services.geo.geo_service.localizar', return_value=GEO_SUL):
            r = self.handler._handle_address_input('Na 307 norte Al 19 lote 53')
        texto = self._texto(r)
        self.assertIn('307 Norte', texto)
        self.assertIn(PEDIR_LOCALIZACAO, texto)

    def test_endereco_nao_achado_pede_com_o_texto_nas_duas_tentativas(self):
        with patch('apps.stores.services.geo.geo_service.localizar', return_value=None), \
                patch.object(type(self.handler), '_endereco_com_quadra', lambda self, sm, texto: texto):
            primeira = self.handler._handle_address_input('lugar que não existe')
            segunda = self.handler._handle_address_input('desisto')
        self.assertIn(PEDIR_LOCALIZACAO, self._texto(primeira))
        self.assertIn(PEDIR_LOCALIZACAO, self._texto(segunda))

    def test_sim_ambiguo_esperando_endereco_pede_com_o_texto(self):
        from apps.whatsapp.intents.handlers.fallback import AffirmativeHandler

        h = AffirmativeHandler(self.handler.account, self.handler.conversation, self.handler.company_profile)
        sm = h._get_session_manager()
        sm.get_or_create_session()
        sm.set_waiting_for_address(True)
        r = h.handle({'original_message': 'sim'})
        self.assertIn(PEDIR_LOCALIZACAO, self._texto(r))
