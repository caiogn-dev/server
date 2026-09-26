"""Operação do atendimento humano: por que a conversa caiu, o que o bot já
tinha colhido, quem assumiu, e o que o bot não entendeu.

26/09: a fila humana dizia QUEM esperava, mas não POR QUÊ nem O QUÊ. O
atendente abria a conversa e relia tudo para descobrir que o cliente já tinha
escolhido dois itens e só faltava o endereço — informação que estava na
sessão do bot o tempo todo. E o motivo aparecia como "Synced from conversation
mode switch" para quase tudo.
"""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

from apps.automation.models import AutoMessage, CompanyProfile, CustomerSession, IntentLog
from apps.conversations.models import Conversation
from apps.handover.models import ConversationHandover, HandoverLog
from apps.stores.models import Store, StoreProduct
from apps.whatsapp.models import Message, WhatsAppAccount

BASE = '/api/v1/conversations'


def _loja(dono, sufixo):
    loja = Store.objects.create(name=f'Loja {sufixo}', slug=f'loja-{sufixo}', owner=dono, status='active')
    conta = WhatsAppAccount.objects.create(
        name=f'Conta {sufixo}', phone_number_id=f'pn-{sufixo}', waba_id=f'wa-{sufixo}',
        phone_number=f'+5563900{sufixo}', display_phone_number=f'+5563900{sufixo}',
        access_token_encrypted='x', webhook_verify_token='x', owner=dono,
    )
    loja.whatsapp_account = conta
    loja.save(update_fields=['whatsapp_account'])
    return loja, conta


@pytest.fixture
def dono(db):
    return get_user_model().objects.create_user(username='dono-op', password='x', first_name='Ana')


@pytest.fixture
def loja_e_conta(dono):
    return _loja(dono, '00021')


@pytest.fixture
def cliente(dono):
    c = APIClient()
    c.force_authenticate(dono)
    return c


@pytest.fixture
def intruso_cliente(db):
    intruso = get_user_model().objects.create_user(username='intruso-op', password='x')
    _loja(intruso, '00022')
    c = APIClient()
    c.force_authenticate(intruso)
    return c


def _humana(conta, tel='5563999990201', nome='Joana', motivo='', esperando_min=12):
    from apps.conversations.services import ConversationService

    conv = Conversation.objects.create(account=conta, phone_number=tel, contact_name=nome)
    ConversationService().switch_to_human(str(conv.id), motivo=motivo)
    agora = timezone.now()
    Message.objects.create(
        account=conta, conversation=conv, whatsapp_message_id=f'in-{tel}', direction='inbound',
        message_type='text', from_number=tel, to_number=conta.phone_number,
        text_body='Oi, quero falar com alguém sobre meu pedido',
    )
    Conversation.objects.filter(pk=conv.pk).update(
        last_customer_message_at=agora - timedelta(minutes=esperando_min),
        last_agent_message_at=agora - timedelta(hours=1),
    )
    Message.objects.filter(conversation=conv).update(created_at=agora - timedelta(minutes=esperando_min))
    conv.refresh_from_db()
    return conv


def _perfil(loja):
    return CompanyProfile.objects.get(store=loja)


@pytest.mark.django_db
class TestMotivo:
    def test_eco_do_celular(self, cliente, loja_e_conta):
        _, conta = loja_e_conta
        conv = _humana(conta, motivo='Respondido pelo WhatsApp do celular')

        motivo = cliente.get(f'{BASE}/{conv.id}/contexto-do-bot/').json()['motivo']

        assert motivo['codigo'] == 'eco_do_celular'
        assert motivo['desde']

    def test_generico_com_intencao_de_atendente_vira_pediu_atendente(self, cliente, loja_e_conta):
        loja, conta = loja_e_conta
        conv = _humana(conta)  # motivo vazio → "Synced from conversation mode switch"
        IntentLog.objects.create(
            company=_perfil(loja), conversation=conv, phone_number=conv.phone_number,
            message_text='quero atendente', intent_type='human_handoff',
        )

        motivo = cliente.get(f'{BASE}/{conv.id}/contexto-do-bot/').json()['motivo']

        assert motivo == {**motivo, 'codigo': 'pediu_atendente', 'texto': 'Cliente pediu atendente'}

    def test_generico_com_eco_vira_eco_do_celular(self, cliente, loja_e_conta):
        _, conta = loja_e_conta
        conv = _humana(conta)
        Message.objects.create(
            account=conta, conversation=conv, whatsapp_message_id='eco-1', direction='outbound',
            message_type='text', from_number=conta.phone_number, to_number=conv.phone_number,
            text_body='Oiii', content={'from': conta.phone_number},
        )

        motivo = cliente.get(f'{BASE}/{conv.id}/contexto-do-bot/').json()['motivo']

        assert motivo['codigo'] == 'eco_do_celular'

    def test_ia_que_falhou_vira_bot_nao_entendeu(self, cliente, loja_e_conta):
        _, conta = loja_e_conta
        conv = _humana(conta, motivo='A IA não conseguiu responder')

        assert cliente.get(f'{BASE}/{conv.id}/contexto-do-bot/').json()['motivo']['codigo'] == 'bot_nao_entendeu'


