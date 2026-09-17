"""Os dois insumos que faltavam para a rodada com fuso: quando cada telefone
fecha a janela e em que fuso a campanha deve pensar.

`fechamentos_por_chave` existe porque a rodada precisa comparar `fecha_em`
contra o horário-alvo de CADA destinatário (task 3) — `chaves_com_janela_aberta`
só diz dentro/fora agora, não quando cada um fecha.

`fuso_da_campanha` existe porque `horario_alvo` (task 1) recebe fuso como
parâmetro; sem isso a rodada calcularia tudo em UTC e o corte de silêncio
(8h-21h) cairia nas horas erradas para a loja.
"""
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.campaigns.models import Campaign
from apps.campaigns.services.contatos import chave_do_telefone
from apps.campaigns.services.janela import fechamentos_por_chave, fuso_da_campanha
from apps.conversations.models import Conversation
from apps.stores.models import Store
from apps.whatsapp.models import WhatsAppAccount

User = get_user_model()


class FechamentosPorChaveTest(TestCase):
    def setUp(self):
        dono = User.objects.create_user(username='dona-fechamentos', password='x')
        self.account = WhatsAppAccount.objects.create(
            name='Cê', phone_number='556300000001', phone_number_id='2',
        )
        self.store = Store.objects.create(
            billing_exempt=True, name='Cê Saladas', slug='ce-fechamentos', owner=dono,
            store_type='food', status='active', whatsapp_account=self.account,
        )
        self.campaign = Campaign.objects.create(
            account=self.account, name='Promo de amanhã',
        )
        conta_orfa = WhatsAppAccount.objects.create(
            name='Sem loja', phone_number='556300000002', phone_number_id='3',
        )
        self.campanha_orfa = Campaign.objects.create(
            account=conta_orfa, name='Campanha sem loja',
        )

    def _conversa(self, telefone, falou_em):
        return Conversation.objects.create(
            account=self.account, phone_number=telefone,
            last_customer_message_at=falou_em,
        )

    def test_devolve_quando_a_janela_de_cada_telefone_fecha(self):
        falou = timezone.now() - timedelta(hours=3)
        self._conversa('5511999990000', falou)

        mapa = fechamentos_por_chave([self.account.id])

        assert mapa[chave_do_telefone('5511999990000')] == falou + timedelta(hours=24)

    def test_quem_nunca_falou_nao_entra_no_mapa(self):
        self._conversa('5511999990001', None)
        assert fechamentos_por_chave([self.account.id]) == {}

    def test_a_conversa_mais_recente_vence_para_o_mesmo_telefone(self):
        """O nono dígito faz o mesmo cliente virar duas conversas. A janela é a
        da mensagem MAIS NOVA — pegar a antiga descartaria quem está dentro."""
        antiga = timezone.now() - timedelta(hours=20)
        nova = timezone.now() - timedelta(hours=1)
        self._conversa('551199990002', antiga)
        self._conversa('5511999990002', nova)

        mapa = fechamentos_por_chave([self.account.id])

        assert mapa[chave_do_telefone('5511999990002')] == nova + timedelta(hours=24)

    def test_fuso_vem_da_loja_da_conta(self):
        self.store.timezone = 'America/Manaus'
        self.store.save(update_fields=['timezone'])
        assert fuso_da_campanha(self.campaign) == 'America/Manaus'

    def test_sem_loja_cai_no_fuso_do_settings(self):
        assert fuso_da_campanha(self.campanha_orfa) == settings.TIME_ZONE
