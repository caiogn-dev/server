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
from decimal import Decimal, InvalidOperation

from django.conf import settings
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
        'disponivel': ifood_oauth.esta_configurado('pedidos'),
        'entregas_disponivel': ifood_oauth.esta_configurado('entregas'),
        'merchant_id': (vinculo.merchant_id if vinculo else '') or '',
        'conectado': bool(vinculo and vinculo.conectado),
        'loja': (vinculo.merchant_name if vinculo else '') or '',
        'erro': (vinculo.ultimo_erro if vinculo else '') or '',
        'frete_pelo_ifood': bool(vinculo and vinculo.frete_pelo_ifood),
        'acrescimo_frete': f'{(vinculo.acrescimo_frete if vinculo else Decimal("0")):.2f}',
        'chamar_entregador': vinculo.chamar_entregador if vinculo else 'manual',
        'tempo_preparo_min': vinculo.tempo_preparo_min if vinculo else 15,
    }


def _estado_mercado_pago(loja) -> dict:
    gateways = StorePaymentGateway.objects.filter(
        store=loja, gateway_type=StorePaymentGateway.GatewayType.MERCADOPAGO, is_enabled=True,
    )
    if any(g.access_token for g in gateways):
        return {'conectado': True, 'conta': 'loja'}
    # Loja do próprio dono da plataforma: recebe no Mercado Pago dele
    # (MERCADO_PAGO_ACCESS_TOKEN) e não tem gateway cadastrado — está conectada.
    if loja.usa_gateway_da_plataforma and getattr(settings, 'MERCADO_PAGO_ACCESS_TOKEN', ''):
        return {'conectado': True, 'conta': 'plataforma'}
    return {'conectado': False, 'conta': None}


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


# ── iFood: app centralizado ──────────────────────────────────────────────
#
# O lojista informa o ID da loja no iFood e aprova o app Cardapidex no Portal
# do Parceiro. Não há código para trocar: o token é da plataforma.

def _loja_ou_erro(request):
    if not request.query_params.get('store'):
        return None, Response({'detail': 'Informe a loja.'}, status=400)
    loja = _loja(request)
    if loja is None:
        return None, Response({'detail': 'Loja não encontrada.'}, status=404)
    return loja, None


class IfoodConfigView(APIView):
    """POST com qualquer parte de: merchant_id, frete_pelo_ifood, acrescimo_frete,
    chamar_entregador, tempo_preparo_min."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        loja, erro = _loja_ou_erro(request)
        if erro:
            return erro
        dados = request.data or {}
        integracao = ifood_oauth.integracao_da_loja(loja)
        campos = []
        if 'frete_pelo_ifood' in dados:
            integracao.frete_pelo_ifood = bool(dados['frete_pelo_ifood'])
            campos.append('frete_pelo_ifood')
        if 'acrescimo_frete' in dados:
            try:
                valor = Decimal(str(dados['acrescimo_frete'] or '0').replace(',', '.')).quantize(Decimal('0.01'))
            except (InvalidOperation, ValueError):
                return Response({'detail': 'Acréscimo inválido.'}, status=400)
            if valor < 0 or valor > 100:
                return Response({'detail': 'Acréscimo entre 0 e 100.'}, status=400)
            integracao.acrescimo_frete = valor
            campos.append('acrescimo_frete')
        if 'chamar_entregador' in dados:
            if dados['chamar_entregador'] not in StoreIfoodIntegration.ChamarEntregador.values:
                return Response({'detail': 'Opção inválida.'}, status=400)
            integracao.chamar_entregador = dados['chamar_entregador']
            campos.append('chamar_entregador')
        if 'tempo_preparo_min' in dados:
            try:
                minutos = int(dados['tempo_preparo_min'])
            except (TypeError, ValueError):
                return Response({'detail': 'Tempo de preparo inválido.'}, status=400)
            if not 0 <= minutos <= 180:
                return Response({'detail': 'Tempo de preparo entre 0 e 180 min.'}, status=400)
            integracao.tempo_preparo_min = minutos
            campos.append('tempo_preparo_min')
        if campos:
            integracao.save(update_fields=[*campos, 'updated_at'])
        if 'merchant_id' in dados:
            try:
                ifood_oauth.vincular(loja, str(dados['merchant_id'] or ''))
            except ValueError as exc:
                return Response({'detail': str(exc)}, status=400)
        return Response(_estado_ifood(loja))


class IfoodDesconectarView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        loja, erro = _loja_ou_erro(request)
        if erro:
            return erro
        ifood_oauth.desconectar(loja)
        return Response(_estado_ifood(loja))


# ── iFood Merchant: status, pausas e horário da loja no iFood ────────────

class _LojaNoIfoodBase(APIView):
    permission_classes = [IsAuthenticated]

    def _responder(self, request, operacao=None):
        from ..services import loja_no_ifood
        loja, erro = _loja_ou_erro(request)
        if erro:
            return erro
        try:
            if operacao:
                operacao(loja_no_ifood, loja)
            return Response(loja_no_ifood.resumo(loja))
        except loja_no_ifood.LojaNoIfoodErro as exc:
            return Response({'detail': str(exc)}, status=400)


class LojaNoIfoodView(_LojaNoIfoodBase):
    def get(self, request):
        return self._responder(request)


class LojaNoIfoodPausarView(_LojaNoIfoodBase):
    def post(self, request):
        dados = request.data or {}
        return self._responder(request, lambda m, loja: m.pausar(
            loja, dados.get('minutos'), str(dados.get('motivo') or '')))


class LojaNoIfoodRetomarView(_LojaNoIfoodBase):
    def post(self, request):
        return self._responder(request, lambda m, loja: m.retomar(loja, (request.data or {}).get('id')))


class LojaNoIfoodHorariosView(_LojaNoIfoodBase):
    def put(self, request):
        horarios = (request.data or {}).get('horarios')
        if not isinstance(horarios, list):
            return Response({'detail': 'Envie os horários.'}, status=400)
        return self._responder(request, lambda m, loja: m.salvar_horarios(loja, horarios))


class IfoodMerchantsDoWidgetView(APIView):
    """IDs das lojas do usuário conectadas ao iFood, para o widget oficial.

    O widget aceita até 10 merchants e deve ser iniciado UMA vez por página com
    a lista certa: trocar a lista derruba a sessão (doc do iFood). Por isso vai
    a lista de todas as lojas acessíveis, não a loja selecionada.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from apps.core.permissions import accessible_store_ids
        ids = list(
            StoreIfoodIntegration.objects
            .filter(store_id__in=accessible_store_ids(request.user), conectado=True)
            .exclude(merchant_id='')
            .order_by('created_at')
            .values_list('merchant_id', flat=True)[:10]
        )
        return Response({'merchant_ids': ids})
