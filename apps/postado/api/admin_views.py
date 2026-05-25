from rest_framework.views import APIView
from rest_framework.response import Response
from apps.postado.api.admin_auth import IsPostadoAdmin


class AdminDashboardView(APIView):
    permission_classes = [IsPostadoAdmin]

    def get(self, request):
        return Response({'status': 'ok'})
