"""Uma pessoa, UMA sessão — o nono dígito não pode rachar o carrinho.

O WhatsApp entrega o `wa_id` de celular brasileiro SEM o nono dígito
(`556391232486`) e a conversa é gravada COM ele (`5563991232486`). O pedido
pelo catálogo é salvo com o número da MENSAGEM (`message.from_number`, sem o
9); o clique em "🛵 Entrega" lê com o número da CONVERSA (com o 9).

O SessionManager montava as variantes na mão — só formatação (cru, só
dígitos, `+dígitos`) — e nunca adotou `phone_variants`, a fonte única criada
em 26/ago justamente para o nono dígito. Resultado medido em 09/set na Cê
Saladas: duas CustomerSession criadas no mesmo minuto para a mesma cliente,
uma com o item e outra vazia, e o bot respondendo "❌ Não encontrei itens no
seu pedido" logo depois de listar o item.
"""
import pytest

from apps.automation.models import CompanyProfile, CustomerSession
from apps.automation.services.session_manager import SessionManager
from apps.stores.models import Store
from django.contrib.auth import get_user_model


@pytest.fixture
def loja(db):
    User = get_user_model()
    dono = User.objects.create_user(username='dono_sessao', email='d@s.com', password='x')
    return Store.objects.create(name='Cê Saladas', slug='ce-sessao', owner=dono)


@pytest.mark.django_db
class TestSessaoUnicaPorPessoa:
    def test_variantes_incluem_a_forma_sem_o_nono_digito(self, loja):
        gerente = SessionManager(loja, '5563991232486')
        assert '556391232486' in gerente.phone_number_variants

    def test_variantes_incluem_a_forma_com_o_nono_digito(self, loja):
        gerente = SessionManager(loja, '556391232486')
        assert '5563991232486' in gerente.phone_number_variants

    def test_carrinho_salvo_sem_o_9_e_lido_com_o_9(self, loja):
        """O caso real: catálogo salva pelo wa_id, botão lê pela conversa."""
        SessionManager(loja, '556391232486').save_pending_order_items(
            [{'product_id': 'p1', 'quantity': 1, 'unit_price': 40.99}]
        )

        itens = SessionManager(loja, '5563991232486').get_pending_order_items()

        assert len(itens) == 1, 'o carrinho foi parar numa sessão que ninguém lê'
        assert CustomerSession.objects.count() == 1, 'a mesma pessoa virou duas sessões'
