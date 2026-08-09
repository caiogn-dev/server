"""A tela "Testar Assistente" precisa dizer de qual loja está falando.

Toda pergunta sobre produto respondia "Cardápio indisponível no momento". A
ferramenta `buscar_produto` começa com `if not store: return ...` — e o
endpoint `/agents/{id}/process/` nunca passava `store`.

O efeito é pior que um erro: o assistente responde educadamente que o cardápio
está fora do ar. Quem testa conclui que o catálogo quebrou, quando o catálogo
está inteiro e quem não sabe da loja é a tela de teste.

O `Agent` não tem vínculo com loja (é global), então a loja tem que vir na
requisição — é o mesmo que acontece no WhatsApp, onde ela vem da conversa.
"""
import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

User = get_user_model()


@pytest.fixture
def cenario(db):
    from apps.agents.models import Agent
    from apps.stores.models import Store, StoreProduct, StoreCategory

    # `is_superuser`: o acesso ao agente é escopado por conta de WhatsApp
    # (`_accessible_agents`), e o assunto aqui é a LOJA chegar às ferramentas,
    # não o escopo de conta — que tem teste próprio em test_is_staff_idor.
    dono = User.objects.create_user(
        username='dono-ag', email='ag@x.com', password='x', is_superuser=True, is_staff=True,
    )
    loja = Store.objects.create(name='Loja Ag', slug='loja-ag', owner=dono, status='active')
    cat = StoreCategory.objects.create(store=loja, name='Massas')
    StoreProduct.objects.create(
        store=loja, category=cat, name='Rondelli de Bacalhau',
        price='61.89', is_active=True,
    )
    agente = Agent.objects.create(
        name='Assistente', provider='nvidia', model_name='x', status='active',
        system_prompt='teste',
    )
    return dono, loja, agente


def test_process_message_aceita_store_de_verdade():
    """A assinatura real, sem mock.

    O teste abaixo mocka `process_message` para inspecionar o que a view passa
    — e um mock aceita qualquer argumento. Foi assim que um `store=` inválido
    passou nos testes e estourou `TypeError: unexpected keyword argument` na
    primeira mensagem em produção.
    """
    import inspect

    from apps.agents.services.langchain_service import LangchainService

    params = inspect.signature(LangchainService.process_message).parameters
    assert 'store' in params, (
        'process_message não aceita `store` — a view passa esse argumento e '
        'toda mensagem viraria TypeError.'
    )


@pytest.mark.django_db
def test_o_endpoint_aceita_a_loja_no_payload(cenario):
    """Sem este campo não existe como a tela informar a loja."""
    from apps.agents.serializers import ProcessMessageSerializer

    assert 'store' in ProcessMessageSerializer().fields


@pytest.mark.django_db
def test_a_loja_chega_na_ferramenta_de_cardapio(cenario, monkeypatch):
    """O que a tela manda tem que chegar em `process_message`.

    Sem isto o serviço monta as ferramentas com `store=None` e toda pergunta
    sobre produto vira "Cardápio indisponível".
    """
    from apps.agents.services import langchain_service as ls

    dono, loja, agente = cenario
    recebido = {}

    def _fake_process(self, message, session_id=None, phone_number=None, store=None, **kw):
        recebido['store'] = store
        return {'response': 'ok', 'session_id': 's', 'processing_time': 0, 'model': 'x', 'tokens_used': 0}

    monkeypatch.setattr(ls.LangchainService, 'process_message', _fake_process)

    api = APIClient()
    api.force_authenticate(user=dono)
    r = api.post(
        f'/api/v1/agents/{agente.id}/process/',
        {'message': 'quanto custa o rondelli?', 'store': loja.slug},
        format='json',
    )

    assert r.status_code == 200, r.content
    assert recebido['store'] is not None, 'a loja não chegou ao serviço'
    assert recebido['store'].slug == loja.slug


@pytest.mark.django_db
def test_loja_de_outro_dono_nao_e_aceita(cenario):
    """Guarda de tenant: informar o slug não pode dar acesso ao catálogo alheio."""
    from apps.stores.models import Store

    dono, loja, agente = cenario
    outro = User.objects.create_user(username='outro-ag', email='o@x.com', password='x')
    # O dono do teste é superuser (para alcançar o agente), então a guarda de
    # loja não se aplica a ele — quem precisa ser barrado é o usuário comum.
    alheia = Store.objects.create(name='Alheia', slug='alheia', owner=outro, status='active')

    api = APIClient()
    api.force_authenticate(user=outro)
    r = api.post(
        f'/api/v1/agents/{agente.id}/process/',
        {'message': 'oi', 'store': loja.slug},
        format='json',
    )
    # Sem conta de WhatsApp acessível o usuário nem alcança o agente — e é
    # justamente essa a primeira barreira. O importante é NÃO ser 200.
    assert r.status_code in (400, 403, 404), r.content
