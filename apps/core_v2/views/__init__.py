"""Core v2 - Views. Django REST Framework viewsets and API views."""
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.authtoken.models import Token
from django.contrib.auth import authenticate, get_user_model
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator

User = get_user_model()


class UserViewSet(viewsets.ModelViewSet):
    """ViewSet for User management."""
    queryset = User.objects.all()
    permission_classes = [IsAuthenticated]
    lookup_field = 'id'

    def get_serializer_class(self):
        """Return appropriate serializer based on action."""
        from .serializers import UserSerializer, UserCreateSerializer, UserUpdateSerializer
        if self.action == 'create':
            return UserCreateSerializer
        elif self.action in ['update', 'partial_update']:
            if self.get_object() == self.request.user:
                return UserUpdateSerializer
        return UserSerializer

    def get_permissions(self):
        """Allow anyone to create users, but require auth for others."""
        if self.action == 'create':
            return [AllowAny()]
        return [IsAuthenticated()]

    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated])
    def me(self, request):
        """Return current user data."""
        from .serializers import UserSerializer
        serializer = UserSerializer(request.user)
        return Response(serializer.data)


@method_decorator(csrf_exempt, name='dispatch')
class LoginView(APIView):
    """
    Login view that returns DRF Token.
    CSRF exempt for cross-origin frontend support.
    """
    permission_classes = []
    authentication_classes = []

    def post(self, request):
        username = request.data.get('username')
        password = request.data.get('password')

        if not username or not password:
            return Response(
                {'error': 'Username e password são obrigatórios.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        user = authenticate(username=username, password=password)

        if user:
            token, created = Token.objects.get_or_create(user=user)
            return Response({
                'token': token.key,
                'user': {
                    'id': str(user.id),
                    'username': user.username,
                    'email': user.email,
                    'is_superuser': user.is_superuser,
                }
            })
        else:
            return Response(
                {'error': 'Credenciais inválidas.'},
                status=status.HTTP_401_UNAUTHORIZED
            )


class LogoutView(APIView):
    """Logout view that deletes the token."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if request.user.is_authenticated:
            Token.objects.filter(user=request.user).delete()
        return Response({'message': 'Logout realizado com sucesso.'})


class HealthCheckView(APIView):
    """Health check endpoint."""
    permission_classes = []
    authentication_classes = []

    def get(self, request):
        return Response({'status': 'ok', 'version': '2.0.0'})
