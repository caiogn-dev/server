"""
Conversation API serializers.
"""
from django.core.exceptions import ObjectDoesNotExist
from rest_framework import serializers
from ..models import Conversation, ConversationNote


class ConversationSerializer(serializers.ModelSerializer):
    """Serializer for Conversation."""
    account_name = serializers.CharField(source='account.name', read_only=True)
    # A qual LOJA esta conversa pertence. Sem isto o painel não conseguia nem
    # marcar visualmente de quem é a conversa, nem descartar no WebSocket as
    # mensagens de outra loja — a lista vinha filtrada da API mas o WS (que roda
    # em modo multi-conta) injetava tudo, então a conversa aparecia ao vivo e
    # sumia no primeiro refresh.
    store_slug = serializers.SerializerMethodField()
    store_name = serializers.SerializerMethodField()
    profile_picture = serializers.SerializerMethodField()
    unified_user_id = serializers.SerializerMethodField()
    assigned_agent_name = serializers.CharField(
        source='assigned_agent.username',
        read_only=True,
        allow_null=True
    )
    ai_agent_name = serializers.CharField(
        source='ai_agent.name',
        read_only=True,
        allow_null=True
    )
    message_count = serializers.SerializerMethodField()
    last_message_preview = serializers.SerializerMethodField()
    unread_count = serializers.SerializerMethodField()
    handover_status = serializers.SerializerMethodField()
    handover_assigned_to = serializers.SerializerMethodField()
    handover_assigned_to_name = serializers.SerializerMethodField()
    
    class Meta:
        model = Conversation
        fields = [
            'id', 'account', 'account_name', 'store_slug', 'store_name',
            'phone_number', 'contact_name',
            'wa_id', 'profile_picture_url', 'profile_picture_file', 'profile_picture',
            'profile_name_last_seen_at',
            'mode', 'status', 'assigned_agent', 'assigned_agent_name',
            'ai_agent', 'ai_agent_name', 'agent_session_id', 'context', 'tags',
            'last_message_at', 'last_message_preview', 'unread_count',
            'handover_status', 'handover_assigned_to', 'handover_assigned_to_name',
            'last_customer_message_at', 'last_agent_message_at',
            'closed_at', 'resolved_at', 'message_count',
            'created_at', 'updated_at', 'is_active',
            'unified_user_id',
        ]
        read_only_fields = [
            'id', 'last_message_at', 'last_customer_message_at',
            'last_agent_message_at', 'closed_at', 'resolved_at',
            'created_at', 'updated_at'
        ]

    # Nomes-lixo que o sistema inventa quando não sabe quem é a pessoa.
    # Mostrar "Desconhecido" no lugar do telefone é PIOR que mostrar o número:
    # o dono perde o único dado útil e 112 conversas ficam idênticas na lista
    # (06/ago: 112 dos 116 unified_users sem nome real tinham exatamente isso).
    NOMES_INUTEIS = {'desconhecido', 'cliente balcão', 'cliente balcao',
                     'cliente', 'sem nome', 'none', 'null'}

    @classmethod
    def _nome_util(cls, valor) -> str:
        nome = str(valor or '').strip()
        if not nome or nome.lower() in cls.NOMES_INUTEIS:
            return ''
        # cliente_5563..., user_123: identificador interno, não nome de gente.
        if nome.lower().startswith(('cliente_', 'user_', 'usuario_')):
            return ''
        return nome

    def to_representation(self, instance):
        """Preenche `contact_name` vazio com o nome que já conhecemos.

        O WhatsApp só manda o nome do perfil junto de mensagem RECEBIDA.
        Conversa aberta por disparo da loja (campanha, notificação) nasce sem
        nome, e o inbox vira uma parede de números.

        Feito aqui, e não como SerializerMethodField, para o campo continuar
        gravável (o painel edita o nome do contato).
        """
        data = super().to_representation(instance)
        if not self._nome_util(data.get('contact_name')):
            nome = self._nome_util(getattr(instance, 'anno_unified_name', None))
            data['contact_name'] = nome or (data.get('contact_name') or '')
        return data

    def get_unified_user_id(self, obj):
        # Subquery do viewset evita 1 query/linha em unified_users.
        if hasattr(obj, 'anno_unified_user_id'):
            anno = obj.anno_unified_user_id
            return str(anno) if anno else None
        from apps.users.models import UnifiedUser
        if not obj.phone_number:
            return None
        result = UnifiedUser.objects.filter(phone_number=obj.phone_number).values('id').first()
        return str(result['id']) if result else None

    @staticmethod
    def _loja(obj):
        """Loja da conta: pelo M2M `stores` ou pelo CompanyProfile.

        O viewset já faz prefetch de `account__stores` e `account__company_profile`,
        então isto não gera query por linha.
        """
        conta = obj.account
        if conta is None:
            return None
        lojas = list(conta.stores.all())
        if lojas:
            return lojas[0]
        perfil = getattr(conta, 'company_profile', None)
        return getattr(perfil, 'store', None) if perfil else None

    def get_store_slug(self, obj):
        loja = self._loja(obj)
        return loja.slug if loja else None

    def get_store_name(self, obj):
        loja = self._loja(obj)
        return loja.name if loja else None

    def get_profile_picture(self, obj):
        if obj.profile_picture_file:
            request = self.context.get('request')
            url = obj.profile_picture_file.url
            return request.build_absolute_uri(url) if request else url
        return obj.profile_picture_url or ''

    def get_message_count(self, obj):
        # Lê a annotation do viewset (1 query agregada) p/ não contar por linha.
        anno = getattr(obj, 'anno_message_count', None)
        if anno is not None:
            return anno
        return obj.messages.count() if hasattr(obj, 'messages') else 0

    # Mídia não tem text_body — sem rótulo, a conversa aparecia em branco.
    ROTULO_POR_TIPO = {
        'image': '📷 Foto',
        'document': '📄 Documento',
        'audio': '🎤 Áudio',
        'video': '🎥 Vídeo',
        'sticker': '💬 Figurinha',
        'location': '📍 Localização',
        'contacts': '👤 Contato',
        'order': '🛒 Pedido pelo catálogo',
        'reaction': '👍 Reação',
    }

    def _preview(self, texto, tipo):
        texto = (texto or '').strip()
        if not texto:
            texto = self.ROTULO_POR_TIPO.get(tipo or '', '')
        return texto[:50] + '...' if len(texto) > 50 else texto

    def get_last_message_preview(self, obj):
        """Get preview of the last message in the conversation."""
        # Subquery do viewset traz o texto da última msg sem query por linha.
        if hasattr(obj, 'anno_last_text'):
            return self._preview(obj.anno_last_text, getattr(obj, 'anno_last_type', ''))
        if hasattr(obj, 'messages'):
            last_msg = obj.messages.order_by('-created_at').first()
            if last_msg:
                return self._preview(last_msg.text_body, last_msg.message_type)
        return ''

    def get_unread_count(self, obj):
        """Count unread inbound messages."""
        anno = getattr(obj, 'anno_unread_count', None)
        if anno is not None:
            return anno
        if hasattr(obj, 'messages'):
            return obj.messages.filter(
                direction='inbound',
                read_at__isnull=True
            ).count()
        return 0

    def _get_handover(self, obj):
        # Canonical handover lives in apps.handover (related_name='handover', OneToOne).
        try:
            return obj.handover
        except (AttributeError, ObjectDoesNotExist):
            return None

    def get_handover_status(self, obj):
        handover = self._get_handover(obj)
        if handover:
            return getattr(handover, 'status', None)
        return 'bot' if obj.mode == Conversation.ConversationMode.AUTO else obj.mode

    def get_handover_assigned_to(self, obj):
        handover = self._get_handover(obj)
        assignee = getattr(handover, 'assigned_to', None) or obj.assigned_agent
        return str(assignee.id) if assignee else None

    def get_handover_assigned_to_name(self, obj):
        handover = self._get_handover(obj)
        assignee = getattr(handover, 'assigned_to', None) or obj.assigned_agent
        if not assignee:
            return None
        return getattr(assignee, 'get_full_name', lambda: '')() or getattr(assignee, 'username', None)


