"""Uma pessoa, uma conversa — mesmo com o nono dígito indo e vindo.

A Meta entrega o wa_id brasileiro SEM o nono dígito (`556384143551`); o pedido
feito no site grava COM ele (`5563984143551`). Como `Conversation` é única por
(account, phone_number), a mesma cliente virava duas threads na mesma conta: a
real, com o histórico, e uma fantasma só com as notificações que o sistema
mandou.

`_get_or_create_conversation` já procurava por `phone_variants`, mas ordenava
por `-last_message_at` e pegava a mais recente — então a mensagem caía numa ou
noutra conforme quem tinha sido mexida por último. Em 10/ago isso aconteceu duas
vezes em 3 minutos com a mesma cliente: 15:57 na fantasma, 16:00 na real.

Contrato:

- a conversa CANÔNICA é a que tem conversa de verdade (mensagem recebida do
  cliente), não a mais recente;
- o desempate é determinístico e não depende de quem escreveu por último;
- contas diferentes NUNCA se fundem — a mesma pessoa falando com Cê Saladas e
  com Pastita são duas conversas legítimas.
"""
from django.test import TestCase

from apps.conversations.models import Conversation
from apps.whatsapp.models import Message, WhatsAppAccount
from apps.whatsapp.services.message_service import MessageService


def _conversa(account, phone, **kw):
    return Conversation.objects.create(account=account, phone_number=phone, **kw)


_contador = iter(range(1, 10_000))


def _msg(conversation, direction, texto='oi'):
    # whatsapp_message_id é único: sem um valor distinto por mensagem, a segunda
    # criação do teste morre com duplicate key e parece bug de produção.
    return Message.objects.create(
        account=conversation.account,
        conversation=conversation,
        whatsapp_message_id=f'wamid.TESTE{next(_contador)}',
        direction=direction,
        message_type='text',
        from_number=conversation.phone_number,
        to_number='556391386719',
        content={'text': texto},
        text_body=texto,
    )


class ConversaCanonicaTest(TestCase):
    """Qual das duas threads é a de verdade."""

    def setUp(self):
        self.account = WhatsAppAccount.objects.create(
            name='Cê Saladas', phone_number_id='PH_FUS', waba_id='WABA_FUS',
        )
        self.service = MessageService()

    def test_prefere_a_thread_com_mensagem_do_cliente(self):
        """A real é onde o cliente falou, não a que o sistema mexeu por último."""
        real = _conversa(self.account, '556384143551', contact_name='Dyana')
        _msg(real, 'inbound')
        fantasma = _conversa(self.account, '5563984143551')
        _msg(fantasma, 'outbound')  # mais recente, mas só notificação nossa

        escolhida = self.service._get_or_create_conversation(self.account, '5563984143551')

        self.assertEqual(escolhida.id, real.id)

    def test_escolha_nao_depende_de_quem_falou_por_ultimo(self):
        """O bug era exatamente este: a ordem mudava a resposta."""
        real = _conversa(self.account, '556384143551', contact_name='Dyana')
        _msg(real, 'inbound')
        fantasma = _conversa(self.account, '5563984143551')

        primeira = self.service._get_or_create_conversation(self.account, '5563984143551')
        _msg(fantasma, 'outbound')
        segunda = self.service._get_or_create_conversation(self.account, '5563984143551')

        self.assertEqual(primeira.id, segunda.id)
        self.assertEqual(segunda.id, real.id)

    def test_sem_thread_com_inbound_usa_a_mais_antiga(self):
        """Desempate estável: a primeira criada, não a mexida por último."""
        antiga = _conversa(self.account, '556384143551')
        _conversa(self.account, '5563984143551')

        escolhida = self.service._get_or_create_conversation(self.account, '63984143551')

        self.assertEqual(escolhida.id, antiga.id)

    def test_conta_diferente_nunca_se_confunde(self):
        """Mesma pessoa em Cê Saladas e Pastita são duas conversas legítimas."""
        outra_conta = WhatsAppAccount.objects.create(
            name='Pastita', phone_number_id='PH_FUS2', waba_id='WABA_FUS2',
        )
        da_outra = _conversa(outra_conta, '556384143551')
        _msg(da_outra, 'inbound')

        escolhida = self.service._get_or_create_conversation(self.account, '556384143551')

        self.assertNotEqual(escolhida.id, da_outra.id)
        self.assertEqual(escolhida.account_id, self.account.id)


class FusaoDasConversasAntigasTest(TestCase):
    """O comando que limpa as duplicatas que já existem."""

    def setUp(self):
        self.account = WhatsAppAccount.objects.create(
            name='Cê Saladas', phone_number_id='PH_MERGE', waba_id='WABA_MERGE',
        )
        self.real = _conversa(self.account, '556384143551', contact_name='Dyana')
        _msg(self.real, 'inbound', 'quero uma salada')
        self.fantasma = _conversa(self.account, '5563984143551')
        _msg(self.fantasma, 'outbound', 'pedido confirmado')

    def _fundir(self, aplicar=True):
        from apps.whatsapp.services.fusao_de_conversas import fundir_duplicatas
        return fundir_duplicatas(aplicar=aplicar)

    def test_fusao_deixa_uma_conversa_so(self):
        self._fundir()

        self.assertEqual(Conversation.objects.filter(account=self.account).count(), 1)
        self.assertTrue(Conversation.objects.filter(pk=self.real.pk).exists())

    def test_mensagens_da_fantasma_migram_e_nada_se_perde(self):
        self._fundir()

        textos = set(Message.objects.filter(conversation=self.real).values_list('text_body', flat=True))
        self.assertEqual(textos, {'quero uma salada', 'pedido confirmado'})

    def test_nome_do_contato_sobrevive(self):
        self._fundir()

        self.real.refresh_from_db()
        self.assertEqual(self.real.contact_name, 'Dyana')

    def test_modo_simulacao_nao_altera_nada(self):
        """Rodar antes de aplicar tem que ser seguro."""
        relatorio = self._fundir(aplicar=False)

        self.assertEqual(Conversation.objects.filter(account=self.account).count(), 2)
        self.assertEqual(len(relatorio), 1)

    def test_conversa_unica_nao_e_tocada(self):
        Conversation.objects.filter(pk=self.fantasma.pk).delete()

        relatorio = self._fundir()

        self.assertEqual(relatorio, [])
        self.assertEqual(Conversation.objects.filter(account=self.account).count(), 1)

    def test_contas_diferentes_nao_se_fundem(self):
        """Os 5 'duplicados' de 10/ago eram isto — e estavam certos."""
        outra = WhatsAppAccount.objects.create(
            name='Pastita', phone_number_id='PH_M2', waba_id='WABA_M2',
        )
        _conversa(outra, '556384143551')

        self._fundir()

        self.assertEqual(Conversation.objects.filter(account=outra).count(), 1)
