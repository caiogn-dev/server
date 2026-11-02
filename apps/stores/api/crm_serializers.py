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
    cadastro = serializers.SerializerMethodField()

    class Meta:
        model = UnifiedUser
        fields = [
            'id', 'name', 'phone_number', 'email',
            'total_orders', 'total_spent', 'last_order_at',
            'addresses', 'cadastro',
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

    def _cliente_da_loja(self, obj):
        store = self.context.get('store')
        if not store:
            return None
        cache = self.context.setdefault('_clientes_da_loja', {})
        if obj.pk not in cache:
            cache[obj.pk] = (
                obj.store_customers.filter(store=store).prefetch_related('address_list').first()
            )
        return cache[obj.pk]

    def get_cadastro(self, obj):
        """PF/PJ e documento do cadastro DESTA loja — o pedido e a nota usam."""
        c = self._cliente_da_loja(obj)
        if c is None:
            return None
        return {
            'id': str(c.id),
            'tipo_pessoa': c.tipo_pessoa,
            'documento': c.documento,
            'razao_social': c.razao_social,
            'nome_fantasia': c.nome_fantasia,
            'inscricao_estadual': c.inscricao_estadual,
            'email': c.email,
        }

    def get_addresses(self, obj):
        store = self.context.get('store')
        if store:
            qs = obj.addresses.filter(tenant=store)
        else:
            qs = obj.addresses.all()
        enderecos = list(UserAddressSerializer(qs, many=True).data)
        # O endereço salvo na tela Clientes (StoreCustomerAddress) não
        # aparecia no novo pedido, que só lia UserAddress (27/10).
        vistos = {((e.get('street') or '').strip().lower(), (e.get('number') or '').strip()) for e in enderecos}
        c = self._cliente_da_loja(obj)
        for a in (c.address_list.all() if c else []):
            chave = ((a.street or '').strip().lower(), (a.number or '').strip())
            if chave in vistos:
                continue
            vistos.add(chave)
            enderecos.append({
                'id': str(a.id), 'label': a.label, 'street': a.street, 'number': a.number,
                'neighborhood': a.neighborhood, 'complement': a.complement, 'city': a.city,
                'state': a.state, 'zip_code': a.zip_code, 'lat': None, 'lng': None,
                'is_default': a.is_default, 'created_at': a.created_at,
            })
        return enderecos


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