@pytest.mark.django_db
class TestContextoDoBot:
    def test_traz_carrinho_passo_e_cliente(self, cliente, loja_e_conta):
        loja, conta = loja_e_conta
        conv = _humana(conta, motivo='Respondido pelo painel')
        produto = StoreProduct.objects.create(store=loja, name='Salada Caesar', price=Decimal('39.99'), sku='C1')
        CustomerSession.objects.create(
            company=_perfil(loja), phone_number=conv.phone_number, session_id='s-ctx',
            status=CustomerSession.SessionStatus.CART_CREATED,
            cart_data={
                'pending_items': [{'product_id': str(produto.id), 'quantity': 2}],
                'waiting_for_address': True,
                'delivery_address': 'Quadra 104 Sul',
                'delivery_fee_calculated': 13,
                'customer_notes': 'sem cebola',
                'pending_delivery_method': 'delivery',
            },
        )
        from apps.stores.models import StoreOrder
        pedidos = StoreOrder.objects.filter(store=loja).count()

        corpo = cliente.get(f'{BASE}/{conv.id}/contexto-do-bot/').json()

        assert corpo['modo'] == 'human'
        assert corpo['motivo']['codigo'] == 'atendente_assumiu'
        assert 11 * 60 <= corpo['esperando_ha_segundos'] <= 13 * 60
        assert corpo['ultima_msg_cliente'] and corpo['ultima_msg_atendente']
        assert corpo['carrinho'] == {
            'passo': 'endereco',
            'itens': [{'nome': 'Salada Caesar', 'quantidade': 2, 'preco': '39.99'}],
            'endereco': 'Quadra 104 Sul',
            'taxa': '13.00',
            'notas': 'sem cebola',
            'entrega': 'delivery',
        }
        assert corpo['cliente'] == {
            'nome': 'Joana', 'telefone': conv.phone_number, 'pedidos': pedidos, 'ultimo_pedido': None,
        }

    def test_sem_sessao_carrinho_vazio_e_nao_cria_sessao(self, cliente, loja_e_conta):
        _, conta = loja_e_conta
        conv = _humana(conta)

        corpo = cliente.get(f'{BASE}/{conv.id}/contexto-do-bot/').json()

        assert corpo['carrinho'] == {
            'passo': 'nenhum', 'itens': [], 'endereco': None, 'taxa': None, 'notas': '', 'entrega': None,
        }
        assert not CustomerSession.objects.filter(phone_number=conv.phone_number).exists()

    def test_outra_loja_nao_ve(self, intruso_cliente, loja_e_conta):
        _, conta = loja_e_conta
        conv = _humana(conta)

        assert intruso_cliente.get(f'{BASE}/{conv.id}/contexto-do-bot/').status_code == 404


@pytest.mark.django_db
class TestFilaComMotivoEEspera:
    def test_itens_trazem_espera_motivo_e_resumo(self, cliente, loja_e_conta):
        loja, conta = loja_e_conta
        _humana(conta, tel='5563999990211', nome='Recente', esperando_min=3, motivo='Respondido pelo painel')
        _humana(conta, tel='5563999990212', nome='Antiga', esperando_min=40,
                motivo='Respondido pelo WhatsApp do celular')

        corpo = cliente.get(f'{BASE}/fila-humana/?store={loja.slug}').json()

        esperando = corpo['esperando']
        assert [e['nome'] for e in esperando] == ['Antiga', 'Recente']
        assert esperando[0]['motivo']['codigo'] == 'eco_do_celular'
        assert 39 * 60 <= esperando[0]['esperando_ha_segundos'] <= 41 * 60
        assert esperando[0]['esperando_desde']
        assert esperando[0]['ultima_mensagem'].startswith('Oi, quero falar')
        assert corpo['resumo']['esperando'] == 2
        assert corpo['resumo']['em_atendimento'] == 0
        assert corpo['resumo']['mais_antiga_segundos'] == esperando[0]['esperando_ha_segundos']


