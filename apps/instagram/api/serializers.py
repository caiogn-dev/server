from types import SimpleNamespace

from rest_framework import serializers
from ..models import (
    InstagramAccount, InstagramMedia, InstagramMediaItem,
    InstagramProductTag, InstagramCatalog, InstagramProduct,
    InstagramLive, InstagramLiveComment, InstagramConversation,
    InstagramMessage, InstagramScheduledPost, InstagramInsight
)


class InstagramAccountSerializer(serializers.ModelSerializer):
    # O painel precisa distinguir "ligado" de "funcionando": conta ativa com
    # token recusado pela Meta é um canal mudo.
    precisa_reconectar = serializers.SerializerMethodField()

    class Meta:
        model = InstagramAccount
        fields = [
            'id', 'platform', 'username', 'instagram_business_id',
            'followers_count', 'follows_count', 'media_count',
            'profile_picture_url', 'biography', 'website',
            'is_active', 'is_verified', 'precisa_reconectar',
            'created_at', 'updated_at', 'last_sync_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_precisa_reconectar(self, obj) -> bool:
        return obj.token_invalido_em is not None


class InstagramMediaItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = InstagramMediaItem
        fields = ['id', 'media_type', 'media_url', 'thumbnail_url', 'order']


class InstagramProductTagSerializer(serializers.ModelSerializer):
    class Meta:
        model = InstagramProductTag
        fields = ['id', 'product_id', 'product_name', 'position_x', 'position_y']


class InstagramMediaSerializer(serializers.ModelSerializer):
    items = InstagramMediaItemSerializer(many=True, read_only=True)
    product_tags = InstagramProductTagSerializer(many=True, read_only=True)
    
    class Meta:
        model = InstagramMedia
        fields = [
            'id', 'account', 'instagram_media_id', 'media_type',
            'caption', 'media_url', 'thumbnail_url', 'permalink',
            'likes_count', 'comments_count', 'shares_count', 'saves_count',
            'reach', 'impressions', 'status', 'scheduled_at', 'published_at',
            'has_product_tags', 'items', 'product_tags',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'account', 'created_at', 'updated_at']


class InstagramProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = InstagramProduct
        fields = [
            'id', 'catalog', 'product_id', 'retailer_id',
            'name', 'description', 'price', 'currency',
            'availability', 'condition', 'image_url',
            'additional_image_urls', 'url', 'is_active',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class InstagramCatalogSerializer(serializers.ModelSerializer):
    products_count = serializers.IntegerField(source='products.count', read_only=True)
    
    class Meta:
        model = InstagramCatalog
        fields = ['id', 'catalog_id', 'name', 'products_count', 'is_active', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']


class InstagramLiveCommentSerializer(serializers.ModelSerializer):
    class Meta:
        model = InstagramLiveComment
        fields = ['id', 'username', 'text', 'created_at']


class InstagramLiveSerializer(serializers.ModelSerializer):
    comments = InstagramLiveCommentSerializer(many=True, read_only=True)
    
    class Meta:
        model = InstagramLive
        fields = [
            'id', 'title', 'description', 'status',
            'viewers_count', 'max_viewers', 'comments_count',
            'stream_url', 'stream_key', 'scheduled_at',
            'started_at', 'ended_at', 'comments',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'stream_key', 'created_at', 'updated_at']


class InstagramMessageSerializer(serializers.ModelSerializer):
    reply_to = serializers.PrimaryKeyRelatedField(read_only=True)
    conversation = serializers.PrimaryKeyRelatedField(read_only=True)
    direction = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()
    
    class Meta:
        model = InstagramMessage
        fields = [
            'id', 'conversation', 'instagram_message_id', 'message_type',
            'content', 'media_url', 'reaction_type',
            'reply_to', 'is_unsent', 'is_from_business',
            'is_read', 'read_at', 'sent_at', 'created_at',
            'direction', 'status',
        ]
        read_only_fields = ['id', 'created_at']

    def get_direction(self, obj):
        return 'outbound' if obj.is_from_business else 'inbound'

    def get_status(self, obj):
        if obj.is_from_business and not obj.instagram_message_id:
            return 'pending'
        if obj.is_read:
            return 'read'
        if obj.is_from_business:
            return 'sent'
        return 'received'


class InstagramConversationSerializer(serializers.ModelSerializer):
    last_message = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()
    last_message_preview = serializers.SerializerMethodField()
    
    class Meta:
        model = InstagramConversation
        fields = [
            'id', 'account', 'instagram_conversation_id',
            'participant_id', 'participant_username',
            'participant_name', 'participant_profile_pic',
            'is_active', 'unread_count', 'last_message_at',
            'last_message', 'last_message_preview',
            'status', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'account', 'created_at', 'updated_at']
    
    @staticmethod
    def _last_msg(obj):
        """Última mensagem não desfeita, buscada no máximo uma vez por conversa.

        O viewset anota `_last_msg_*` via Subquery (zero queries extras);
        sem anotação, cai numa query única memorizada no objeto.
        """
        if hasattr(obj, '_last_msg_type'):
            if obj._last_msg_type is None:
                return None
            return SimpleNamespace(
                message_type=obj._last_msg_type,
                content=obj._last_msg_content,
                created_at=obj._last_msg_created_at,
            )
        if not hasattr(obj, '_last_msg_cache'):
            obj._last_msg_cache = obj.messages.filter(
                is_unsent=False
            ).order_by('-created_at').first()
        return obj._last_msg_cache

    def get_last_message(self, obj):
        last_msg = self._last_msg(obj)
        if last_msg:
            return {
                'type': last_msg.message_type,
                'content': last_msg.content[:100] if last_msg.content else None,
                'created_at': last_msg.created_at.isoformat()
            }
        return None

    def get_status(self, obj):
        return 'active' if obj.is_active else 'closed'

    def get_last_message_preview(self, obj):
        last_msg = self._last_msg(obj)
        if not last_msg:
            return ''
        if last_msg.content:
            return last_msg.content[:120]
        return last_msg.message_type.replace('_', ' ').title()


class InstagramScheduledPostSerializer(serializers.ModelSerializer):
    class Meta:
        model = InstagramScheduledPost
        fields = [
            'id', 'media_type', 'caption', 'media_files',
            'schedule_time', 'timezone', 'product_tags',
            'status', 'instagram_media_id', 'error_message',
            'published_at', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class InstagramInsightSerializer(serializers.ModelSerializer):
    class Meta:
        model = InstagramInsight
        fields = [
            'date', 'impressions', 'reach', 'profile_views',
            'website_clicks', 'follower_count', 'followers_gained',
            'followers_lost', 'engagement', 'created_at'
        ]
