from rest_framework import serializers
from apps.postado.models import PostadoClient, PostadoPack, PostadoPost


class PostadoPostAdminSerializer(serializers.ModelSerializer):
    class Meta:
        model = PostadoPost
        fields = [
            'id', 'post_number', 'post_type', 'caption', 'hashtags', 'cta',
            'image_prompt', 'feed_image_url', 'stories_image_url',
            'status', 'revision_notes',
        ]


class PostadoPackListSerializer(serializers.ModelSerializer):
    client_name = serializers.CharField(source='client.business_name', read_only=True)
    total_posts = serializers.SerializerMethodField()

    def get_total_posts(self, obj):
        return obj.posts.count()

    class Meta:
        model = PostadoPack
        fields = [
            'id', 'client', 'client_name', 'month', 'status',
            'drive_folder_url', 'created_at', 'total_posts',
        ]


class PostadoPackAdminSerializer(serializers.ModelSerializer):
    posts = PostadoPostAdminSerializer(many=True, read_only=True)
    client_name = serializers.CharField(source='client.business_name', read_only=True)
    total_posts = serializers.SerializerMethodField()

    def get_total_posts(self, obj):
        return obj.posts.count()

    class Meta:
        model = PostadoPack
        fields = [
            'id', 'client', 'client_name', 'month', 'status',
            'drive_folder_url', 'generated_at', 'approved_at', 'delivered_at',
            'created_at', 'total_posts', 'posts',
        ]


class PostadoClientListSerializer(serializers.ModelSerializer):
    pack_count = serializers.SerializerMethodField()
    latest_pack_status = serializers.SerializerMethodField()

    def get_pack_count(self, obj):
        return obj.packs.count()

    def get_latest_pack_status(self, obj):
        latest = obj.packs.first()
        return latest.status if latest else None

    class Meta:
        model = PostadoClient
        fields = [
            'id', 'business_name', 'niche', 'status', 'email',
            'created_at', 'pack_count', 'latest_pack_status',
        ]


class PostadoClientAdminSerializer(serializers.ModelSerializer):
    packs = PostadoPackListSerializer(many=True, read_only=True)
    pack_count = serializers.SerializerMethodField()

    def get_pack_count(self, obj):
        return obj.packs.count()

    class Meta:
        model = PostadoClient
        fields = [
            'id', 'business_name', 'niche', 'tone', 'brand_colors',
            'logo_url', 'email', 'whatsapp', 'drive_folder_id',
            'mp_subscription_id', 'status', 'created_at', 'pack_count', 'packs',
            'description', 'products', 'target_audience', 'instagram_handle',
            'contact_info', 'reference_images', 'brand_guidelines',
        ]
