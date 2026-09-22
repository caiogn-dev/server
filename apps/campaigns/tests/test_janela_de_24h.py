"""Campanha grátis: só para quem tem a janela de 24h aberta.

O PEDIDO DO DONO (04/09): mandar o card da promoção do dia seguinte às 20h para
quem já falou com a loja. "Já é um aviso e menos gastos, pois ainda teremos a
janela de 24h."

A ECONOMIA É REAL e a regra é da Meta, não nossa. Dentro de 24 horas contadas
da ÚLTIMA MENSAGEM QUE A CLIENTE MANDOU, a loja responde texto livre de graça.
Fora disso só sai template aprovado, que é cobrado por conversa.

O QUE ELE DESCREVEU, exatamente: cliente manda mensagem às 11h de hoje; a
promoção de amanhã sai às 20h de hoje. Vinte horas depois da mensagem dela, com
quatro de folga na janela.

A ARMADILHA QUE ESTE ARQUIVO EXISTE PARA FECHAR: a audiência tem que ser
resolvida NA HORA DO ENVIO, nunca no agendamento. Quem escolhe às 15h e agenda
para 20h estaria mandando para uma lista de 15h — e quem falou com a loja às
14h de ONTEM já está fora da janela às 20h de hoje. O envio falharia com
131047, e o pior: sem aviso, porque campanha registra erro por destinatário e
segue.

Fora da janela NÃO É ERRO, é só "não é para essa pessoa hoje". Ela não entra na
lista, e o dono vê quantas ficaram de fora.
"""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.campaigns.services.janela import (
    JANELA_HORAS, chaves_com_janela_aberta, quando_fecha,
)
from apps.conversations.models import Conversation
from apps.stores.models import Store
from apps.whatsapp.models import WhatsAppAccount

User = get_user_model()


class JanelaDe24hTest(TestCase):
    def setUp(self):
        dono = User.objects.create_user(username='dona-janela', password='x')
        self.store = Store.objects.create(
            billing_exempt=True, name='Cê Saladas', slug='ce-janela', owner=dono,
            store_type='food', status='active',
        )
        self.conta = WhatsAppAccount.objects.create(
            name='Cê', phone_number='556300000000', phone_number_id='1',
        )

    def _conversa(self, telefone, falou_ha_horas=None):
        quando = (
            timezone.now() - timedelta(hours=falou_ha_horas)
            if falou_ha_horas is not None else None
        )
        return Conversation.objects.create(
            account=self.conta, phone_number=telefone,
            last_customer_message_at=quando,
        )

    def _abertas(self, quando=None):
        return chaves_com_janela_aberta([self.conta.id], em=quando)

    # ── quem está dentro ────────────────────────────────────────────────

    def test_quem_falou_ha_pouco_esta_dentro(self):
        self._conversa('5563992618115', falou_ha_horas=2)

        self.assertIn('556392618115', self._abertas())

    def test_quem_falou_ha_23h_ainda_esta_dentro(self):
        self._conversa('5563992618115', falou_ha_horas=23)

        self.assertIn('556392618115', self._abertas())

    def test_quem_falou_ha_25h_ficou_de_fora(self):
        self._conversa('5563992618115', falou_ha_horas=25)

        self.assertEqual(self._abertas(), set())

    def test_quem_nunca_falou_fica_de_fora(self):
        self._conversa('5563992618115', falou_ha_horas=None)

        self.assertEqual(self._abertas(), set())

    # ── a armadilha do agendamento ──────────────────────────────────────

    def test_a_janela_e_medida_NA_HORA_DO_ENVIO(self):
        """O caso que o dono descreveu: mensagem às 11h, envio às 20h.

        Quem escolhe a audiência às 15h e agenda para 20h estaria mandando para
        uma lista de 15h. Esta pessoa está dentro agora e FORA às 20h de amanhã
        — a conta tem que ser refeita na hora.
        """
        self._conversa('5563992618115', falou_ha_horas=20)

        self.assertIn('556392618115', self._abertas())
        daqui_a_cinco_horas = timezone.now() + timedelta(hours=5)
        self.assertEqual(self._abertas(quando=daqui_a_cinco_horas), set())

    def test_o_horario_do_dono_funciona(self):
        """Mensagem às 11h, promoção às 20h do mesmo dia: 9 horas depois."""
        agora = timezone.now()
        onze_da_manha = agora.replace(hour=11, minute=0, second=0, microsecond=0)
        oito_da_noite = agora.replace(hour=20, minute=0, second=0, microsecond=0)
        Conversation.objects.create(
            account=self.conta, phone_number='5563992618115',
            last_customer_message_at=onze_da_manha,
        )

        self.assertIn('556392618115', self._abertas(quando=oito_da_noite))

    def test_diz_quando_a_janela_fecha(self):
        """O dono precisa saber até que horas pode agendar."""
        falou = timezone.now() - timedelta(hours=3)

        fecha = quando_fecha(falou)

        self.assertEqual(fecha, falou + timedelta(hours=JANELA_HORAS))

    # ── identidade ──────────────────────────────────────────────────────

    def test_casa_o_telefone_em_qualquer_formato(self):
        """O wa_id vem sem o nono dígito; o pedido tem com.

        Sem colapsar, metade da audiência não casaria com os segmentos de
        compra e a campanha sairia para menos gente do que podia.
        """
        self._conversa('556392618115', falou_ha_horas=1)

        self.assertIn('556392618115', self._abertas())

    def test_duas_conversas_da_mesma_pessoa_contam_como_uma(self):
        """A conversa guarda o ENDEREÇO, e o mesmo cliente pode ter dois.

        O wa_id chega sem o nono dígito e o checkout grava com ele; a conversa
        preserva os dois porque é por ali que a mensagem sai, e mexer no
        endereço faz a mensagem não chegar (medido: 1,5% de falha no formato
        legado contra 29% com o dígito acrescentado).

        Quem colapsa é a LEITURA. A janela aberta numa das conversas vale para
        a pessoa, não para o número.
        """
        self._conversa('556392618115', falou_ha_horas=30)
        self._conversa('5563992618115', falou_ha_horas=1)

        self.assertIn('556392618115', self._abertas())

    def test_so_conta_conversa_da_conta_da_loja(self):
        """Janela é por número da LOJA: outra loja não abre janela para esta."""
        outra = WhatsAppAccount.objects.create(
            name='Outra', phone_number='556311111111', phone_number_id='2',
        )
        Conversation.objects.create(
            account=outra, phone_number='5563992618115',
            last_customer_message_at=timezone.now(),
        )

        self.assertEqual(self._abertas(), set())


