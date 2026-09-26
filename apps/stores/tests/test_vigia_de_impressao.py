"""O vigia de impressão: quem descobre que a cozinha parou de imprimir é o
sistema, não o cliente.

Medido em 24/09/2026: a Cê Saladas ficou da noite de 23/09 até a tarde de
24/09 sem imprimir — 14 comandas falhas, 10 presas no spooler do Windows.
A situação aparece na tela de Impressão; aviso por WhatsApp foi retirado a
pedido do dono (26/09).
"""
from datetime import timedelta
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.stores.models import Store, StorePrintAgent, StorePrintJob
from apps.stores.services import vigia_de_impressao as vigia

User = get_user_model()

ERRO_DA_EPSON = (
    "Printer 'EPSON TM-T20' is not ready: status=NotAvailable, jobs=10, port=ESDPRT001\n"
    "No C:\\Users\\caixa\\..."
)


def _loja(slug='loja-vigia', **extra):
    owner = User.objects.create_user(username=f'owner-{slug}', email=f'{slug}@t.com', password='x')
    return Store.objects.create(name=slug, slug=slug, owner=owner, status='active', **extra)


def _agent(store, **extra):
    _, prefix, hashed = StorePrintAgent.generate_api_key()
    campos = dict(
        store=store, name='Caixa', slug=f'caixa-{store.slug}', printer_name='EPSON TM-T20',
        api_key_prefix=prefix, api_key_hash=hashed, last_seen_at=timezone.now(),
        app_version=vigia.VERSAO_ATUAL_DO_AGENT,
    )
    campos.update(extra)
    return StorePrintAgent.objects.create(**campos)


def _job(agent, *, status, quando, erro=''):
    job = StorePrintJob.objects.create(
        store=agent.store, station=agent.station, template='kitchen_ticket',
        title='Pedido', payload={}, status=status, claimed_by=agent,
        printed_at=quando if status == StorePrintJob.JobStatus.COMPLETED else None,
        failed_at=quando if status == StorePrintJob.JobStatus.FAILED else None,
        last_error=erro,
    )
    return job


class SituacaoDoAgenteTests(TestCase):
    def setUp(self):
        self.agora = timezone.now()
        self.store = _loja()

    def test_agente_vivo_sem_falha_esta_ok(self):
        agent = _agent(self.store)
        _job(agent, status=StorePrintJob.JobStatus.COMPLETED, quando=self.agora - timedelta(minutes=5))

        s = vigia.situacao_do_agente(agent, agora=self.agora)

        self.assertEqual(s.codigo, 'ok')
        self.assertIsNone(s.desde)

    def test_agente_sem_heartbeat_ha_mais_de_tres_minutos_esta_offline(self):
        ultimo = self.agora - timedelta(minutes=4)
        agent = _agent(self.store, last_seen_at=ultimo)

        s = vigia.situacao_do_agente(agent, agora=self.agora)

        self.assertEqual(s.codigo, 'offline')
        self.assertEqual(s.desde, ultimo)
        self.assertIn('4 min', s.detalhe)

    def test_agente_que_nunca_conectou_esta_offline_desde_o_cadastro(self):
        agent = _agent(self.store, last_seen_at=None)

        s = vigia.situacao_do_agente(agent, agora=self.agora)

        self.assertEqual(s.codigo, 'offline')
        self.assertEqual(s.desde, agent.created_at)

    def test_falha_de_impressora_depois_do_ultimo_sucesso_e_impressora_indisponivel(self):
        agent = _agent(self.store)
        _job(agent, status=StorePrintJob.JobStatus.COMPLETED, quando=self.agora - timedelta(hours=20))
        primeira = self.agora - timedelta(hours=18)
        _job(agent, status=StorePrintJob.JobStatus.FAILED, quando=primeira, erro=ERRO_DA_EPSON)
        _job(agent, status=StorePrintJob.JobStatus.FAILED, quando=self.agora - timedelta(minutes=10), erro=ERRO_DA_EPSON)

        s = vigia.situacao_do_agente(agent, agora=self.agora)

        self.assertEqual(s.codigo, 'impressora_indisponivel')
        # Desde a PRIMEIRA falha do episódio, não a última: é quanto tempo a cozinha está às cegas.
        self.assertEqual(s.desde, primeira)
        self.assertEqual(s.detalhe, 'EPSON TM-T20 não responde — 10 impressões presas no Windows')

    def test_sucesso_depois_da_falha_fecha_o_episodio(self):
        agent = _agent(self.store)
        _job(agent, status=StorePrintJob.JobStatus.FAILED, quando=self.agora - timedelta(hours=2), erro=ERRO_DA_EPSON)
        _job(agent, status=StorePrintJob.JobStatus.COMPLETED, quando=self.agora - timedelta(hours=1))

        self.assertEqual(vigia.situacao_do_agente(agent, agora=self.agora).codigo, 'ok')

    def test_falha_que_nao_e_da_impressora_nao_vira_alerta(self):
        # Um template desconhecido é bug de software, não impressora parada.
        agent = _agent(self.store)
        _job(agent, status=StorePrintJob.JobStatus.FAILED, quando=self.agora - timedelta(minutes=1),
             erro='Unsupported template: xyz')

        self.assertEqual(vigia.situacao_do_agente(agent, agora=self.agora).codigo, 'ok')

    def test_offline_ganha_de_impressora_indisponivel(self):
        agent = _agent(self.store, last_seen_at=self.agora - timedelta(hours=1))
        _job(agent, status=StorePrintJob.JobStatus.FAILED, quando=self.agora - timedelta(hours=2), erro=ERRO_DA_EPSON)

        self.assertEqual(vigia.situacao_do_agente(agent, agora=self.agora).codigo, 'offline')

    def test_falha_presa_na_fila_do_windows_tambem_conta(self):
        agent = _agent(self.store)
        _job(agent, status=StorePrintJob.JobStatus.FAILED, quando=self.agora - timedelta(minutes=1),
             erro='Print job 12 stayed in queue after 15s')

        s = vigia.situacao_do_agente(agent, agora=self.agora)
        self.assertEqual(s.codigo, 'impressora_indisponivel')
        self.assertEqual(s.detalhe, 'A impressora aceitou e não imprimiu (ficou presa no Windows)')


