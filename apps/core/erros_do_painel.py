"""Recebe erro do navegador do painel e manda para o GlitchTip via logging.

Sem isto o erro de tela do operador morria no `console.error` do computador da
loja (05/10: o GlitchTip só tinha o projeto `server2`).

`logger.error` com a mensagem JÁ formatada: a integração do Sentry agrupa evento
de logging pelo texto, então cada erro distinto vira uma issue — e a rota vai sem
ids, senão o mesmo erro em cem pedidos viraria cem issues.
"""
import logging
import re

from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

logger = logging.getLogger(__name__)

_UUID = re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', re.I)
_NUMERO = re.compile(r'/\d+(?=/|$)')


class _ErrosThrottle(AnonRateThrottle):
    # Por IP, logado ou não: um loop de render quebrado não pode inundar o GlitchTip.
    scope = 'erros_do_painel'
    rate = '20/minute'

    def get_cache_key(self, request, view):
        return self.cache_format % {'scope': self.scope, 'ident': self.get_ident(request)}


def _texto(valor, limite: int) -> str:
    return str(valor or '').strip()[:limite]


def rota_sem_ids(rota: str) -> str:
    rota = _UUID.sub(':id', rota.split('?')[0])
    return _NUMERO.sub('/:n', rota)


class ErrosDoPainelView(APIView):
    """POST /api/v1/core/erros-do-painel/ — 204 sempre que registrou."""

    permission_classes = [permissions.AllowAny]
    throttle_classes = [_ErrosThrottle]

    def post(self, request):
        dados = request.data if isinstance(request.data, dict) else {}
        mensagem = _texto(dados.get('mensagem'), 300)
        if not mensagem:
            return Response({'error': 'mensagem é obrigatória'}, status=status.HTTP_400_BAD_REQUEST)

        rota = rota_sem_ids(_texto(dados.get('rota'), 200))
        usuario = getattr(request.user, 'id', None) if request.user.is_authenticated else None
        logger.error(
            f'[painel] {mensagem} — {rota or "?"}',
            extra={
                'painel_origem': _texto(dados.get('origem'), 30),
                'painel_versao': _texto(dados.get('versao'), 60),
                'painel_loja': _texto(dados.get('loja'), 80),
                'painel_pilha': _texto(dados.get('pilha'), 4000),
                'painel_navegador': _texto(request.META.get('HTTP_USER_AGENT'), 200),
                'usuario': usuario,
            },
        )
        return Response(status=status.HTTP_204_NO_CONTENT)
