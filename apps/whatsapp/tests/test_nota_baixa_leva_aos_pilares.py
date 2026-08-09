"""Nota baixa no WhatsApp abre a avaliação detalhada; nota alta vai ao Google.

O convite pós-entrega manda três botões (5★ / 3★ / ⭐). O que acontece depois de
cada um decide se a loja aprende alguma coisa:

- 5★  →  Google + cupom. Prova social pública, que traz cliente novo.
- ≤3★ →  a avaliação própria, onde estão os pilares. Cliente insatisfeito não
         vai para o Google (seria pedir uma nota pública ruim), vai para o
         canal onde ele diz O QUE deu errado — comida, entrega ou atendimento.

Antes, a nota baixa recebia só "sentimos muito, responda aqui se quiser
contar". Sem link e sem pergunta: a insatisfação virava uma estrela solta na
média, e o dono ficava sabendo que alguém não gostou sem saber de quê.
"""
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model

from apps.stores.models import Store, StoreOrder, StoreReview

User = get_user_model()


@pytest.fixture
def cenario(db):
    from apps.automation.models import CompanyProfile
    from apps.conversations.models import Conversation
    from apps.whatsapp.models import WhatsAppAccount

    dono = User.objects.create_user(username='dono-nota', email='nota@x.com', password='x')
    loja = Store.objects.create(
        name='Loja Nota', slug='loja-nota', owner=dono, status='active',
        metadata={'google_review_url': 'https://g.page/r/exemplo/review'},
    )
    conta = WhatsAppAccount.objects.create(
        name='Conta', phone_number='5563999990000', phone_number_id='1', waba_id='2',
    )
    perfil, _ = CompanyProfile.objects.get_or_create(store=loja, defaults={'name': loja.name})
    conversa = Conversation.objects.create(
        account=conta, phone_number='5563988887777', contact_name='Cliente',
    )
    pedido = StoreOrder.objects.create(
        store=loja, status=StoreOrder.OrderStatus.DELIVERED,
        payment_status=StoreOrder.PaymentStatus.PAID,
        customer_name='Cliente', customer_phone='5563988887777',
        subtotal=Decimal('50'), total=Decimal('50'),
    )
    return loja, conta, perfil, conversa, pedido


def _clicar(cenario, nota):
    """Clica num botão de avaliação e devolve o TEXTO que o cliente recebe.

    `HandlerResult` guarda o texto em `response_text` quando é mensagem simples
    e em `interactive_data['body']` quando tem botões — nos botões o
    `response_text` é só o marcador 'BUTTONS_SENT'. Testar o objeto direto
    compararia contra o `repr`, que passa em qualquer asserção de "não contém".
    """
    from apps.whatsapp.intents.handlers.interactive import InteractiveReplyHandler

    _, conta, perfil, conversa, pedido = cenario
    h = InteractiveReplyHandler(conta, conversa, perfil)
    r = h._handle_feedback_rating(f'rating_{nota}_{pedido.id}')
    return f"{r.response_text or ''} {(r.interactive_data or {}).get('body', '')}"


@pytest.mark.django_db
class TestNotaBaixa:
    def test_uma_estrela_recebe_o_link_da_avaliacao_detalhada(self, cenario):
        pedido = cenario[4]
        assert str(pedido.access_token) in _clicar(cenario, 1)

    def test_tres_estrelas_tambem(self, cenario):
        pedido = cenario[4]
        assert str(pedido.access_token) in _clicar(cenario, 3)

    def test_nota_baixa_nomeia_os_pilares(self, cenario):
        # "Conte o que aconteceu" é convite vago. Nomear comida, entrega e
        # atendimento diz ao cliente que a resposta cabe em três toques.
        corpo = _clicar(cenario, 1)
        assert 'comida' in corpo.lower()
        assert 'entrega' in corpo.lower()
        assert 'atendimento' in corpo.lower()

    def test_nota_baixa_NAO_manda_para_o_google(self, cenario):
        # Pedir avaliação pública a quem acabou de reclamar é pedir uma nota
        # ruim no Google. O insatisfeito vai para o canal privado.
        corpo = _clicar(cenario, 1)
        assert 'g.page' not in corpo
        assert 'google' not in corpo.lower()

    def test_nota_baixa_nao_oferece_cupom(self, cenario):
        # Cupom aqui soa como compra do silêncio, e o cliente ainda não disse o
        # que deu errado — que é o dado que interessa.
        corpo = _clicar(cenario, 1).lower()
        assert 'desconto' not in corpo
        assert 'cupom' not in corpo

    def test_a_nota_continua_sendo_gravada(self, cenario):
        pedido = cenario[4]
        _clicar(cenario, 1)
        assert StoreReview.objects.get(order=pedido).rating == 1


@pytest.mark.django_db
class TestNotaAlta:
    def test_cinco_estrelas_continua_indo_para_o_google_com_cupom(self, cenario):
        # O caminho que já funcionava não pode regredir.
        corpo = _clicar(cenario, 5)
        assert 'g.page' in corpo
        assert 'desconto' in corpo.lower()

    def test_cinco_estrelas_sem_google_configurado_cai_na_avaliacao_propria(self, cenario):
        loja = cenario[0]
        loja.metadata = {}
        loja.save(update_fields=['metadata'])
        pedido = cenario[4]

        corpo = _clicar(cenario, 5)
        # Sem Google não há para onde mandar: aproveita para pedir o detalhe.
        assert str(pedido.access_token) in corpo