class VersaoDoAgentTests(TestCase):
    def test_versao_igual_a_atual_nao_esta_desatualizada(self):
        self.assertFalse(vigia.versao_desatualizada(vigia.VERSAO_ATUAL_DO_AGENT))

    def test_versao_antiga_esta_desatualizada(self):
        self.assertTrue(vigia.versao_desatualizada('0.1.0'))
        self.assertTrue(vigia.versao_desatualizada('0.2.0'))

    def test_sem_versao_conta_como_desatualizada(self):
        self.assertTrue(vigia.versao_desatualizada(''))

    def test_compara_numero_a_numero_e_nao_texto(self):
        self.assertFalse(vigia.versao_desatualizada('0.10.0'))


class ApiDoPainelTests(APITestCase):
    def test_lista_de_agentes_traz_a_situacao(self):
        store = _loja(slug='loja-api')
        agent = _agent(store, app_version='0.1.0')
        _job(agent, status=StorePrintJob.JobStatus.FAILED, quando=timezone.now() - timedelta(minutes=1), erro=ERRO_DA_EPSON)
        self.client.force_authenticate(store.owner)

        resp = self.client.get('/api/v1/stores/print-agents/', {'store': store.slug})

        self.assertEqual(resp.status_code, 200, resp.content)
        dado = resp.json()
        dado = dado['results'][0] if isinstance(dado, dict) else dado[0]
        self.assertEqual(dado['situacao'], 'impressora_indisponivel')
        self.assertTrue(dado['situacao_desde'])
        self.assertEqual(dado['situacao_detalhe'], 'EPSON TM-T20 não responde — 10 impressões presas no Windows')
        self.assertTrue(dado['versao_desatualizada'])
        self.assertEqual(dado['versao_atual'], vigia.VERSAO_ATUAL_DO_AGENT)


class HeartbeatDevolveVersaoTests(APITestCase):
    def test_heartbeat_diz_ao_agent_qual_e_a_versao_atual(self):
        store = _loja(slug='loja-hb')
        raw, prefix, hashed = StorePrintAgent.generate_api_key()
        StorePrintAgent.objects.create(store=store, name='Caixa', slug='caixa-hb', api_key_prefix=prefix, api_key_hash=hashed)

        resp = self.client.post('/api/v1/stores/print/agent/heartbeat/', {'app_version': '0.1.0'},
                                format='json', HTTP_X_PRINT_AGENT_KEY=raw)

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['versao_atual'], vigia.VERSAO_ATUAL_DO_AGENT)
        self.assertTrue(resp.json()['versao_desatualizada'])