class CampanhaSoParaQuemEstaNaJanelaTest(TestCase):
    """A lista é refeita NA HORA DO ENVIO, não no agendamento.

    O destinatário fora da janela vira SKIPPED, não FAILED: não é erro, é "não
    é para essa pessoa hoje". Marcar como falha inflaria a taxa de erro da
    campanha e esconderia falha de verdade no meio.
    """

    def setUp(self):
        from apps.campaigns.models import Campaign
        dono = User.objects.create_user(username='dona-camp', password='x')
        self.store = Store.objects.create(
            billing_exempt=True, name='Cê Saladas', slug='ce-camp', owner=dono,
            store_type='food', status='active',
        )
        self.conta = WhatsAppAccount.objects.create(
            name='Cê', phone_number='556300000000', phone_number_id='9',
        )
        self.campanha = Campaign.objects.create(
            account=self.conta, name='Promoção de amanhã',
            message_content='Amanhã tem Tilápia a R$ 31,99',
            audience_filters={'somente_janela_aberta': True},
            created_by=dono,
        )

    def _destinatario(self, telefone):
        from apps.campaigns.models import CampaignRecipient
        return CampaignRecipient.objects.create(
            campaign=self.campanha, phone_number=telefone, contact_name='Cliente',
        )

    def _conversa(self, telefone, ha_horas):
        Conversation.objects.create(
            account=self.conta, phone_number=telefone,
            last_customer_message_at=timezone.now() - timedelta(hours=ha_horas),
        )

    def _recortar(self):
        from apps.campaigns.services.janela import recortar_para_a_janela
        return recortar_para_a_janela(self.campanha)

    def test_quem_esta_na_janela_continua_pendente(self):
        from apps.campaigns.models import CampaignRecipient
        d = self._destinatario('5563992618115')
        self._conversa('5563992618115', ha_horas=2)

        self._recortar()

        d.refresh_from_db()
        self.assertEqual(d.status, CampaignRecipient.RecipientStatus.PENDING)

    def test_quem_esta_fora_vira_SKIPPED_e_nao_FAILED(self):
        from apps.campaigns.models import CampaignRecipient
        d = self._destinatario('5563992618115')
        self._conversa('5563992618115', ha_horas=30)

        self._recortar()

        d.refresh_from_db()
        self.assertEqual(d.status, CampaignRecipient.RecipientStatus.SKIPPED)

    def test_quem_nunca_falou_com_a_loja_tambem_e_pulado(self):
        from apps.campaigns.models import CampaignRecipient
        d = self._destinatario('5563984143551')

        self._recortar()

        d.refresh_from_db()
        self.assertEqual(d.status, CampaignRecipient.RecipientStatus.SKIPPED)

    def test_devolve_a_conta_para_a_tela(self):
        self._destinatario('5563992618115')
        self._conversa('5563992618115', ha_horas=2)
        self._destinatario('5563984143551')

        resultado = self._recortar()

        self.assertEqual(resultado, {'dentro': 1, 'pulados': 1})

    def test_campanha_normal_nao_e_recortada(self):
        """Sem a marca, a campanha manda para todo mundo — é template pago."""
        from apps.campaigns.models import CampaignRecipient
        self.campanha.audience_filters = {}
        self.campanha.save(update_fields=['audience_filters'])
        d = self._destinatario('5563984143551')

        self._recortar()

        d.refresh_from_db()
        self.assertEqual(d.status, CampaignRecipient.RecipientStatus.PENDING)

    def test_nao_mexe_em_quem_ja_foi_enviado(self):
        """Campanha retomada não pode reprocessar quem já recebeu."""
        from apps.campaigns.models import CampaignRecipient
        d = self._destinatario('5563984143551')
        d.status = CampaignRecipient.RecipientStatus.SENT
        d.save(update_fields=['status'])

        self._recortar()

        d.refresh_from_db()
        self.assertEqual(d.status, CampaignRecipient.RecipientStatus.SENT)


