"""
Pastita API Serializers
"""
from rest_framework import serializers
from .models import (
    CustomUser, Produto, Molho, Carne, Rondelli, Combo,
    Carrinho, ItemCarrinho, ItemComboCarrinho,
    Pedido, ItemPedido, ItemComboPedido
)


# =============================================================================
# USER SERIALIZERS
# =============================================================================

class UserSerializer(serializers.ModelSerializer):
    """User serializer for registration and profile."""
    password = serializers.CharField(write_only=True, min_length=8)
    
    class Meta:
        model = CustomUser
        fields = ['id', 'email', 'first_name', 'last_name', 'phone', 'password', 'date_joined']
        read_only_fields = ['id', 'date_joined']

    def create(self, validated_data):
        password = validated_data.pop('password')
        user = CustomUser(**validated_data)
        user.set_password(password)
        user.save()
        return user


class UserProfileSerializer(serializers.ModelSerializer):
    """User profile serializer (no password)."""
    
    class Meta:
        model = CustomUser
        fields = ['id', 'email', 'first_name', 'last_name', 'phone', 'date_joined']
        read_only_fields = ['id', 'email', 'date_joined']


# =============================================================================
# PRODUCT SERIALIZERS
# =============================================================================

class ProdutoSerializer(serializers.ModelSerializer):
    """Base product serializer."""
    imagem_url = serializers.SerializerMethodField()
    tipo_produto = serializers.SerializerMethodField()
    
    class Meta:
        model = Produto
        fields = [
            'id', 'nome', 'descricao', 'preco', 'imagem', 'imagem_url',
            'ativo', 'criado_em', 'atualizado_em', 'tipo_produto'
        ]
        read_only_fields = ['id', 'criado_em', 'atualizado_em']

    def get_imagem_url(self, obj):
        request = self.context.get('request')
        if obj.imagem and hasattr(obj.imagem, 'url'):
            if request:
                return request.build_absolute_uri(obj.imagem.url)
            return obj.imagem.url
        return None

    def get_tipo_produto(self, obj):
        """Determine the specific product type."""
        if hasattr(obj, 'molho'):
            return 'molho'
        elif hasattr(obj, 'carne'):
            return 'carne'
        elif hasattr(obj, 'rondelli'):
            return 'rondelli'
        return 'produto'


class MolhoSerializer(serializers.ModelSerializer):
    """Sauce product serializer."""
    imagem_url = serializers.SerializerMethodField()
    tipo_display = serializers.CharField(source='get_tipo_display', read_only=True)
    
    class Meta:
        model = Molho
        fields = [
            'id', 'nome', 'descricao', 'preco', 'imagem', 'imagem_url',
            'ativo', 'tipo', 'tipo_display', 'quantidade', 'criado_em'
        ]
        read_only_fields = ['id', 'criado_em']

    def get_imagem_url(self, obj):
        request = self.context.get('request')
        if obj.imagem and hasattr(obj.imagem, 'url'):
            if request:
                return request.build_absolute_uri(obj.imagem.url)
            return obj.imagem.url
        return None


class CarneSerializer(serializers.ModelSerializer):
    """Meat product serializer."""
    imagem_url = serializers.SerializerMethodField()
    tipo_display = serializers.CharField(source='get_tipo_display', read_only=True)
    molhos_compativeis = MolhoSerializer(source='molhos', many=True, read_only=True)
    
    class Meta:
        model = Carne
        fields = [
            'id', 'nome', 'descricao', 'preco', 'imagem', 'imagem_url',
            'ativo', 'tipo', 'tipo_display', 'quantidade', 
            'molhos', 'molhos_compativeis', 'criado_em'
        ]
        read_only_fields = ['id', 'criado_em']

    def get_imagem_url(self, obj):
        request = self.context.get('request')
        if obj.imagem and hasattr(obj.imagem, 'url'):
            if request:
                return request.build_absolute_uri(obj.imagem.url)
            return obj.imagem.url
        return None


class RondelliSerializer(serializers.ModelSerializer):
    """Rondelli pasta serializer."""
    imagem_url = serializers.SerializerMethodField()
    sabor_display = serializers.CharField(source='get_sabor_display', read_only=True)
    categoria_display = serializers.CharField(source='get_categoria_display', read_only=True)
    is_gourmet = serializers.BooleanField(read_only=True)
    
    class Meta:
        model = Rondelli
        fields = [
            'id', 'nome', 'descricao', 'preco', 'imagem', 'imagem_url',
            'ativo', 'categoria', 'categoria_display', 'sabor', 'sabor_display',
            'quantidade', 'is_gourmet', 'criado_em'
        ]
        read_only_fields = ['id', 'criado_em', 'is_gourmet']

    def get_imagem_url(self, obj):
        request = self.context.get('request')
        if obj.imagem and hasattr(obj.imagem, 'url'):
            if request:
                return request.build_absolute_uri(obj.imagem.url)
            return obj.imagem.url
        return None


class ComboSerializer(serializers.ModelSerializer):
    """Combo bundle serializer."""
    imagem_url = serializers.SerializerMethodField()
    molhos_inclusos = MolhoSerializer(source='molhos', many=True, read_only=True)
    carne_inclusa = CarneSerializer(source='carne', read_only=True)
    rondelli_incluso = RondelliSerializer(source='rondelli', read_only=True)
    economia = serializers.DecimalField(max_digits=8, decimal_places=2, read_only=True)
    percentual_desconto = serializers.IntegerField(read_only=True)
    
    class Meta:
        model = Combo
        fields = [
            'id', 'nome', 'descricao', 'preco', 'preco_original',
            'imagem', 'imagem_url', 'ativo', 'destaque',
            'molhos', 'molhos_inclusos',
            'carne', 'carne_inclusa',
            'rondelli', 'rondelli_incluso',
            'economia', 'percentual_desconto', 'criado_em'
        ]
        read_only_fields = ['id', 'criado_em', 'economia', 'percentual_desconto']

    def get_imagem_url(self, obj):
        request = self.context.get('request')
        if obj.imagem and hasattr(obj.imagem, 'url'):
            if request:
                return request.build_absolute_uri(obj.imagem.url)
            return obj.imagem.url
        return None


