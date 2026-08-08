"""O recibo de entrega da Meta precisa chegar na campanha.

Em 08/ago/2026 o painel passou a exibir entrega e leitura na própria linha da
campanha, e as duas campanhas reais da Cê Saladas apareceram com "0 entregues,
0 lidas" — ambas concluídas. A mensagem CHEGOU; o número é que nunca foi
escrito: nada no código incrementava `Campaign.messages_delivered`.

O webhook de status já atualizava `Message`. Faltava o elo até
`CampaignRecipient`, que guarda o mesmo `whatsapp_message_id`.

DUAS REGRAS QUE OS TESTES FIXAM:

1. O contador é MONOTÔNICO por destinatário. A Meta reenvia o mesmo status
   (retry, duplicata do webhook) e conta dupla inflaria a entrega acima de
   100% — número impossível destrói a confiança na tela inteira.

2. `read` implica `delivered`. A Meta às vezes entrega só o `read` (leitura
   rápida, ou o `delivered` se perde). Sem isso a campanha mostraria mais
   lidas do que entregues.
"""
from django.utils import timezone

import pytest

from apps.campaigns.models import Campaign, CampaignRecipient
from apps.campaigns.services.recibos import registrar_recibo


@pytest.fixture
def conta(db):
    from apps.whatsapp.models import WhatsAppAccount

    return WhatsAppAccount.objects.create(
        name='Conta de teste',
        phone_number='5563999990000',
        phone_number_id='111',
        waba_id='222',
    )


@pytest.fixture
def campanha(db, conta):
    return Campaign.objects.create(
        account=conta,
        name='Terça fraca',
        status=Campaign.CampaignStatus.RUNNING,
        total_recipients=2,
        messages_sent=2,
    )


def _destinatario(campanha, wamid, telefone='5563999990000'):
    return CampaignRecipient.objects.create(
        campaign=campanha,
        phone_number=telefone,
        status=CampaignRecipient.RecipientStatus.SENT,
        whatsapp_message_id=wamid,
        sent_at=timezone.now(),
    )


@pytest.mark.django_db
class TestReciboDeCampanha:
    def test_entrega_conta_na_campanha(self, campanha):
        d = _destinatario(campanha, 'wamid.AAA')

        assert registrar_recibo('wamid.AAA', 'delivered') is True

        campanha.refresh_from_db()
        d.refresh_from_db()
        assert campanha.messages_delivered == 1
        assert d.status == CampaignRecipient.RecipientStatus.DELIVERED
        assert d.delivered_at is not None

    def test_webhook_repetido_nao_conta_duas_vezes(self, campanha):
        # A Meta reenvia status. Contar duas vezes daria 200% de entrega — um
        # número impossível que derruba a confiança na tela inteira.
        _destinatario(campanha, 'wamid.AAA')
        registrar_recibo('wamid.AAA', 'delivered')
        registrar_recibo('wamid.AAA', 'delivered')

        campanha.refresh_from_db()
        assert campanha.messages_delivered == 1

    def test_leitura_implica_entrega(self, campanha):
        # Leitura rápida faz a Meta mandar só o `read`. Sem isso a campanha
        # mostraria mais lidas do que entregues.
        _destinatario(campanha, 'wamid.BBB')

        registrar_recibo('wamid.BBB', 'read')

        campanha.refresh_from_db()
        assert campanha.messages_read == 1
        assert campanha.messages_delivered == 1

    def test_entrega_depois_de_leitura_nao_retrocede(self, campanha):
        # Webhook fora de ordem é comum. `delivered` chegando depois de `read`
        # não pode rebaixar o destinatário nem somar de novo.
        _destinatario(campanha, 'wamid.CCC')
        registrar_recibo('wamid.CCC', 'read')
        registrar_recibo('wamid.CCC', 'delivered')

        campanha.refresh_from_db()
        d = CampaignRecipient.objects.get(whatsapp_message_id='wamid.CCC')
        assert d.status == CampaignRecipient.RecipientStatus.READ
        assert campanha.messages_delivered == 1
        assert campanha.messages_read == 1

    def test_falha_conta_e_guarda_o_motivo(self, campanha):
        _destinatario(campanha, 'wamid.DDD')

        registrar_recibo(
            'wamid.DDD', 'failed',
            erro={'code': '131047', 'title': 'Re-engagement message'},
        )

        campanha.refresh_from_db()
        d = CampaignRecipient.objects.get(whatsapp_message_id='wamid.DDD')
        assert campanha.messages_failed == 1
        assert d.status == CampaignRecipient.RecipientStatus.FAILED
        # Sem o motivo, "1 falha" não diz se foi número errado ou janela de 24h
        # — e são ações opostas.
        assert '131047' in d.error_code
        assert d.error_message

    def test_mensagem_fora_de_campanha_e_ignorada_em_silencio(self, campanha):
        # A imensa maioria dos recibos é de conversa normal do inbox. Não achar
        # destinatário é o caso COMUM, não um erro — logar warning aqui encheria
        # o log de ruído e esconderia problema de verdade.
        assert registrar_recibo('wamid.NAO-EXISTE', 'delivered') is False
        campanha.refresh_from_db()
        assert campanha.messages_delivered == 0

    def test_status_desconhecido_nao_quebra(self, campanha):
        _destinatario(campanha, 'wamid.EEE')
        assert registrar_recibo('wamid.EEE', 'inventado') is False
        campanha.refresh_from_db()
        assert campanha.messages_delivered == 0
