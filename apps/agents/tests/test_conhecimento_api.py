"""API do painel para o que o dono ensinou à IA (perguntas e respostas).

A tela "Ensinar o bot" lista, edita e apaga o que foi ensinado. Escopo por
loja, como todo o resto: loja alheia é 404.
"""
import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.agents.models import Agent, AgentKnowledgeEntry
from apps.automation.models import CompanyProfile
from apps.stores.models import Store

BASE = '/api/v1/agents/conhecimento'


def _loja(dono, sufixo, com_agente=True):
    loja = Store.objects.create(name=f'Loja {sufixo}', slug=f'loja-{sufixo}', owner=dono, status='active')
    if com_agente:
        agente = Agent.objects.create(name=f'IA {sufixo}', provider=Agent.AgentProvider.NVIDIA)
        perfil = CompanyProfile.objects.get(store=loja)
        perfil.use_ai_agent = True
        perfil.default_agent = agente
        perfil.save()
    return loja


@pytest.fixture
def dono(db):
    return get_user_model().objects.create_user(username='dono-kn', password='x')


@pytest.fixture
def loja(dono):
    return _loja(dono, 'kn1')


@pytest.fixture
def cliente(dono):
    c = APIClient()
    c.force_authenticate(dono)
    return c


@pytest.fixture
def intruso(db):
    u = get_user_model().objects.create_user(username='intruso-kn', password='x')
    _loja(u, 'kn2')
    c = APIClient()
    c.force_authenticate(u)
    return c


@pytest.mark.django_db
class TestConhecimentoAPI:
    def test_criar_lista_e_apagar(self, cliente, loja):
        r = cliente.post(f'{BASE}/?store={loja.slug}', {
            'topic': 'entrega', 'example_input': 'entrega em taquaralto?',
            'example_response': 'Entregamos em Taquaralto de segunda a sexta.',
        }, format='json')
        assert r.status_code == 201, r.content
        entrada = AgentKnowledgeEntry.objects.get()
        assert entrada.store_id == loja.id
        assert entrada.source == 'manual'
        assert entrada.agent_id == CompanyProfile.objects.get(store=loja).default_agent_id

        r = cliente.get(f'{BASE}/?store={loja.slug}')
        assert r.status_code == 200
        assert [e['example_input'] for e in r.json()] == ['entrega em taquaralto?']

        r = cliente.patch(f'{BASE}/{entrada.id}/?store={loja.slug}', {'example_response': 'Sim, seg a sex.'}, format='json')
        assert r.status_code == 200, r.content
        entrada.refresh_from_db()
        assert entrada.example_response == 'Sim, seg a sex.'

        assert cliente.delete(f'{BASE}/{entrada.id}/?store={loja.slug}').status_code == 204
        assert AgentKnowledgeEntry.objects.count() == 0

    def test_automatico_nao_aparece_na_lista_do_dono(self, cliente, loja):
        agente = CompanyProfile.objects.get(store=loja).default_agent
        AgentKnowledgeEntry.objects.create(agent=agente, store=loja, source='auto',
                                           example_input='auto', example_response='x')
        assert cliente.get(f'{BASE}/?store={loja.slug}').json() == []

    def test_loja_alheia_e_404(self, cliente, intruso, loja):
        agente = CompanyProfile.objects.get(store=loja).default_agent
        e = AgentKnowledgeEntry.objects.create(agent=agente, store=loja, source='manual',
                                               example_input='segredo', example_response='x')
        assert intruso.get(f'{BASE}/?store={loja.slug}').status_code == 404
        assert intruso.delete(f'{BASE}/{e.id}/?store={loja.slug}').status_code == 404
        assert AgentKnowledgeEntry.objects.filter(pk=e.pk).exists()

    def test_loja_sem_agente_de_ia_recebe_400_claro(self, cliente, dono):
        sem = _loja(dono, 'kn3', com_agente=False)
        r = cliente.post(f'{BASE}/?store={sem.slug}', {
            'example_input': 'x', 'example_response': 'y',
        }, format='json')
        assert r.status_code == 400
        assert 'atendente de IA' in r.json()['error']


@pytest.mark.django_db
class TestSugestoesDoAtendimento:
    """O aprendizado só SUGERE (06/10); o dono aprova, edita ou descarta aqui."""

    def _sugestao(self, loja, texto='vocês entregam na região sul?'):
        from apps.automation.models import CompanyProfile
        agente = CompanyProfile.objects.get(store=loja).default_agent
        return AgentKnowledgeEntry.objects.create(
            agent=agente, store=loja, topic='entrega', source='sugestao', is_active=False,
            example_input=texto, example_response='Entregamos sim em toda a região sul.',
        )

    def test_lista_de_sugestoes_separada_do_ensinado(self, cliente, loja):
        s = self._sugestao(loja)
        ensinado = cliente.get(f'{BASE}/?store={loja.slug}').json()
        sugestoes = cliente.get(f'{BASE}/?store={loja.slug}&sugestoes=1').json()
        assert str(s.id) not in [e['id'] for e in ensinado]
        assert [e['id'] for e in sugestoes] == [str(s.id)]

    def test_aprovar_liga_e_pode_editar_a_resposta(self, cliente, loja):
        s = self._sugestao(loja)
        r = cliente.post(f'{BASE}/{s.id}/aprovar/?store={loja.slug}',
                         {'example_response': 'Entregamos sim, em toda a região sul de Palmas.'}, format='json')
        assert r.status_code == 200, r.content
        s.refresh_from_db()
        assert (s.source, s.is_active) == ('reviewed', True)
        assert s.example_response == 'Entregamos sim, em toda a região sul de Palmas.'

    def test_descartar_apaga(self, cliente, loja):
        s = self._sugestao(loja)
        assert cliente.delete(f'{BASE}/{s.id}/?store={loja.slug}').status_code == 204
        assert not AgentKnowledgeEntry.objects.filter(pk=s.pk).exists()

    def test_loja_alheia_nao_aprova(self, intruso, loja):
        s = self._sugestao(loja)
        r = intruso.post(f'{BASE}/{s.id}/aprovar/?store={loja.slug}', {}, format='json')
        assert r.status_code == 404
