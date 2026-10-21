"""API dos vigias no painel + o comando do dono pelo fluxo real do WhatsApp."""
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.stores.models import VigiaAviso, VigiaConfig, VigiaEnvio
from apps.stores.tests.factories import make_store
from apps.stores.tests.test_vigias_regras import local, pedido
from apps.stores.vigias import canal_do_dono

User = get_user_model()


@pytest.fixture
def loja(db):
    return make_store(name='Cê Saladas API')


@pytest.fixture
def cliente(loja):
    c = APIClient()
    c.force_authenticate(loja.owner)
    return c


def _url(caminho, loja):
    return f'/api/v1/stores/{caminho}?store={loja.slug}'


class TestConfig:
    def test_loja_nova_vem_desligada_sem_gravar(self, cliente, loja):
        r = cliente.get(_url('vigias/', loja))
        assert r.status_code == 200
        assert r.data['config']['ativo'] is False
        assert r.data['config']['hora_resumo'] == '08:00'
        assert {c['tipo'] for c in r.data['catalogo']} >= {'resumo', 'sem_pedido', 'sabor_em_queda'}
        assert r.data['canal']['whatsapp_conectado'] is False
        assert not VigiaConfig.objects.exists()

    def test_ligar_com_telefone_formatado(self, cliente, loja):
        r = cliente.patch(_url('vigias/', loja), {'ativo': True, 'telefone': '(63) 99911-2233',
                                                  'hora_resumo': '07:30', 'dias': [0, 1, 2, 3, 4, 5]},
                          format='json')
        assert r.status_code == 200, r.data
        c = VigiaConfig.objects.get(store=loja)
        assert c.ativo and c.telefone == '5563999112233' and str(c.hora_resumo)[:5] == '07:30'
        assert c.dias == [0, 1, 2, 3, 4, 5]

    @pytest.mark.parametrize('campo,valor', [
        ('telefone', '123'), ('hora_resumo', '25:00'), ('dias', [7]), ('dias', 'seg'),
        ('desligados', ['nao_existe']), ('email', 'dono@'),
    ])
    def test_valor_invalido_nao_grava(self, cliente, loja, campo, valor):
        r = cliente.patch(_url('vigias/', loja), {campo: valor}, format='json')
        assert r.status_code == 400 and campo in r.data['campos']
        assert not VigiaConfig.objects.filter(store=loja, telefone='123').exists()

    def test_email_grava_e_apaga(self, cliente, loja):
        r = cliente.patch(_url('vigias/', loja), {'email': ' Dono@Example.com '}, format='json')
        assert r.status_code == 200, r.data
        assert VigiaConfig.objects.get(store=loja).email == 'dono@example.com'
        cliente.patch(_url('vigias/', loja), {'email': ''}, format='json')
        assert VigiaConfig.objects.get(store=loja).email == ''

    def test_ligado_sem_dia_nenhum_nao_vale(self, cliente, loja):
        r = cliente.patch(_url('vigias/', loja), {'ativo': True, 'dias': []}, format='json')
        assert r.status_code == 400

    def test_pausar_e_retomar(self, cliente, loja):
        cliente.patch(_url('vigias/', loja), {'ativo': True}, format='json')
        assert cliente.patch(_url('vigias/', loja), {'pausado': True}, format='json').data['config']['pausado']
        assert not cliente.patch(_url('vigias/', loja), {'pausado': False}, format='json').data['config']['pausado']

    def test_loja_de_outro_dono_e_404(self, loja, db):
        outro = APIClient()
        outro.force_authenticate(User.objects.create_user(username='intruso', password='x'))
        assert outro.get(_url('vigias/', loja)).status_code == 404
        assert outro.patch(_url('vigias/', loja), {'ativo': True}, format='json').status_code == 404
        assert not VigiaConfig.objects.exists()

    def test_sem_login_e_401(self, loja):
        assert APIClient().get(_url('vigias/', loja)).status_code in (401, 403)