class ConversationNoteSerializer(serializers.ModelSerializer):
    """Serializer for Conversation Note."""
    author_name = serializers.CharField(source='author.username', read_only=True, allow_null=True)
    
    class Meta:
        model = ConversationNote
        fields = [
            'id', 'conversation', 'author', 'author_name', 'content',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class SwitchModeSerializer(serializers.Serializer):
    """Serializer for switching conversation mode."""
    agent_id = serializers.IntegerField(required=False, allow_null=True)


class AddNoteSerializer(serializers.Serializer):
    """Serializer for adding a note."""
    content = serializers.CharField(max_length=5000)


class UpdateContextSerializer(serializers.Serializer):
    """Serializer for updating context."""
    context = serializers.DictField()


class TagSerializer(serializers.Serializer):
    """Serializer for tag operations."""
    tag = serializers.CharField(max_length=50)


class AssignAgentSerializer(serializers.Serializer):
    """Serializer for assigning agent."""
    agent_id = serializers.IntegerField()


class UniversalConversationSerializer(serializers.Serializer):
    """Normalized read-only serializer for the multichannel conversations hub."""

    id = serializers.CharField()
    platform = serializers.CharField()
    platform_icon_key = serializers.CharField()
    source_conversation_id = serializers.CharField()
    account_id = serializers.CharField(allow_null=True)
    display_name = serializers.CharField()
    secondary_identifier = serializers.CharField(allow_blank=True, allow_null=True)
    last_message_preview = serializers.CharField(allow_blank=True, allow_null=True)
    last_message_at = serializers.DateTimeField(allow_null=True)
    unread_count = serializers.IntegerField()
    status = serializers.CharField(allow_blank=True, allow_null=True)
    route = serializers.CharField()
    route_params = serializers.JSONField()
    is_actionable = serializers.BooleanField()
