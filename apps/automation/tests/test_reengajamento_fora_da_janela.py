"""Reengajamento não pode gastar envio com quem está fora da janela.

Medido em 21/09, nos 3 dias seguintes à fase 1: 74 mensagens de reengajamento,
**72 falharam** — todas com 131047, "passaram mais de 24 h desde a última
mensagem do cliente". É a própria definição do público: cliente inativo há 10
a 30 dias está sempre fora da janela. Além de não chegar, cada falha disparava
`self.retry`, multiplicando o desperdício.
"""
from unittest.mock import patch

import pytest
from django.utils import timezone
from datetime import timedelta

from apps.automation.mensageiro import EnvioFalhou, janela


@pytest.mark.django_db
class TestJanelaDoReengajamento:
    def _conversa(self, quando):
        from apps.conversations.models import Conversation
        from apps.whatsapp.models import WhatsAppAccount

        conta = WhatsAppAccount.objects.create(
            name='Loja', phone_number_id=f'PH-{quando}', waba_id='WABA-R',
        )
        Conversation.objects.create(
            account=conta, phone_number='5563911112222',
            last_customer_message_at=quando,
        )
        return conta

    def test_cliente_que_falou_hoje_tem_janela_aberta(self):
        conta = self._conversa(timezone.now() - timedelta(hours=2))

        assert janela.aberta(conta, '5563911112222') is True

    def test_cliente_de_dois_dias_atras_esta_fora(self):
        conta = self._conversa(timezone.now() - timedelta(days=2))

        assert janela.aberta(conta, '5563911112222') is False

    def test_quem_nunca_falou_esta_fora(self):
        conta = self._conversa(None)

        assert janela.aberta(conta, '5563911112222') is False


def test_janela_fechada_nao_e_erro_para_repetir():
    assert janela.e_janela_fechada(EnvioFalhou('(#131047) Re-engagement message')) is True
    assert janela.e_janela_fechada(EnvioFalhou('timeout na rede')) is False


@pytest.mark.django_db
def test_reengajamento_nao_gasta_envio_fora_da_janela():
    """O caminho inteiro da tarefa, sem conversa recente: nada sai."""
    from unittest.mock import MagicMock

    from apps.stores.tests.factories import make_store
    from apps.whatsapp.models import WhatsAppAccount
    from apps.whatsapp.tasks.automation_tasks import send_reengagement_message

    conta = WhatsAppAccount.objects.create(
        name='Conta', phone_number_id='pn-janela', waba_id='wa-janela',
    )
    loja = make_store()
    envio = MagicMock()

    with patch('apps.whatsapp.tasks.automation_tasks._get_store_profile', return_value=object()), \
            patch('apps.whatsapp.tasks.automation_tasks._get_account_for_profile', return_value=conta), \
            patch('apps.whatsapp.tasks.automation_tasks._reengagement_content', return_value=('oi', [])), \
            patch('apps.automation.mensageiro.enviar_botoes', envio):
        send_reengagement_message.run('5563911113333', str(loja.id))

    envio.assert_not_called()