class TestAvisos:
    def _aviso(self, loja, chave='resumo:1', **extra):
        envio = VigiaEnvio.objects.create(store=loja, dia='2026-10-16', turno='manha', status='enviado',
                                          canal='modelo')
        return VigiaAviso.objects.create(store=loja, tipo='resumo', chave=chave, grupo='resumo',
                                         titulo='Resumo', texto='Ontem: 3 pedidos', envio=envio, **extra)

    def test_lista_so_os_da_loja(self, cliente, loja, db):
        self._aviso(loja)
        self._aviso(make_store(name='Outra'), chave='resumo:2')
        r = cliente.get(_url('vigias/avisos/', loja))
        assert [a['texto'] for a in r.data['resultados']] == ['Ontem: 3 pedidos']
        assert r.data['resultados'][0]['envio']['canal'] == 'modelo'

    def test_marcar_util(self, cliente, loja):
        aviso = self._aviso(loja)
        r = cliente.post(_url(f'vigias/avisos/{aviso.id}/util/', loja), {'util': False}, format='json')
        assert r.status_code == 200
        aviso.refresh_from_db()
        assert aviso.util is False

    def test_marcar_util_de_outra_loja_e_404(self, cliente, loja, db):
        alheio = self._aviso(make_store(name='Outra 2'), chave='resumo:9')
        r = cliente.post(_url(f'vigias/avisos/{alheio.id}/util/', loja), {'util': True}, format='json')
        assert r.status_code == 404


class TestPreviaETeste:
    def test_previa_mostra_a_mensagem_sem_gravar(self, cliente, loja):
        ontem = local(2026, 10, 15, 12)
        pedido(loja, ontem, [('Queridinha', 3, 36.99, 14)])
        with patch('django.utils.timezone.now', return_value=local(2026, 10, 16, 9, 0)):
            r = cliente.get(_url('vigias/previa/', loja))
        assert r.status_code == 200
        assert r.data['fatos'][0]['tipo'] == 'resumo'
        assert 'Vigia da Cê Saladas API' in r.data['mensagem']
        assert not VigiaAviso.objects.exists()

    def test_teste_sem_telefone_explica(self, cliente, loja):
        VigiaConfig.objects.create(store=loja, ativo=True)
        r = cliente.post(_url('vigias/teste/', loja))
        assert r.status_code == 400 and 'telefone' in r.data['error']

    def test_teste_sem_whatsapp_conectado_volta_o_motivo(self, cliente, loja):
        VigiaConfig.objects.create(store=loja, ativo=True, telefone='5563999112233')
        r = cliente.post(_url('vigias/teste/', loja))
        assert r.status_code == 409 and 'WhatsApp' in r.data['erro']
        assert not VigiaEnvio.objects.exists()

    def test_modelo_sem_whatsapp_explica(self, cliente, loja):
        r = cliente.post(_url('vigias/modelo/', loja))
        assert r.status_code == 400


