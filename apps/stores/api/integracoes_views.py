"""A aba Integrações do painel: o estado de cada canal de venda da loja.

    GET /api/v1/stores/integracoes/?store=<id|slug>

Um endpoint só, para a tela não fazer uma chamada por canal e mostrar "não
conectado" no canal cuja chamada caiu. WhatsApp e Instagram ficam de fora:
são contas da empresa, não da loja, e a tela já os lê pelos endpoints deles.

99Food não tem "botão de conectar": as credenciais são da plataforma e a loja
é reconhecida pelo `app_shop_id` do aviso. Então "ativo" = chegou pedido.
"""
from __future__ import annotations

from datetime import timedelta

from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from ..models import StoreOrder, StorePaymentGateway
from ..models.ifood import StoreIfoodIntegration
from ..services import ifood_oauth
from ..services.pedidos_da_99 import PROVEDOR as FONTE_99
from .repasse_99_views import _loja


def _estado_99(loja) -> dict:
    pedidos = StoreOrder.objects.filter(store=loja, source=FONTE_99)
    ultimo = pedidos.order_by('-created_at').values_list('created_at', flat=True).first()
    return {
        'ativo': ultimo is not None,
        'ultimo_pedido_em': ultimo.isoformat() if ultimo else None,
        'pedidos_30_dias': pedidos.filter(created_at__gte=timezone.now() - timedelta(days=30)).count(),
    }


def _estado_ifood(loja) -> dict:
    vinculo = StoreIfoodIntegration.objects.filter(store=loja).first()
    return {
        'disponivel': ifood_oauth.esta_configurado(),
        'conectado': bool(vinculo and vinculo.conectado),
        'loja': (vinculo.merchant_name if vinculo else '') or '',
        'erro': (vinculo.ultimo_erro if vinculo else '') or '',
    }


def _estado_mercado_pago(loja) -> dict:
    gateways = StorePaymentGateway.objects.filter(
        store=loja, gateway_type=StorePaymentGateway.GatewayType.MERCADOPAGO, is_enabled=True,
    )
    conectado = any(g.access_token for g in gateways)
    return {'conectado': conectado}


class IntegracoesDaLojaView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not request.query_params.get('store'):
            return Response({'detail': 'Informe a loja.'}, status=400)
        loja = _loja(request)
        if loja is None:
            return Response({'detail': 'Loja não encontrada.'}, status=404)
        return Response({
            '99food': _estado_99(loja),
            'ifood': _estado_ifood(loja),
            'mercado_pago': _estado_mercado_pago(loja),
        })
