"""
Serializers CRM — CustomerSearch, UserAddress, TeamMember.
"""
from rest_framework import serializers
from django.contrib.auth import get_user_model
from apps.users.models import UserAddress, UnifiedUser
from apps.stores.models import StoreTeamMember

User = get_user_model()


class UserAddressSerializer(serializers.ModelSerializer):
    """Endereço salvo de um cliente."""

    class Meta:
        model = UserAddress
        fields = [
            'id', 'label', 'street', 'number', 'neighborhood',
            'city', 'state', 'zip_code', 'lat', 'lng', 'is_default',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class CustomerSearchSerializer(serializers.ModelSerializer):
    """
    Resultado de busca de clientes no PDV.

    Inclui endereços filtrados pela loja do contexto.
    """
    addresses = serializers.SerializerMethodField()

    class Meta:
        model = UnifiedUser
        fields = [
            'id', 'name', 'phone_number', 'email',
            'total_orders', 'total_spent', 'last_order_at',
            'addresses',
        ]

    def get_addresses(self, obj):
        store = self.context.get('store')
        if store:
            qs = obj.addresses.filter(tenant=store)
        else:
            qs = obj.addresses.all()
        return UserAddressSerializer(qs, many=True).data


class TeamMemberUserSerializer(serializers.ModelSerializer):
    """Dados básicos do usuário para exibição no painel de equipe."""

    class Meta:
        model = User
        fields = ['id', 'email', 'first_name', 'last_name']
        read_only_fields = ['id', 'email', 'first_name', 'last_name']


class TeamMemberSerializer(serializers.ModelSerializer):
    """Leitura de um membro da equipe."""
    user = TeamMemberUserSerializer(read_only=True)

    class Meta:
        model = StoreTeamMember
        fields = ['id', 'user', 'role', 'is_active', 'created_at']
        read_only_fields = ['id', 'created_at']


class TeamMemberCreateSerializer(serializers.ModelSerializer):
    """Criação/atualização de um membro da equipe."""
    user_id = serializers.UUIDField()

    class Meta:
        model = StoreTeamMember
        fields = ['user_id', 'role']

    def validate_user_id(self, value):
        if not User.objects.filter(pk=value).exists():
            raise serializers.ValidationError("Usuário não encontrado.")
        return value
