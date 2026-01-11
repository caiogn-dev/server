"""
Pastita API Views - REST API endpoints for the Pastita app.
"""
import logging
from decimal import Decimal
from urllib.parse import quote

from django.conf import settings
from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404
from django.utils.timezone import now
from django.views.decorators.csrf import csrf_exempt

from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework.views import APIView

import mercadopago

from .models import (
    Produto, Molho, Carne, Rondelli, Combo,
    Carrinho, ItemCarrinho, ItemComboCarrinho,
    Pedido, ItemPedido, ItemComboPedido
)
from .serializers import (
    UserSerializer, UserProfileSerializer,
    ProdutoSerializer, MolhoSerializer, CarneSerializer, RondelliSerializer, ComboSerializer,
    CarrinhoSerializer, ItemCarrinhoSerializer, ItemComboCarrinhoSerializer,
    AddToCartSerializer, AddComboToCartSerializer, UpdateCartItemSerializer,
    PedidoSerializer, PedidoListSerializer,
    CheckoutSerializer, PaymentResponseSerializer, CatalogoSerializer
)

User = get_user_model()

logger = logging.getLogger(__name__)


# =============================================================================
# PRODUCT VIEWSETS
# =============================================================================

class ProdutoViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for all products (read-only)."""
    queryset = Produto.objects.filter(ativo=True)
    serializer_class = ProdutoSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Search filter
        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(nome__icontains=search) | queryset.filter(descricao__icontains=search)
        
        return queryset.order_by('-criado_em')


class MolhoViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for sauces."""
    queryset = Molho.objects.filter(ativo=True)
    serializer_class = MolhoSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Filter by type
        tipo = self.request.query_params.get('tipo')
        if tipo:
            queryset = queryset.filter(tipo=tipo)
        
        return queryset.order_by('-criado_em')


class CarneViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for meats."""
    queryset = Carne.objects.filter(ativo=True)
    serializer_class = CarneSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Filter by type
        tipo = self.request.query_params.get('tipo')
        if tipo:
            queryset = queryset.filter(tipo=tipo)
        
        return queryset.order_by('-criado_em')


class RondelliViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for rondelli pastas."""
    queryset = Rondelli.objects.filter(ativo=True)
    serializer_class = RondelliSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Filter by category
        categoria = self.request.query_params.get('categoria')
        if categoria:
            queryset = queryset.filter(categoria=categoria)
        
        # Filter by flavor
        sabor = self.request.query_params.get('sabor')
        if sabor:
            queryset = queryset.filter(sabor=sabor)
        
        return queryset.order_by('categoria', '-criado_em')

    @action(detail=False, methods=['get'])
    def classicos(self, request):
        """Get only classic rondelli."""
        queryset = self.get_queryset().filter(categoria='classicos')
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def gourmet(self, request):
        """Get only gourmet rondelli."""
        queryset = self.get_queryset().filter(categoria='gourmet')
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)


class ComboViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for combos."""
    queryset = Combo.objects.filter(ativo=True)
    serializer_class = ComboSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        return super().get_queryset().order_by('-destaque', '-criado_em')

    @action(detail=False, methods=['get'])
    def destaques(self, request):
        """Get featured combos."""
        queryset = self.get_queryset().filter(destaque=True)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)


# =============================================================================
# CATALOG VIEW
# =============================================================================

class CatalogoView(APIView):
    """Combined catalog view for home page."""
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        data = {
            'massas_classicos': RondelliSerializer(
                Rondelli.objects.filter(ativo=True, categoria='classicos').order_by('-criado_em'),
                many=True, context={'request': request}
            ).data,
            'massas_gourmet': RondelliSerializer(
                Rondelli.objects.filter(ativo=True, categoria='gourmet').order_by('-criado_em'),
                many=True, context={'request': request}
            ).data,
            'carnes': CarneSerializer(
                Carne.objects.filter(ativo=True).order_by('-criado_em'),
                many=True, context={'request': request}
            ).data,
            'molhos': MolhoSerializer(
                Molho.objects.filter(ativo=True).order_by('-criado_em'),
                many=True, context={'request': request}
            ).data,
            'combos': ComboSerializer(
                Combo.objects.filter(ativo=True).order_by('-destaque', '-criado_em'),
                many=True, context={'request': request}
            ).data,
        }
        return Response(data)


# =============================================================================
# CART VIEWS
# =============================================================================

class CarrinhoViewSet(viewsets.ViewSet):
    """ViewSet for shopping cart operations."""
    permission_classes = [permissions.IsAuthenticated]

    def get_cart(self, user):
        """Get or create cart for user."""
        cart, _ = Carrinho.objects.get_or_create(usuario=user)
        return cart

    def list(self, request):
        """Get current user's cart."""
        cart = self.get_cart(request.user)
        serializer = CarrinhoSerializer(cart, context={'request': request})
        return Response(serializer.data)

    @action(detail=False, methods=['post'])
    def adicionar_produto(self, request):
        """Add product to cart."""
        serializer = AddToCartSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        produto_id = serializer.validated_data['produto_id']
        quantidade = serializer.validated_data['quantidade']
        
        produto = get_object_or_404(Produto, pk=produto_id, ativo=True)
        cart = self.get_cart(request.user)
        
        item, created = ItemCarrinho.objects.get_or_create(
            carrinho=cart,
            produto=produto
        )
        
        if created:
            item.quantidade = quantidade
        else:
            item.quantidade += quantidade
        item.save()
        
        return Response({
            'message': f'{produto.nome} adicionado ao carrinho',
            'cart': CarrinhoSerializer(cart, context={'request': request}).data
        })

    @action(detail=False, methods=['post'])
    def adicionar_combo(self, request):
        """Add combo to cart."""
        serializer = AddComboToCartSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        combo_id = serializer.validated_data['combo_id']
        quantidade = serializer.validated_data['quantidade']
        
        combo = get_object_or_404(Combo, pk=combo_id, ativo=True)
        cart = self.get_cart(request.user)
        
        item, created = ItemComboCarrinho.objects.get_or_create(
            carrinho=cart,
            combo=combo
        )
        
        if not created:
            item.quantidade += quantidade
            item.save()
        
        return Response({
            'message': f'Combo {combo.nome} adicionado ao carrinho',
            'cart': CarrinhoSerializer(cart, context={'request': request}).data
        })

    @action(detail=False, methods=['post'], url_path='atualizar-produto/(?P<item_id>[^/.]+)')
    def atualizar_produto(self, request, item_id=None):
        """Update product quantity in cart."""
        serializer = UpdateCartItemSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        quantidade = serializer.validated_data['quantidade']
        
        item = get_object_or_404(
            ItemCarrinho,
            id=item_id,
            carrinho__usuario=request.user
        )
        
        if quantidade <= 0:
            item.delete()
            message = 'Item removido do carrinho'
        else:
            item.quantidade = quantidade
            item.save()
            message = 'Quantidade atualizada'
        
        cart = self.get_cart(request.user)
        return Response({
            'message': message,
            'cart': CarrinhoSerializer(cart, context={'request': request}).data
        })

    @action(detail=False, methods=['post'], url_path='atualizar-combo/(?P<item_id>[^/.]+)')
    def atualizar_combo(self, request, item_id=None):
        """Update combo quantity in cart."""
        serializer = UpdateCartItemSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        quantidade = serializer.validated_data['quantidade']
        
        item = get_object_or_404(
            ItemComboCarrinho,
            id=item_id,
            carrinho__usuario=request.user
        )
        
        if quantidade <= 0:
            item.delete()
            message = 'Combo removido do carrinho'
        else:
            item.quantidade = quantidade
            item.save()
            message = 'Quantidade atualizada'
        
        cart = self.get_cart(request.user)
        return Response({
            'message': message,
            'cart': CarrinhoSerializer(cart, context={'request': request}).data
        })

    @action(detail=False, methods=['delete'], url_path='remover-produto/(?P<item_id>[^/.]+)')
    def remover_produto(self, request, item_id=None):
        """Remove product from cart."""
        item = get_object_or_404(
            ItemCarrinho,
            id=item_id,
            carrinho__usuario=request.user
        )
        nome = item.produto.nome
        item.delete()
        
        cart = self.get_cart(request.user)
        return Response({
            'message': f'{nome} removido do carrinho',
            'cart': CarrinhoSerializer(cart, context={'request': request}).data
        })

    @action(detail=False, methods=['delete'], url_path='remover-combo/(?P<item_id>[^/.]+)')
    def remover_combo(self, request, item_id=None):
        """Remove combo from cart."""
        item = get_object_or_404(
            ItemComboCarrinho,
            id=item_id,
            carrinho__usuario=request.user
        )
        nome = item.combo.nome
        item.delete()
        
        cart = self.get_cart(request.user)
        return Response({
            'message': f'Combo {nome} removido do carrinho',
            'cart': CarrinhoSerializer(cart, context={'request': request}).data
        })

    @action(detail=False, methods=['delete'])
    def limpar(self, request):
        """Clear entire cart."""
        cart = self.get_cart(request.user)
        cart.itens.all().delete()
        cart.combos.all().delete()
        
        return Response({
            'message': 'Carrinho limpo',
            'cart': CarrinhoSerializer(cart, context={'request': request}).data
        })


