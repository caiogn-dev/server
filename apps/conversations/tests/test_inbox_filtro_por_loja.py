"""
O inbox tem que respeitar a loja selecionada no painel.

Bug relatado pelo dono (05/ago/2026): "o chat e a separação dos números não está
sendo feita". Conferido nos dados de produção: um mesmo usuário dono de
`ce-saladas`, `pastita` e `kero-kero` recebia as 61 conversas das três contas
misturadas numa lista só.

Duas causas somadas:
  1. `_accessible_conversations` filtra por USUÁRIO (dono/staff), não por loja —
     correto como fronteira de segurança, insuficiente como fronteira de contexto.
  2. Nada no ViewSet aceitava a loja: `filterset_fields` tinha account/status/
     mode/assigned_agent e mais nada. O dash, do seu lado, chamava
     `getConversations({})` — sem parâmetro nenhum.

Aqui trava o filtro `?store=<slug|uuid>`: a conversa de uma loja não pode
aparecer quando outra loja está selecionada. A fronteira por usuário continua
valendo por baixo — `store=` restringe, nunca amplia.
"""
import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.conversations.models import Conversation
from apps.stores.models import Store
from apps.whatsapp.models import WhatsAppAccount

User = get_user_model()


@pytest.fixture
def dono(db):
    return User.objects.create_user(username='dono_inbox', password='x')


def _loja_com_conta(dono, slug, numero, pid):
    loja = Store.objects.create(owner=dono, name=slug, slug=slug)
    conta = WhatsAppAccount.objects.create(
        phone_number_id=pid, waba_id=f'waba-{slug}',
        phone_number=numero, is_active=True, owner=dono,
    )
    conta.stores.add(loja)
    return loja, conta


def _conversa(conta, telefone):
    return Conversation.objects.create(
        account=conta, phone_number=telefone, wa_id=telefone,
        contact_name=f'Cliente {telefone}', is_active=True,
    )


@pytest.fixture
def cenario(dono):
    loja_a, conta_a = _loja_com_conta(dono, 'loja-alpha', '+5563900000001', 'pid-alpha')
    loja_b, conta_b = _loja_com_conta(dono, 'loja-beta', '+5563900000002', 'pid-beta')
    _conversa(conta_a, '5563911111111')
    _conversa(conta_a, '5563922222222')
    _conversa(conta_b, '5563933333333')
    return {'dono': dono, 'a': loja_a, 'b': loja_b, 'conta_a': conta_a, 'conta_b': conta_b}


def _get(user, **params):
    c = APIClient()
    c.force_authenticate(user=user)
    resp = c.get('/api/v1/conversations/', params)
    assert resp.status_code == 200, resp.content[:300]
    dados = resp.json()
    return dados['results'] if isinstance(dados, dict) and 'results' in dados else dados


@pytest.mark.django_db
class TestFiltroPorLoja:

    def test_sem_filtro_o_dono_ve_tudo_que_e_dele(self, cenario):
        """A fronteira por usuário continua sendo a de segurança."""
        assert len(_get(cenario['dono'])) == 3

    def test_filtrar_por_slug_traz_so_a_loja_pedida(self, cenario):
        linhas = _get(cenario['dono'], store='loja-alpha')
        assert len(linhas) == 2, 'conversa de outra loja apareceu no inbox'

    def test_a_outra_loja_traz_a_sua(self, cenario):
        linhas = _get(cenario['dono'], store='loja-beta')
        assert len(linhas) == 1
        assert linhas[0]['phone_number'] == '5563933333333'

    def test_filtrar_por_uuid_tambem_funciona(self, cenario):
        """O dash às vezes tem o id, não o slug."""
        linhas = _get(cenario['dono'], store=str(cenario['b'].id))
        assert len(linhas) == 1

    def test_loja_de_outro_dono_nao_vaza_via_parametro(self, cenario, db):
        """`store=` restringe; nunca pode ampliar o que o usuário alcança."""
        estranho = User.objects.create_user(username='estranho', password='x')
        loja_x, conta_x = _loja_com_conta(estranho, 'loja-secreta', '+5563900000009', 'pid-x')
        _conversa(conta_x, '5563999999999')
        assert _get(cenario['dono'], store='loja-secreta') == []

    def test_loja_inexistente_nao_devolve_tudo(self, cenario):
        """Falha fechada: slug errado não pode virar 'sem filtro'."""
        assert _get(cenario['dono'], store='nao-existe') == []
