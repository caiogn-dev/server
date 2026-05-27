from rest_framework import serializers
from apps.postado.models import PostadoClient


class PostadoClientCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = PostadoClient
        fields = ['business_name', 'niche', 'tone', 'brand_colors',
                  'email', 'whatsapp', 'logo_url', 'photos']