# =============================================================================
# CART SERIALIZERS
# =============================================================================

class ItemCarrinhoSerializer(serializers.ModelSerializer):
    """Cart item serializer for products."""
    produto_info = ProdutoSerializer(source='produto', read_only=True)
    subtotal = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    
    class Meta:
        model = ItemCarrinho
        fields = ['id', 'produto', 'produto_info', 'quantidade', 'subtotal', 'criado_em']
        read_only_fields = ['id', 'subtotal', 'criado_em']


class ItemComboCarrinhoSerializer(serializers.ModelSerializer):
    """Cart item serializer for combos."""
    combo_info = ComboSerializer(source='combo', read_only=True)
    subtotal = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    
    class Meta:
        model = ItemComboCarrinho
        fields = ['id', 'combo', 'combo_info', 'quantidade', 'subtotal', 'criado_em']
        read_only_fields = ['id', 'subtotal', 'criado_em']


class CarrinhoSerializer(serializers.ModelSerializer):
    """Shopping cart serializer with products and combos."""
    itens = ItemCarrinhoSerializer(many=True, read_only=True)
    combos = ItemComboCarrinhoSerializer(many=True, read_only=True)
    total_produtos = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    total_combos = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    total = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    quantidade_itens = serializers.IntegerField(read_only=True)
    tem_itens = serializers.BooleanField(read_only=True)
    
    class Meta:
        model = Carrinho
        fields = [
            'id', 'usuario', 'itens', 'combos',
            'total_produtos', 'total_combos', 'total',
            'quantidade_itens', 'tem_itens',
            'criado_em', 'atualizado_em'
        ]
        read_only_fields = ['id', 'usuario', 'criado_em', 'atualizado_em']


class AddToCartSerializer(serializers.Serializer):
    """Serializer for adding product to cart."""
    produto_id = serializers.IntegerField()
    quantidade = serializers.IntegerField(min_value=1, default=1)


class AddComboToCartSerializer(serializers.Serializer):
    """Serializer for adding combo to cart."""
    combo_id = serializers.IntegerField()
    quantidade = serializers.IntegerField(min_value=1, default=1)


class UpdateCartItemSerializer(serializers.Serializer):
    """Serializer for updating cart item quantity."""
    quantidade = serializers.IntegerField(min_value=0)


# =============================================================================
# ORDER SERIALIZERS
# =============================================================================

class ItemPedidoSerializer(serializers.ModelSerializer):
    """Order item serializer for products."""
    subtotal = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    
    class Meta:
        model = ItemPedido
        fields = ['id', 'produto', 'nome_produto', 'quantidade', 'preco_unitario', 'subtotal']
        read_only_fields = ['id', 'subtotal']


class ItemComboPedidoSerializer(serializers.ModelSerializer):
    """Order item serializer for combos."""
    subtotal = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    
    class Meta:
        model = ItemComboPedido
        fields = ['id', 'combo', 'nome_combo', 'quantidade', 'preco_unitario', 'subtotal']
        read_only_fields = ['id', 'subtotal']


class PedidoSerializer(serializers.ModelSerializer):
    """Order serializer."""
    itens = ItemPedidoSerializer(many=True, read_only=True)
    combos = ItemComboPedidoSerializer(many=True, read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    status_class = serializers.CharField(source='status_display_class', read_only=True)
    
    class Meta:
        model = Pedido
        fields = [
            'id', 'usuario', 'payment_id', 'preference_id',
            'status', 'status_display', 'status_class',
            'total', 'endereco_entrega', 'observacoes',
            'itens', 'combos',
            'criado_em', 'atualizado_em', 'data_pagamento'
        ]
        read_only_fields = [
            'id', 'usuario', 'payment_id', 'preference_id',
            'criado_em', 'atualizado_em', 'data_pagamento'
        ]


class PedidoListSerializer(serializers.ModelSerializer):
    """Simplified order serializer for list views."""
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    itens_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Pedido
        fields = [
            'id', 'status', 'status_display', 'total',
            'itens_count', 'criado_em'
        ]

    def get_itens_count(self, obj):
        return obj.itens.count() + obj.combos.count()


# =============================================================================
# CHECKOUT SERIALIZERS
# =============================================================================

class CheckoutSerializer(serializers.Serializer):
    """Serializer for checkout process."""
    endereco_entrega = serializers.CharField(required=False, allow_blank=True)
    observacoes = serializers.CharField(required=False, allow_blank=True)


class PaymentResponseSerializer(serializers.Serializer):
    """Response serializer for payment creation."""
    pedido_id = serializers.IntegerField()
    preference_id = serializers.CharField()
    init_point = serializers.URLField()
    sandbox_init_point = serializers.URLField(required=False)


# =============================================================================
# CATALOG SERIALIZERS (Combined views)
# =============================================================================

class CatalogoSerializer(serializers.Serializer):
    """Combined catalog serializer for home page."""
    massas_classicos = RondelliSerializer(many=True)
    massas_gourmet = RondelliSerializer(many=True)
    carnes = CarneSerializer(many=True)
    molhos = MolhoSerializer(many=True)
    combos = ComboSerializer(many=True)
