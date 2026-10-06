"""O atendimento aprende só com o que deu certo — e só sugere; o dono aprova.

MEDIDO (06/10, Cê Saladas): 35 exemplos "aprendidos" sozinhos, todos com
confiança 1.0, injetados no prompt da IA:
- conversa pessoal: "se ele for na justiça ela ganha como vínculo" → uma
  promoção mandada para a Chef Ivoneth;
- erro como acerto: "qual o valor da de camarao" → "😕 Não encontrei…";
- data como verdade: "hoje (segunda) a promoção é só o Camarão", "ontem…".
A tarefa reprocessava a mesma conversa a cada 5 min (+1 uso, +0,05 de
confiança por volta) e não olhava se a conversa vendeu.

Regras novas:
1. Só aprende de conversa que virou pedido pelo WhatsApp, sem mão humana.
2. Só de resposta do BOT (não de atendente, campanha ou aviso de status).
3. Nada com data, dia da semana, horário, preço, promoção, nome do cliente
   ou cara de erro.
4. Vira SUGESTÃO desligada; só entra no prompt depois de aprovada.
5. Rodar de novo não duplica nem inventa contador.
"""
import itertools
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model

from apps.agents.learning import AgentLearningService
from apps.agents.models import Agent, AgentKnowledgeEntry
from apps.automation.models import CompanyProfile
from apps.conversations.models import Conversation
from apps.stores.models import Store, StoreOrder
from apps.whatsapp.models import Message, WhatsAppAccount

PHONE = '5563981111111'
_ids = itertools.count()


@pytest.fixture
def cenario(db):
    dono = get_user_model().objects.create_user(username='dono-apr', password='x')
    loja = Store.objects.create(name='Cê Apr', slug='ce-apr', owner=dono, status='active')
    conta = WhatsAppAccount.objects.create(name='Apr', phone_number_id='PHAPR', waba_id='WAPR')
    loja.whatsapp_account = conta
    loja.save(update_fields=['whatsapp_account'])
    agente = Agent.objects.create(name='IA Apr', provider=Agent.AgentProvider.NVIDIA)
    perfil = CompanyProfile.objects.get(store=loja)
    CompanyProfile.objects.filter(account=conta).exclude(pk=perfil.pk).delete()
    perfil.account = conta
    perfil.use_ai_agent = True
    perfil.default_agent = agente
    perfil.save()
    conversa = Conversation.objects.create(account=conta, phone_number=PHONE, contact_name='Leani Souza')
    return {'loja': loja, 'conta': conta, 'agente': agente, 'conversa': conversa}


def _msg(c, direcao, texto, origem=''):
    from django.utils import timezone
    m = Message.objects.create(
        account=c['conta'], conversation=c['conversa'],
        whatsapp_message_id=f'wamid.apr{next(_ids)}', direction=direcao, message_type='text',
        from_number=PHONE if direcao == 'inbound' else 'loja', to_number='loja' if direcao == 'inbound' else PHONE,
        text_body=texto, content={'text': texto}, metadata={'source': origem} if origem else {},
    )
    if direcao == 'inbound':
        Conversation.objects.filter(pk=c['conversa'].pk).update(last_customer_message_at=timezone.now())
    return m


def _virou_pedido(c):
    StoreOrder.objects.create(
        store=c['loja'], customer_name='Leani', customer_phone=PHONE, source='whatsapp',
        subtotal=Decimal('30'), total=Decimal('30'),
    )


RESPOSTA_BOA = (
    'Sim! Entregamos em toda a região sul de Palmas. A taxa é calculada pela distância '
    'do seu endereço, e o pedido chega quentinho porque sai direto da cozinha para o motoboy.'
)


def _aprender(c):
    return AgentLearningService(c['agente']).learn(lookback_hours=24)


def _sugestoes(c):
    return list(AgentKnowledgeEntry.objects.filter(store=c['loja'], source='sugestao'))