@pytest.mark.django_db
class TestAssumirEDevolver:
    def test_assumir_marca_atendente_e_registra(self, cliente, dono, loja_e_conta):
        _, conta = loja_e_conta
        conv = _humana(conta, motivo='Respondido pelo WhatsApp do celular')

        r = cliente.post(f'{BASE}/{conv.id}/assumir/')

        assert r.status_code == 200, r.content
        item = r.json()
        assert item['id'] == str(conv.id)
        assert item['atendente'] == {'id': dono.id, 'nome': 'Ana'}
        conv.refresh_from_db()
        assert conv.assigned_agent_id == dono.id
        assert ConversationHandover.objects.get(conversation=conv).assigned_to_id == dono.id
        assert HandoverLog.objects.filter(conversation=conv, performed_by=dono).exists()
        # Assumir não apaga o motivo original da passagem para humano.
        assert item['motivo']['codigo'] == 'eco_do_celular'

    def test_assumir_conversa_do_bot_passa_para_humano(self, cliente, loja_e_conta):
        _, conta = loja_e_conta
        conv = Conversation.objects.create(account=conta, phone_number='5563999990221')

        r = cliente.post(f'{BASE}/{conv.id}/assumir/')

        assert r.status_code == 200, r.content
        conv.refresh_from_db()
        assert conv.mode == 'human'
        assert r.json()['motivo']['codigo'] == 'atendente_assumiu'

    def test_devolver_ao_bot(self, cliente, dono, loja_e_conta):
        _, conta = loja_e_conta
        conv = _humana(conta)
        cliente.post(f'{BASE}/{conv.id}/assumir/')

        r = cliente.post(f'{BASE}/{conv.id}/devolver-ao-bot/')

        assert r.status_code == 200, r.content
        conv.refresh_from_db()
        assert conv.mode == 'auto'
        assert conv.assigned_agent_id is None
        handover = ConversationHandover.objects.get(conversation=conv)
        assert handover.status == 'bot' and handover.assigned_to_id is None
        log = HandoverLog.objects.filter(conversation=conv).first()
        assert log.to_status == 'bot' and log.performed_by_id == dono.id

    def test_outra_loja_nao_assume_nem_devolve(self, intruso_cliente, loja_e_conta):
        _, conta = loja_e_conta
        conv = _humana(conta)

        assert intruso_cliente.post(f'{BASE}/{conv.id}/assumir/').status_code == 404
        assert intruso_cliente.post(f'{BASE}/{conv.id}/devolver-ao-bot/').status_code == 404
        conv.refresh_from_db()
        assert conv.mode == 'human' and conv.assigned_agent_id is None


def _nao_entendeu(loja, texto, conv=None, tel='5563999990301', intent='unknown', minutos=0, resposta='Não entendi 😅'):
    log = IntentLog.objects.create(
        company=_perfil(loja), conversation=conv, phone_number=tel,
        message_text=texto, intent_type=intent, response_text=resposta,
    )
    if minutos:
        IntentLog.objects.filter(pk=log.pk).update(created_at=timezone.now() - timedelta(minutes=minutos))
    return log


