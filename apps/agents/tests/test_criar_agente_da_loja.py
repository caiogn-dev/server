"""Criar o agente de uma loja e LIGAR a IA — os dois, ou nada acontece.

Pedido em 13/ago: "CRIE O AGENTE DA CE-SALADAS PARA USAR IA". O fluxo foi
melhorado e o agente nunca foi criado: a loja seguiu com `use_ai_agent=False` e
`default_agent=None`, 100% determinística, sem ninguém notar.

E o modo de falha desta feature é justamente o silêncio. Ligar a IA exige
quatro coisas simultâneas, e faltar uma não gera erro nenhum — só um bot que
continua respondendo por regex. Foi assim que o agente ficou `inactive` em 13
perfis.
"""
import pytest

from django.core.management import call_command

from apps.agents.models import Agent
from apps.automation.models import CompanyProfile
from apps.stores.tests.factories import make_store


@pytest.fixture
def loja(db):
    return make_store(name='Cê Saladas')


@pytest.fixture
def perfil(loja):
    return CompanyProfile.objects.get_or_create(store=loja)[0]


@pytest.mark.django_db
class TestCriarOAgente:
    def test_cria_o_agente_da_loja(self, loja, perfil):
        call_command('criar_agente_da_loja', loja=loja.slug)

        assert Agent.objects.filter(name__icontains='Cê Saladas').exists()

    def test_usa_NVIDIA_e_nunca_outro_provedor(self, loja, perfil):
        """Produção nunca chamou Anthropic nem OpenAI — a chave é da NVIDIA."""
        call_command('criar_agente_da_loja', loja=loja.slug)

        assert Agent.objects.get(name__icontains='Cê Saladas').provider == 'nvidia'

    def test_ativo_nos_DOIS_campos(self, loja, perfil):
        """`_agent_is_runtime_available` exige `is_active` E `status='active'`.

        Setar só um deixa o agente cadastrado e mudo — sem erro em lugar nenhum.
        """
        call_command('criar_agente_da_loja', loja=loja.slug)

        a = Agent.objects.get(name__icontains='Cê Saladas')
        assert a.is_active is True
        assert a.status == 'active'

    def test_o_perfil_passa_a_apontar_pro_agente(self, loja, perfil):
        call_command('criar_agente_da_loja', loja=loja.slug)

        perfil.refresh_from_db()
        assert perfil.default_agent is not None

    def test_a_voz_da_loja_cita_a_LOJA(self, loja, perfil):
        """Multi-tenant: prompt com nome de outra loja é o e-mail assinado 'Pastita'."""
        call_command('criar_agente_da_loja', loja=loja.slug)

        assert 'Cê Saladas' in Agent.objects.get(name__icontains='Cê Saladas').system_prompt

    def test_a_voz_PROIBE_inventar_ingrediente(self, loja, perfil):
        """A regra que o dono pediu: não falar de receita que não sabe."""
        call_command('criar_agente_da_loja', loja=loja.slug)

        prompt = Agent.objects.get(name__icontains='Cê Saladas').system_prompt.lower()
        assert 'invente' in prompt or 'inventar' in prompt
        assert 'alérgeno' in prompt or 'alergeno' in prompt

    def test_temperatura_baixa(self, loja, perfil):
        """Modelo criativo é modelo que inventa ingrediente."""
        call_command('criar_agente_da_loja', loja=loja.slug)

        assert Agent.objects.get(name__icontains='Cê Saladas').temperature <= 0.5


@pytest.mark.django_db
class TestLigarEDesligar:
    def test_criar_NAO_liga_sozinho(self, loja, perfil):
        """Ligar IA para clientes reais é decisão explícita, não efeito colateral."""
        call_command('criar_agente_da_loja', loja=loja.slug)

        perfil.refresh_from_db()
        assert perfil.use_ai_agent is False

    def test_com_ligar_a_IA_responde(self, loja, perfil):
        from apps.automation.services.context_service import AutomationContextService

        call_command('criar_agente_da_loja', loja=loja.slug, ligar=True)

        perfil.refresh_from_db()
        assert perfil.use_ai_agent is True
        assert AutomationContextService.is_ai_enabled(
            store=loja, company=perfil, allow_env_override=False,
        )

    def test_desligar_NAO_apaga_o_agente(self, loja, perfil):
        """Desligar é botão de emergência; apagar obrigaria a recadastrar."""
        call_command('criar_agente_da_loja', loja=loja.slug, ligar=True)
        call_command('criar_agente_da_loja', loja=loja.slug, desligar=True)

        perfil.refresh_from_db()
        assert perfil.use_ai_agent is False
        assert perfil.default_agent is not None


@pytest.mark.django_db
class TestOQueNaoPodeAcontecer:
    def test_rodar_duas_vezes_nao_duplica(self, loja, perfil):
        call_command('criar_agente_da_loja', loja=loja.slug)
        call_command('criar_agente_da_loja', loja=loja.slug)

        assert Agent.objects.filter(name__icontains='Cê Saladas').count() == 1

    def test_loja_inexistente_falha_alto(self, db):
        from django.core.management.base import CommandError

        with pytest.raises(CommandError):
            call_command('criar_agente_da_loja', loja='loja-que-nao-existe')

    def test_nao_mexe_no_agente_de_OUTRA_loja(self, loja, perfil):
        outra = make_store(name='Kero Kero')
        CompanyProfile.objects.get_or_create(store=outra)
        call_command('criar_agente_da_loja', loja=loja.slug, ligar=True)
        call_command('criar_agente_da_loja', loja=outra.slug)

        perfil.refresh_from_db()
        assert perfil.use_ai_agent is True
        assert perfil.default_agent.name != Agent.objects.get(
            name__icontains='Kero Kero',
        ).name