class OEnvioRecortaAntesDeDispararTest(TestCase):
    """Campanha marcada NÃO é mais recortada no disparo — 19/set.

    O recorte media a janela uma vez só, no começo, e descartava quem só
    caberia mais tarde: em 18/set foram 352 de 380. Agora a decisão é por
    pessoa, a cada rodada (`rodada_da_janela`), e quem está fora AGORA continua
    pendente até o horário da campanha, porque pode responder no meio do dia e
    reabrir a própria janela. O recorte segue valendo para campanha sem a marca.
    """

    def setUp(self):
        from apps.campaigns.models import Campaign, CampaignRecipient
        dono = User.objects.create_user(username='dona-envio', password='x')
        self.conta = WhatsAppAccount.objects.create(
            name='Cê', phone_number='556300000000', phone_number_id='7',
        )
        self.campanha = Campaign.objects.create(
            account=self.conta, name='Promoção',
            message_content='Amanhã tem Tilápia a R$ 31,99',
            audience_filters={'somente_janela_aberta': True},
            created_by=dono,
        )
        self.dentro = CampaignRecipient.objects.create(
            campaign=self.campanha, phone_number='5563992618115',
        )
        self.fora = CampaignRecipient.objects.create(
            campaign=self.campanha, phone_number='5563984143551',
        )
        Conversation.objects.create(
            account=self.conta, phone_number='5563992618115',
            last_customer_message_at=timezone.now() - timedelta(hours=2),
        )

    def test_iniciar_a_campanha_nao_descarta_mais_quem_esta_fora_agora(self):
        from unittest.mock import patch
        from apps.campaigns.models import CampaignRecipient
        from apps.campaigns.services.campaign_service import CampaignService

        with patch.object(CampaignService, '_check_celery_connection', return_value=False), \
             patch('apps.campaigns.services.campaign_service.logger'):
            try:
                CampaignService().start_campaign(str(self.campanha.id))
            except Exception:
                # O disparo em si pode falhar sem Celery — o que importa aqui é
                # que o recorte rodou ANTES.
                pass

        self.dentro.refresh_from_db()
        self.fora.refresh_from_db()

        # Ninguém é descartado no disparo: a rodada decide pessoa por pessoa,
        # e só desiste de quem continua fora depois do horário da campanha.
        self.assertEqual(self.fora.status, CampaignRecipient.RecipientStatus.PENDING)
        self.assertEqual(self.dentro.status, CampaignRecipient.RecipientStatus.PENDING)
