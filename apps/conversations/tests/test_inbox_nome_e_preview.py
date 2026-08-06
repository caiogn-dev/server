"""O inbox não pode virar uma parede de números nem de linhas em branco.

06/ago, com a ordenação já corrigida, o painel passou a mostrar o topo real da
lista e apareceram dois buracos antigos:

1. NOME — o WhatsApp só entrega o nome do perfil junto de mensagem RECEBIDA.
   Conversa que a loja abriu disparando (campanha, notificação) nasce sem
   `contact_name`: eram 116 de 182 conversas só com o número. Os 116 nomes já
   estavam em `unified_users` — o serializer só não olhava.

2. PREVIEW — imagem, documento e áudio não têm `text_body` (77 de 78 imagens e
   40 de 41 documentos naquele dia). A última mensagem virava preview vazio e a
   conversa parecia em branco na lista.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.conversations.api.serializers import ConversationSerializer
from apps.conversations.api.views import _accessible_conversations
from apps.conversations.models import Conversation
from apps.users.models import UnifiedUser
from apps.whatsapp.models import Message, WhatsAppAccount

User = get_user_model()
TELEFONE = '556392777991'


class NomeDeFallbackTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            username='admin-nome', password='x', email='admin-nome@real.com',
        )
        self.account = WhatsAppAccount.objects.create(
            name='Conta Nome', phone_number_id='321', waba_id='123',
            access_token='t', phone_number='5563000000009',
        )
        self.conversa = Conversation.objects.create(
            account=self.account, phone_number=TELEFONE,
            contact_name='', last_message_at=timezone.now(),
        )

    def _serializar(self):
        obj = (
            _accessible_conversations(self.admin)
            .filter(pk=self.conversa.pk)
            .first()
        )
        return ConversationSerializer(obj).data

    def test_usa_o_nome_do_unified_user_quando_nao_tem_contact_name(self):
        UnifiedUser.objects.update_or_create(
            phone_number=TELEFONE, defaults={'name': 'Dona Cleuza'},
        )
        self.assertEqual(self._serializar()['contact_name'], 'Dona Cleuza')

    def test_sem_nome_em_lugar_nenhum_continua_vazio(self):
        UnifiedUser.objects.filter(phone_number=TELEFONE).delete()
        self.assertEqual(self._serializar()['contact_name'], '')

    def test_placeholder_desconhecido_nao_substitui_o_numero(self):
        UnifiedUser.objects.update_or_create(
            phone_number=TELEFONE, defaults={'name': 'Desconhecido'},
        )
        self.assertEqual(
            self._serializar()['contact_name'], '',
            'mostrar "Desconhecido" apaga o telefone e não informa nada',
        )

    def test_identificador_interno_nao_vira_nome(self):
        UnifiedUser.objects.update_or_create(
            phone_number=TELEFONE, defaults={'name': 'cliente_556392777991'},
        )
        self.assertEqual(self._serializar()['contact_name'], '')

    def test_contact_name_real_tem_prioridade(self):
        UnifiedUser.objects.update_or_create(
            phone_number=TELEFONE, defaults={'name': 'Nome Velho'},
        )
        self.conversa.contact_name = 'Nome do WhatsApp'
        self.conversa.save(update_fields=['contact_name'])
        self.assertEqual(self._serializar()['contact_name'], 'Nome do WhatsApp')


class PreviewDeMidiaTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            username='admin-prev', password='x', email='admin-prev@real.com',
        )
        self.account = WhatsAppAccount.objects.create(
            name='Conta Prev', phone_number_id='654', waba_id='456',
            access_token='t', phone_number='5563000000010',
        )
        self.conversa = Conversation.objects.create(
            account=self.account, phone_number='556392777002',
            contact_name='Cliente', last_message_at=timezone.now(),
        )

    def _preview_para(self, message_type, text_body=''):
        Message.objects.create(
            account=self.account, conversation=self.conversa,
            whatsapp_message_id=f'wamid-{message_type}-{text_body[:5]}',
            direction='outbound', message_type=message_type, status='sent',
            from_number='5563000000010', to_number='556392777002',
            text_body=text_body,
        )
        obj = (
            _accessible_conversations(self.admin)
            .filter(pk=self.conversa.pk)
            .first()
        )
        return ConversationSerializer(obj).data['last_message_preview']

    def test_imagem_sem_texto_mostra_rotulo(self):
        self.assertEqual(self._preview_para('image'), '📷 Foto')

    def test_documento_sem_texto_mostra_rotulo(self):
        self.assertEqual(self._preview_para('document'), '📄 Documento')

    def test_texto_normal_continua_aparecendo(self):
        self.assertEqual(self._preview_para('text', 'Bom dia!'), 'Bom dia!')

    def test_legenda_da_imagem_tem_prioridade_sobre_o_rotulo(self):
        self.assertEqual(self._preview_para('image', 'Olha o prato'), 'Olha o prato')
