from rest_framework import serializers
from ..models import (
    InstagramAccount, InstagramMedia, InstagramMediaItem,
    InstagramProductTag, InstagramCatalog, InstagramProduct,
    InstagramLive, InstagramLiveComment, InstagramConversation,
    InstagramMessage, InstagramScheduledPost, InstagramInsight
)


class InstagramAccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = InstagramAccount
        fields = [
            'id', 'platform', 'username', 'instagram_business_id',
            'followers_count', 'follows_count', 'media_count',
            'profile_picture_url', 'biography', 'website',
            'is_active', 'is_verified', 'created_at', 'updated_at', 'last_sync_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


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
        read_only_fields = ['id', 'created_at', 'updated_at']


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
    
    class Meta:
        model = InstagramMessage
        fields = [
            'id', 'instagram_message_id', 'message_type',
            'content', 'media_url', 'reaction_type',
            'reply_to', 'is_unsent', 'is_from_business',
            'is_read', 'read_at', 'sent_at', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']


class InstagramConversationSerializer(serializers.ModelSerializer):
    last_message = serializers.SerializerMethodField()
    
    class Meta:
        model = InstagramConversation
        fields = [
            'id', 'instagram_conversation_id',
            'participant_id', 'participant_username',
            'participant_name', 'participant_profile_pic',
            'is_active', 'unread_count', 'last_message_at',
            'last_message', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_last_message(self, obj):
        last_msg = obj.messages.filter(is_unsent=False).order_by('-created_at').first()
        if last_msg:
            return {
                'type': last_msg.message_type,
                'content': last_msg.content[:100] if last_msg.content else None,
                'created_at': last_msg.created_at.isoformat()
            }
        return None


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