# =============================================================================
# ORDER VIEWS
# =============================================================================

class PedidoViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for orders (read-only for users)."""
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Pedido.objects.filter(usuario=self.request.user).order_by('-criado_em')

    def get_serializer_class(self):
        if self.action == 'list':
            return PedidoListSerializer
        return PedidoSerializer

    @action(detail=True, methods=['get'])
    def status(self, request, pk=None):
        """Get order status."""
        pedido = self.get_object()
        return Response({
            'id': pedido.id,
            'status': pedido.status,
            'status_display': pedido.get_status_display()
        })

    @action(detail=True, methods=['get'])
    def whatsapp(self, request, pk=None):
        """Get WhatsApp confirmation URL."""
        pedido = self.get_object()
        
        # Build order message
        itens_texto = []
        for item in pedido.itens.all():
            itens_texto.append(f"- {item.quantidade}× {item.nome_produto}")
        for item in pedido.combos.all():
            itens_texto.append(f"- {item.quantidade}× Combo {item.nome_combo}")
        
        itens_str = "\n".join(itens_texto)
        
        mensagem = (
            f"Olá! Gostaria de confirmar meu pedido #{pedido.id}:\n\n"
            f"{itens_str}\n\n"
            f"Total: R$ {pedido.total:.2f}"
        )
        
        whatsapp_number = getattr(settings, 'PASTITA_WHATSAPP_NUMBER', '5563992957931')
        whatsapp_url = f"https://wa.me/{whatsapp_number}?text={quote(mensagem)}"
        
        return Response({
            'pedido_id': pedido.id,
            'whatsapp_url': whatsapp_url,
            'mensagem': mensagem
        })


# =============================================================================
# CHECKOUT / PAYMENT VIEWS
# =============================================================================

class CheckoutView(APIView):
    """Create payment and redirect to Mercado Pago."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = CheckoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        try:
            # Get cart
            cart = get_object_or_404(Carrinho, usuario=request.user)
            
            if not cart.tem_itens:
                return Response(
                    {'error': 'Carrinho vazio'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            total = float(cart.total)
            
            # Create order
            pedido = Pedido.objects.create(
                usuario=request.user,
                total=Decimal(str(total)),
                status='pendente',
                endereco_entrega=serializer.validated_data.get('endereco_entrega', ''),
                observacoes=serializer.validated_data.get('observacoes', '')
            )
            
            # Copy cart items to order
            for item in cart.itens.all():
                ItemPedido.objects.create(
                    pedido=pedido,
                    produto=item.produto,
                    nome_produto=item.produto.nome,
                    quantidade=item.quantidade,
                    preco_unitario=item.produto.preco
                )
            
            # Copy cart combos to order
            for item in cart.combos.all():
                ItemComboPedido.objects.create(
                    pedido=pedido,
                    combo=item.combo,
                    nome_combo=item.combo.nome,
                    quantidade=item.quantidade,
                    preco_unitario=item.combo.preco
                )
            
            # Clear cart
            cart.itens.all().delete()
            cart.combos.all().delete()
            
            # Create Mercado Pago preference
            access_token = getattr(settings, 'MERCADO_PAGO_ACCESS_TOKEN', None)
            if not access_token:
                pedido.status = 'falhou'
                pedido.save()
                return Response(
                    {'error': 'Mercado Pago não configurado'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
            
            sdk = mercadopago.SDK(access_token)
            
            # Build items list
            items = []
            for item in pedido.itens.all():
                items.append({
                    "id": str(item.produto.id) if item.produto else str(item.id),
                    "title": item.nome_produto[:127],
                    "quantity": int(item.quantidade),
                    "currency_id": "BRL",
                    "unit_price": float(item.preco_unitario)
                })
            
            for item in pedido.combos.all():
                items.append({
                    "id": f"combo_{item.combo.id}" if item.combo else f"combo_{item.id}",
                    "title": f"Combo: {item.nome_combo[:120]}",
                    "quantity": int(item.quantidade),
                    "currency_id": "BRL",
                    "unit_price": float(item.preco_unitario)
                })
            
            # Get base URL for callbacks
            base_url = getattr(settings, 'PASTITA_BASE_URL', request.build_absolute_uri('/')[:-1])
            
            preference_data = {
                "items": items,
                "payer": {
                    "email": request.user.email,
                    "name": request.user.first_name[:127] if request.user.first_name else "Cliente",
                    "surname": request.user.last_name[:127] if request.user.last_name else "Pastita",
                },
                "back_urls": {
                    "success": f"{base_url}/pagamento/sucesso",
                    "failure": f"{base_url}/pagamento/falha",
                    "pending": f"{base_url}/pagamento/pendente",
                },
                "auto_return": "approved",
                "external_reference": str(pedido.id),
                "notification_url": f"{base_url}/api/v1/pastita/webhook/mercadopago/",
                "binary_mode": True,
            }
            
            response = sdk.preference().create(preference_data)
            
            if response['status'] not in (200, 201):
                msg = response.get('response', {}).get('message', 'Erro no Mercado Pago')
                logger.error(f"Mercado Pago error: {msg}")
                pedido.status = 'falhou'
                pedido.save()
                return Response(
                    {'error': f'Erro no Mercado Pago: {msg}'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
            
            pref = response['response']
            pedido.preference_id = pref['id']
            pedido.save()
            
            # Return payment URLs
            return Response({
                'pedido_id': pedido.id,
                'preference_id': pref['id'],
                'init_point': pref.get('init_point'),
                'sandbox_init_point': pref.get('sandbox_init_point'),
            })
            
        except Exception as e:
            logger.exception("Erro ao criar pagamento")
            if 'pedido' in locals():
                pedido.status = 'falhou'
                pedido.save()
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


# =============================================================================
# WEBHOOK
# =============================================================================

@csrf_exempt
@api_view(['GET', 'POST', 'HEAD'])
@permission_classes([permissions.AllowAny])
def mercado_pago_webhook(request):
    """Handle Mercado Pago webhook notifications."""
    
    # Accept GET/HEAD for verification
    if request.method in ("GET", "HEAD"):
        return Response({"status": "ok"})
    
    try:
        payload = request.data
        action = payload.get('action') or payload.get('topic') or payload.get('type')
        resource = payload.get('data', {}).get('id')
        
        logger.info(f"Webhook received: action={action}, resource={resource}")
        
        access_token = getattr(settings, 'MERCADO_PAGO_ACCESS_TOKEN', None)
        if not access_token:
            logger.error("Mercado Pago access token not configured")
            return Response({"status": "ok"})
        
        sdk = mercadopago.SDK(access_token)

        if action and 'payment' in action:
            # Get payment details
            pay = sdk.payment().get(resource).get('response', {})
            ref = pay.get('external_reference')
            
            pedido = Pedido.objects.filter(id=ref).first()
            
            if pedido:
                status_map = {
                    'approved': 'aprovado',
                    'pending': 'pendente',
                    'in_process': 'processando',
                    'rejected': 'falhou',
                    'refunded': 'reembolsado',
                    'cancelled': 'cancelado',
                    'in_mediation': 'em_mediacao',
                    'charged_back': 'estornado',
                }
                
                new_status = status_map.get(pay.get('status'), pedido.status)
                pedido.status = new_status
                pedido.payment_id = str(resource)
                pedido.atualizado_em = now()
                
                if new_status == 'aprovado':
                    pedido.data_pagamento = now()
                
                pedido.save()
                logger.info(f"Pedido {pedido.id} updated to {new_status}")

        elif action and 'merchant_order' in action:
            # Handle merchant orders
            mo = sdk.merchant_order().get(resource).get('response', {})
            
            for p in mo.get('payments', []):
                ref = p.get('external_reference')
                pedido = Pedido.objects.filter(id=ref).first()
                
                if pedido and p.get('status') == 'approved':
                    pedido.status = 'aprovado'
                    pedido.payment_id = str(p.get('id'))
                    pedido.data_pagamento = now()
                    pedido.save()
                    logger.info(f"Pedido {pedido.id} approved via merchant_order")

    except Exception as e:
        logger.exception(f"Erro ao processar webhook: {e}")
    
    # Always return 200 to acknowledge receipt
    return Response({"status": "ok"})


# =============================================================================
# AUTH VIEWS
# =============================================================================

class RegisterView(APIView):
    """User registration endpoint."""
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = UserSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            return Response({
                'message': 'Conta criada com sucesso',
                'user': UserProfileSerializer(user).data
            }, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ProfileView(APIView):
    """User profile endpoint."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        serializer = UserProfileSerializer(request.user)
        return Response(serializer.data)

    def patch(self, request):
        serializer = UserProfileSerializer(request.user, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