@pytest.mark.django_db
class TestSoAprendeDoQueDeuCerto:
    def test_conversa_que_virou_pedido_vira_sugestao_desligada(self, cenario):
        _msg(cenario, 'inbound', 'vocês entregam na região sul de palmas?')
        _msg(cenario, 'outbound', RESPOSTA_BOA, 'unified_llm')
        _virou_pedido(cenario)

        _aprender(cenario)

        [s] = _sugestoes(cenario)
        assert s.example_input == 'vocês entregam na região sul de palmas?'
        assert s.is_active is False

    def test_conversa_sem_pedido_nao_ensina_nada(self, cenario):
        _msg(cenario, 'inbound', 'vocês entregam na região sul de palmas?')
        _msg(cenario, 'outbound', RESPOSTA_BOA, 'unified_llm')
        _aprender(cenario)
        assert _sugestoes(cenario) == []

    def test_conversa_com_atendente_humano_nao_ensina(self, cenario):
        _msg(cenario, 'inbound', 'vocês entregam na região sul de palmas?')
        _msg(cenario, 'outbound', RESPOSTA_BOA, 'unified_llm')
        _msg(cenario, 'outbound', 'Oi, aqui é o Caio, já vou te ajudar com seu pedido', 'whatsapp_inbox_page')
        _virou_pedido(cenario)
        _aprender(cenario)
        assert _sugestoes(cenario) == []


@pytest.mark.django_db
class TestSoRespostaDoBotSemCoisaQueEnvelhece:
    def _par(self, cenario, resposta, origem='unified_llm'):
        _msg(cenario, 'inbound', 'vocês entregam na região sul de palmas?')
        _msg(cenario, 'outbound', resposta, origem)
        _virou_pedido(cenario)
        _aprender(cenario)
        return _sugestoes(cenario)

    def test_campanha_nao_e_resposta(self, cenario):
        assert self._par(cenario, RESPOSTA_BOA, origem='campaign') == []

    @pytest.mark.parametrize('trecho', [
        'Hoje a entrega é grátis para toda a região sul de Palmas, aproveite',
        'Amanhã (quarta) tem oferta e entregamos em toda a região sul de Palmas',
        'Entregamos sim, a loja está aberta até 17:00 e o pedido chega rapidinho',
        'Entregamos sim, a taxa para a região sul de Palmas fica R$ 9,90 nesse endereço',
        'Entregamos sim, e a promoção da Queridinha vale para toda a região sul',
        'Oi Leani! Entregamos sim em toda a região sul de Palmas, pode pedir tranquila',
        '😕 Não encontrei esse bairro na lista de entrega da região sul de Palmas, me manda o endereço',
    ])
    def test_resposta_que_envelhece_ou_falha_nao_vira_sugestao(self, cenario, trecho):
        assert self._par(cenario, trecho + ' ' + 'e qualquer dúvida é só chamar aqui no WhatsApp da loja.') == []


@pytest.mark.django_db
class TestSemDuplicarSemContadorInventado:
    def test_rodar_de_novo_nao_duplica(self, cenario):
        _msg(cenario, 'inbound', 'vocês entregam na região sul de palmas?')
        _msg(cenario, 'outbound', RESPOSTA_BOA, 'unified_llm')
        _virou_pedido(cenario)
        _aprender(cenario)
        _aprender(cenario)
        [s] = _sugestoes(cenario)
        assert s.usage_count == 0


@pytest.mark.django_db
class TestOPromptSoRecebeOAprovado:
    def test_so_manual_e_aprovado_entram(self, cenario):
        from apps.agents.graph.nodes import _load_knowledge_context
        for origem, texto in (('manual', 'MANUAL'), ('reviewed', 'APROVADO'), ('auto', 'AUTO'), ('sugestao', 'SUGESTAO')):
            AgentKnowledgeEntry.objects.create(
                agent=cenario['agente'], store=cenario['loja'], topic='outro', source=origem, is_active=True,
                example_input=f'pergunta {texto}', example_response=f'resposta {texto}',
            )
        contexto = _load_knowledge_context(cenario['agente'], cenario['loja'])
        assert 'MANUAL' in contexto and 'APROVADO' in contexto
        assert 'AUTO' not in contexto and 'SUGESTAO' not in contexto
