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
    name = serializers.SerializerMethodField()

    class Meta:
        model = UnifiedUser
        fields = [
            'id', 'name', 'phone_number', 'email',
            'total_orders', 'total_spent', 'last_order_at',
            'addresses',
        ]

    def get_name(self, obj):
        """Nome do cadastro; se for só o telefone, o último nome usado nos
        pedidos da loja — é por ele que o lojista conhece a cliente."""
        from apps.core.services.customer_identity import CustomerIdentityService
        if not CustomerIdentityService.is_placeholder_name(obj.name):
            return obj.name
        store = self.context.get('store')
        if store and obj.django_user_id:
            from apps.stores.models import StoreOrder
            nomes = (
                StoreOrder.objects
                .filter(store=store, customer_id=obj.django_user_id)
                .exclude(customer_name='')
                .order_by('-created_at')
                .values_list('customer_name', flat=True)[:5]
            )
            for nome in nomes:
                if not CustomerIdentityService.is_placeholder_name(nome):
                    return nome
        return obj.name

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


class TeamMemberCreateSerializer(serializers.Serializer):
    """Criação/atualização de um membro da equipe — por TELEFONE.

    `user_id` era `UUIDField` e a chave do `User` e `AutoField`: toda criação
    voltava 400 "Deve ser um UUID válido". O endpoint nunca conseguiu criar um
    membro desde que nasceu, em junho. Agora e `IntegerField`, do tipo certo.

    Mas o caminho normal e o telefone: o dono da loja nao sabe o id de
    ninguem, e id nao aparece na tela do lojista. `user_id` fica so para quem
    ja chamava a API assim.
    """
    phone = serializers.CharField(required=False, allow_blank=True)
    name = serializers.CharField(required=False, allow_blank=True)
    # A senha com que a pessoa entra no painel (celular + senha). Sem ela o
    # convite criava um usuário com senha inutilizável e ninguém conseguia
    # entrar — medido em 28/09: "eu registro ele e ele acessa como?".
    password = serializers.CharField(required=False, allow_blank=True, write_only=True, min_length=6)
    user_id = serializers.IntegerField(required=False)
    role = serializers.ChoiceField(
        choices=StoreTeamMember.Role.choices,
        default=StoreTeamMember.Role.OPERATOR,
    )

    def validate_user_id(self, value):
        if not User.objects.filter(pk=value).exists():
            raise serializers.ValidationError("Usuário não encontrado.")
        return value

    def validate(self, attrs):
        if not attrs.get('phone') and not attrs.get('user_id'):
            raise serializers.ValidationError(
                {'phone': ['Informe o telefone do colaborador, com DDD.']}
            )
        return attrs