@pytest.mark.django_db
class TestNaoEntendi:
    def test_lista_deduplicada_mais_recentes_primeiro(self, cliente, loja_e_conta):
        loja, _ = loja_e_conta
        _nao_entendeu(loja, 'Tem Coca Zero?', minutos=30)
        _nao_entendeu(loja, 'tem coca zero', minutos=5, tel='5563999990302')
        _nao_entendeu(loja, 'aceita vale refeição', intent='fallback', minutos=10)
        _nao_entendeu(loja, 'quero o cardápio', intent='menu_request')  # entendeu: fora
        _nao_entendeu(loja, 'coisa velha', minutos=60 * 24 * 10)  # fora da janela

        r = cliente.get(f'{BASE}/nao-entendi/?store={loja.slug}&dias=7')

        assert r.status_code == 200, r.content
        linhas = r.json()
        assert [(l['texto'], l['vezes']) for l in linhas] == [
            ('tem coca zero', 2), ('aceita vale refeição', 1),
        ]
        assert set(linhas[0]) >= {'id', 'conversa_id', 'telefone', 'texto', 'quando', 'resposta_do_bot', 'vezes'}
        assert linhas[0]['telefone'] == '5563999990302'
        assert linhas[0]['resposta_do_bot'] == 'Não entendi 😅'

    def test_outra_loja_nao_ve(self, intruso_cliente, loja_e_conta):
        loja, _ = loja_e_conta
        _nao_entendeu(loja, 'segredo')

        r = intruso_cliente.get(f'{BASE}/nao-entendi/?store={loja.slug}')

        assert r.status_code in (403, 404) or r.json() == []

    def test_sem_store_lista_so_as_lojas_do_usuario(self, intruso_cliente, loja_e_conta):
        loja, _ = loja_e_conta
        _nao_entendeu(loja, 'segredo')

        assert intruso_cliente.get(f'{BASE}/nao-entendi/').json() == []

    def test_ignorar_some_da_lista(self, cliente, loja_e_conta):
        loja, _ = loja_e_conta
        _nao_entendeu(loja, 'Blá blá')
        _nao_entendeu(loja, 'bla bla!')
        _nao_entendeu(loja, 'outra coisa')

        r = cliente.post(f'{BASE}/nao-entendi/ensinar/?store={loja.slug}',
                         {'texto': 'blá blá', 'acao': 'ignorar'}, format='json')

        assert r.status_code == 200, r.content
        assert r.json()['marcadas'] == 2
        textos = [l['texto'] for l in cliente.get(f'{BASE}/nao-entendi/?store={loja.slug}').json()]
        assert textos == ['outra coisa']
        assert IntentLog.objects.filter(metadata__ignorado=True).count() == 2

    def test_ensinar_produto_grava_apelido_sem_duplicar(self, cliente, loja_e_conta):
        loja, _ = loja_e_conta
        produto = StoreProduct.objects.create(store=loja, name='Refrigerante Lata', price=Decimal('6'), sku='R1')
        _nao_entendeu(loja, 'Coquinha gelada')

        for _ in range(2):
            r = cliente.post(f'{BASE}/nao-entendi/ensinar/?store={loja.slug}', {
                'texto': 'Coquinha  Gelada', 'acao': 'produto', 'produto_id': str(produto.id),
            }, format='json')
            assert r.status_code == 200, r.content

        produto.refresh_from_db()
        assert produto.metadata['apelidos'] == ['coquinha gelada']
        assert cliente.get(f'{BASE}/nao-entendi/?store={loja.slug}').json() == []

    def test_ensinar_produto_de_outra_loja_e_recusado(self, cliente, loja_e_conta, db):
        loja, _ = loja_e_conta
        outro_dono = get_user_model().objects.create_user(username='outro-op', password='x')
        outra, _ = _loja(outro_dono, '00023')
        alheio = StoreProduct.objects.create(store=outra, name='X', price=Decimal('1'), sku='X1')

        r = cliente.post(f'{BASE}/nao-entendi/ensinar/?store={loja.slug}', {
            'texto': 'x', 'acao': 'produto', 'produto_id': str(alheio.id),
        }, format='json')

        assert r.status_code == 404
        alheio.refresh_from_db()
        assert 'apelidos' not in (alheio.metadata or {})

    def test_ensinar_resposta_cria_e_atualiza_mensagem_de_palavra_chave(self, cliente, loja_e_conta):
        loja, _ = loja_e_conta
        url = f'{BASE}/nao-entendi/ensinar/?store={loja.slug}'

        cliente.post(url, {'texto': 'Aceita VR?', 'acao': 'resposta', 'resposta': 'Aceitamos sim!'}, format='json')
        r = cliente.post(url, {'texto': 'aceita vr', 'acao': 'resposta', 'resposta': 'Aceitamos VR e VA.'},
                         format='json')

        assert r.status_code == 200, r.content
        msgs = AutoMessage.objects.filter(company__store=loja, conditions__origem='nao_entendi')
        assert msgs.count() == 1
        msg = msgs.get()
        assert msg.message_text == 'Aceitamos VR e VA.'
        assert msg.conditions['gatilhos'] == ['aceita vr']

    def test_acao_invalida_400(self, cliente, loja_e_conta):
        loja, _ = loja_e_conta
        r = cliente.post(f'{BASE}/nao-entendi/ensinar/?store={loja.slug}', {'texto': 'x', 'acao': 'x'}, format='json')
        assert r.status_code == 400

    def test_ensinar_em_loja_alheia_e_recusado(self, intruso_cliente, loja_e_conta):
        loja, _ = loja_e_conta
        _nao_entendeu(loja, 'segredo')

        r = intruso_cliente.post(f'{BASE}/nao-entendi/ensinar/?store={loja.slug}',
                                 {'texto': 'segredo', 'acao': 'ignorar'}, format='json')

        assert r.status_code in (403, 404)
        assert not IntentLog.objects.filter(metadata__ignorado=True).exists()
