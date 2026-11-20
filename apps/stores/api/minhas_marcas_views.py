"""GET/PUT /api/v1/stores/minhas-marcas/?store=<slug> — ver services/minhas_marcas.py."""
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from ..services import minhas_marcas
from .repasse_99_views import _loja


class MinhasMarcasView(APIView):
    permission_classes = [IsAuthenticated]

    def _loja_do_dono(self, request):
        loja = _loja(request)
        if loja is None:
            return None, Response({'detail': 'Loja não encontrada.'}, status=404)
        if loja.owner_id != request.user.id:
            return None, Response({'detail': 'Só o dono da loja organiza as marcas.'}, status=403)
        return loja, None

    def get(self, request):
        loja, erro = self._loja_do_dono(request)
        if erro:
            return erro
        return Response({'marcas': minhas_marcas.listar(loja)})

    def put(self, request):
        loja, erro = self._loja_do_dono(request)
        if erro:
            return erro
        try:
            marcas = minhas_marcas.salvar(loja, request.data.get('marcas'))
        except minhas_marcas.MarcasErro as exc:
            return Response({'detail': str(exc)}, status=400)
        return Response({'marcas': marcas})
