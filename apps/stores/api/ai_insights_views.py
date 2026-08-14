"""Endpoints de IA do painel (resumo diário + análise de conversas).

Escopo estrito por dono: o `?store=` só resolve lojas do usuário autenticado
(superuser vê todas). IA nunca é chamada por evento de cliente — só pelo dash.
"""
import logging

from django.core.cache import cache
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from ..models import Store

logger = logging.getLogger(__name__)

CACHE_TTL_SUMMARY = 6 * 3600

#: Prazo do fallback de template. Curto de propósito: guardar a versão pobre
#: pelas mesmas 6 horas prenderia o dono nela mesmo depois de o LLM voltar.
#: 10 minutos evitam repetir o timeout na mesma sessão e ainda tentam de novo
#: logo em seguida.
CACHE_TTL_FALLBACK = 10 * 60
CACHE_TTL_INSIGHTS = 12 * 3600


class BaseAIInsightsView(APIView):
    permission_classes = [IsAuthenticated]

    def get_store(self, request):
        param = request.query_params.get('store') or ''
        if not param:
            return None
        qs = Store.objects.all() if request.user.is_superuser else Store.objects.filter(owner=request.user)
        try:
            import uuid
            uuid.UUID(param)
            return qs.filter(id=param).first()
        except (ValueError, AttributeError):
            return qs.filter(slug=param).first()


class AIDailySummaryView(BaseAIInsightsView):
    """GET /api/v1/stores/ai/daily-summary/?store=<slug>[&refresh=1]"""

    def get(self, request):
        store = self.get_store(request)
        if not store:
            return Response({'error': 'Loja não encontrada'}, status=404)
        from ..services.ai_insights import compute_daily_stats, generate_daily_summary

        day_key = compute_daily_stats(store)['date']
        cache_key = f'ai:daily-summary:{store.id}:{day_key}'
        if request.query_params.get('refresh') != '1':
            cached = cache.get(cache_key)
            if cached:
                return Response({**cached, 'cached': True})
        data = generate_daily_summary(store)
        # O fallback de template TAMBÉM é cacheado, com prazo curto.
        #
        # Antes só o resultado do LLM entrava no cache, então quando o modelo
        # caía cada visita ao painel pagava o timeout inteiro de novo — o painel
        # ficava lento exatamente quando a IA estava quebrada, que é o pior
        # momento possível.
        #
        # Prazo curto de propósito: guardar o template pelas mesmas horas do
        # resultado bom prenderia o dono na versão pobre até o dia seguinte.
        ttl = CACHE_TTL_SUMMARY if data['source'] == 'llm' else CACHE_TTL_FALLBACK
        cache.set(cache_key, data, ttl)
        return Response({**data, 'cached': False})


class AIConversationInsightsView(BaseAIInsightsView):
    """GET /api/v1/stores/ai/conversation-insights/?store=<slug>[&days=7][&refresh=1]"""

    def get(self, request):
        store = self.get_store(request)
        if not store:
            return Response({'error': 'Loja não encontrada'}, status=404)
        try:
            days = min(max(int(request.query_params.get('days', 7)), 1), 30)
        except ValueError:
            days = 7
        from ..services.ai_insights import generate_conversation_insights

        cache_key = f'ai:conv-insights:{store.id}:{days}'
        if request.query_params.get('refresh') != '1':
            cached = cache.get(cache_key)
            if cached:
                return Response({**cached, 'cached': True})
        data = generate_conversation_insights(store, days)
        if data['source'] == 'llm':
            cache.set(cache_key, data, CACHE_TTL_INSIGHTS)
        return Response({**data, 'cached': False})
