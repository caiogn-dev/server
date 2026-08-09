"""
A resposta de escrita do agente tem que ter o mesmo contrato da leitura.

Bug real (09/ago/2026): POST/PATCH em /api/v1/agents/ respondiam com
AgentCreateUpdateSerializer, que não tem `id` e devolve `accounts` como lista
de PKs. No painel isso virava:

  setAgent(updated) → agent.id === undefined → isEditing false
                    → o botão de salvar virava "Criar Agente"

  accounts.map(a => a.id) → [undefined] → JSON → accounts: [null]
                    → 400 {"accounts": ["Pk inválido \\"None\\" ..."]}

Um bug, dois sintomas. Leitura e escrita passam a falar a mesma língua.
"""
import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.agents.models import Agent
from apps.whatsapp.models import WhatsAppAccount


def _ids(response):
    payload = response.data
    linhas = payload["results"] if isinstance(payload, dict) and "results" in payload else payload
    return [str(a["id"]) for a in linhas]


@pytest.fixture
def dono(db):
    return get_user_model().objects.create_user(
        username="dono-agente", email="dono-agente@example.com", password="pw",
    )


@pytest.fixture
def conta(db, dono):
    return WhatsAppAccount.objects.create(
        owner=dono,
        name="Loja Teste",
        phone_number="5563999999999",
        phone_number_id="pn-1",
        waba_id="waba-1",
        access_token_encrypted="tok",
    )


@pytest.fixture
def agente(db, conta):
    a = Agent.objects.create(
        name="Atendente",
        provider=Agent.AgentProvider.NVIDIA,
        system_prompt="Original.",
    )
    a.accounts.add(conta)
    return a


@pytest.fixture
def api(dono):
    c = APIClient()
    c.force_authenticate(user=dono)
    return c


def test_patch_devolve_id(api, agente):
    r = api.patch(f"/api/v1/agents/{agente.id}/", {"system_prompt": "Novo."}, format="json")

    assert r.status_code == 200, r.data
    assert str(r.data.get("id")) == str(agente.id)


def test_patch_devolve_accounts_como_objetos(api, agente, conta):
    """O painel faz accounts.map(a => a.id); string não tem .id."""
    r = api.patch(f"/api/v1/agents/{agente.id}/", {"system_prompt": "Novo."}, format="json")

    assert r.status_code == 200, r.data
    accounts = r.data.get("accounts")
    assert isinstance(accounts, list) and accounts
    assert isinstance(accounts[0], dict)
    assert str(accounts[0]["id"]) == str(conta.id)


def test_reenviar_a_resposta_do_patch_nao_quebra(api, agente, conta):
    """Round-trip: salvar duas vezes seguidas era o que produzia accounts:[null]."""
    primeiro = api.patch(
        f"/api/v1/agents/{agente.id}/", {"system_prompt": "A."}, format="json"
    )
    assert primeiro.status_code == 200, primeiro.data

    payload = {
        "system_prompt": "B.",
        "accounts": [a["id"] for a in primeiro.data["accounts"]],
    }
    segundo = api.patch(f"/api/v1/agents/{agente.id}/", payload, format="json")

    assert segundo.status_code == 200, segundo.data
    agente.refresh_from_db()
    assert agente.system_prompt == "B."


def test_accounts_nulo_nao_derruba_o_save(api, agente):
    """Front antigo em cache continua mandando [null] — não pode virar 400."""
    r = api.patch(
        f"/api/v1/agents/{agente.id}/",
        {"system_prompt": "C.", "accounts": [None]},
        format="json",
    )

    assert r.status_code == 200, r.data
    agente.refresh_from_db()
    assert agente.system_prompt == "C."


def test_usuario_de_outro_tenant_nao_ve_o_agente(db, agente):
    """Isolamento real (era garantido por inspeção de fonte em test_is_staff_idor).

    O escopo do agente ganhou os caminhos de dono/staff da loja; nenhum deles
    pode abrir a porta para um usuário sem relação nenhuma com o tenant.
    """
    estranho = get_user_model().objects.create_user(
        username="estranho", email="estranho@example.com", password="pw",
    )
    c = APIClient()
    c.force_authenticate(user=estranho)

    lista = c.get("/api/v1/agents/")
    assert lista.status_code == 200
    assert str(agente.id) not in _ids(lista)

    assert c.get(f"/api/v1/agents/{agente.id}/").status_code == 404


def test_dono_sem_conta_whatsapp_ainda_ve_o_proprio_agente(db):
    """O sintoma 'só aparece Criar': lojista sem conta WhatsApp vinculada
    ao CompanyProfile não enxergava o agente da própria loja."""
    from apps.automation.models import CompanyProfile
    from apps.stores.tests.factories import make_store

    store = make_store()
    agente = Agent.objects.create(
        name="Agente da Loja", provider=Agent.AgentProvider.NVIDIA, system_prompt="Oi.",
    )
    perfil = CompanyProfile.objects.filter(store=store).first()
    assert perfil is not None, "CompanyProfile é criado 1:1 com a Store"
    perfil.default_agent = agente
    perfil.save(update_fields=["default_agent"])

    c = APIClient()
    c.force_authenticate(user=store.owner)
    r = c.get("/api/v1/agents/")

    assert r.status_code == 200
    assert str(agente.id) in _ids(r)


def test_post_devolve_id_para_o_painel_navegar(api, conta):
    r = api.post(
        "/api/v1/agents/",
        {
            "name": "Novo Atendente",
            "provider": Agent.AgentProvider.NVIDIA,
            "model_name": "meta/llama-3.1-70b-instruct",
            "system_prompt": "Oi.",
            "accounts": [str(conta.id)],
        },
        format="json",
    )

    assert r.status_code == 201, r.data
    assert r.data.get("id"), "sem id o painel navega para /agents/undefined"