@pytest.mark.django_db
class TestComandoPeloWhatsApp:
    def _montar(self):
        from apps.automation.models import CompanyProfile
        from apps.conversations.models import Conversation
        from apps.whatsapp.models import WhatsAppAccount

        loja = make_store(name='Cê Vigia')
        conta = WhatsAppAccount.objects.create(name='CeVigia', phone_number_id='PHVIG', waba_id='WVIG')
        loja.whatsapp_account = conta
        loja.save(update_fields=['whatsapp_account'])
        perfil = CompanyProfile.objects.get(store=loja)
        perfil.account = conta
        CompanyProfile.objects.filter(account=conta).exclude(pk=perfil.pk).delete()
        perfil.save()
        VigiaConfig.objects.create(store=loja, ativo=True, telefone='5563999112233')
        return loja, conta, Conversation

    def test_dono_pausa_respondendo_no_whatsapp_mesmo_em_modo_humano(self):
        from apps.automation.services.unified_service import UnifiedService

        loja, conta, Conversation = self._montar()
        conversa = Conversation.objects.create(account=conta, phone_number='5563999112233', mode='human')
        resposta = UnifiedService(conta, conversa, use_llm=False).process_message('PARAR AVISOS')
        assert resposta is not None and 'pausad' in resposta.content.lower()
        assert VigiaConfig.objects.get(store=loja).pausado_em is not None

    def test_cliente_que_escreve_parar_avisos_nao_mexe(self):
        from apps.automation.services.unified_service import UnifiedService

        loja, conta, Conversation = self._montar()
        conversa = Conversation.objects.create(account=conta, phone_number='5563988887777')
        UnifiedService(conta, conversa, use_llm=False).process_message('parar avisos')
        assert VigiaConfig.objects.get(store=loja).pausado_em is None


def test_beat_agenda_os_vigias():
    from config.celery import app

    tarefas = {e['task'] for e in app.conf.beat_schedule.values()}
    assert 'apps.stores.tasks.rodar_vigias' in tarefas


def test_corpo_do_modelo_e_valido_para_a_meta():
    corpo = canal_do_dono.CORPO
    assert corpo.count('{{1}}') == 1 and corpo.count('{{2}}') == 1
    assert not corpo.startswith('{{') and not corpo.rstrip().endswith('}}')
    assert all('\n' not in v for v in canal_do_dono.EXEMPLO)


@pytest.mark.django_db
class TestComandoAtravessaAsTravas:
    def test_webhook_nao_cala_o_comando_do_dono_em_modo_humano(self):
        from types import SimpleNamespace

        from apps.whatsapp.services.webhook_service import WebhookService

        loja = make_store(name='Cê Trava')
        VigiaConfig.objects.create(store=loja, ativo=True, telefone='5563999112233')
        conversa = SimpleNamespace(mode='human', phone_number='5563999112233')
        contexto = SimpleNamespace(store=loja, profile=None)
        servico = WebhookService.__new__(WebhookService)

        def calaria(texto, telefone='5563999112233'):
            msg = SimpleNamespace(conversation=SimpleNamespace(mode='human', phone_number=telefone),
                                  text_body=texto, id='m1')
            return servico._should_suppress_for_human_mode(msg, None, None, context=contexto)

        with patch('apps.conversations.services.atendimento_humano.devolver_ao_bot_se_venceu', return_value=False):
            assert calaria('PARAR AVISOS') is False
            assert calaria('quero uma salada') is True
            assert calaria('PARAR AVISOS', telefone='5563988887777') is True
        assert conversa.mode == 'human'

    def test_respostas_automaticas_desligadas_nao_impedem_o_comando(self):
        from apps.automation.models import CompanyProfile
        from apps.automation.services.unified_service import UnifiedService
        from apps.conversations.models import Conversation
        from apps.whatsapp.models import WhatsAppAccount

        loja = make_store(name='Cê Desligada')
        conta = WhatsAppAccount.objects.create(name='CeDes', phone_number_id='PHDES', waba_id='WDES')
        loja.whatsapp_account = conta
        loja.save(update_fields=['whatsapp_account'])
        perfil = CompanyProfile.objects.get(store=loja)
        perfil.account = conta
        perfil.auto_reply_enabled = False
        CompanyProfile.objects.filter(account=conta).exclude(pk=perfil.pk).delete()
        perfil.save()
        VigiaConfig.objects.create(store=loja, ativo=True, telefone='5563999112233')
        conversa = Conversation.objects.create(account=conta, phone_number='5563999112233')

        resposta = UnifiedService(conta, conversa, use_llm=False).process_message('parar avisos')
        assert resposta is not None and 'pausad' in resposta.content.lower()
        assert UnifiedService(conta, conversa, use_llm=False).process_message('oi') is None
