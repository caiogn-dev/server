"""
Authentication views for the API.
"""
import logging
from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.core.exceptions import ObjectDoesNotExist
from django.middleware.csrf import get_token
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.authtoken.models import Token
from rest_framework import serializers
from drf_spectacular.utils import extend_schema
from .models import UserProfile
from apps.notifications.services import email_service

logger = logging.getLogger(__name__)


class LoginSerializer(serializers.Serializer):
    email = serializers.CharField()
    password = serializers.CharField(write_only=True)


class RegisterSerializer(serializers.Serializer):
    email = serializers.EmailField(required=False, allow_blank=True)
    password = serializers.CharField(write_only=True, min_length=8)
    name = serializers.CharField(max_length=300, required=True)
    phone = serializers.CharField(max_length=20, required=True)
    coupon_code = serializers.CharField(max_length=50, required=False, allow_blank=True)
    store_slug = serializers.CharField(max_length=100, required=False, allow_blank=True)


class TokenSerializer(serializers.Serializer):
    token = serializers.CharField()
    user_id = serializers.IntegerField()
    username = serializers.CharField()
    email = serializers.EmailField()
    first_name = serializers.CharField()
    last_name = serializers.CharField()


class UserSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    username = serializers.CharField()
    email = serializers.EmailField()
    first_name = serializers.CharField()
    last_name = serializers.CharField()
    is_staff = serializers.BooleanField()
    is_superuser = serializers.BooleanField()
    date_joined = serializers.DateTimeField()


class UserProfileSerializer(serializers.Serializer):
    """Extended user profile serializer with all fields."""
    id = serializers.IntegerField(source='user.id')
    username = serializers.CharField(source='user.username')
    email = serializers.EmailField(source='user.email')
    first_name = serializers.CharField(source='user.first_name')
    last_name = serializers.CharField(source='user.last_name')
    phone = serializers.CharField(allow_blank=True)
    cpf = serializers.CharField(allow_blank=True)
    address = serializers.CharField(allow_blank=True)
    city = serializers.CharField(allow_blank=True)
    state = serializers.CharField(allow_blank=True)
    zip_code = serializers.CharField(allow_blank=True)


class UpdateProfileSerializer(serializers.Serializer):
    """Serializer for updating user profile."""
    first_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    email = serializers.EmailField(required=False)
    phone = serializers.CharField(max_length=20, required=False, allow_blank=True)
    cpf = serializers.CharField(max_length=14, required=False, allow_blank=True)
    address = serializers.CharField(required=False, allow_blank=True)
    city = serializers.CharField(max_length=100, required=False, allow_blank=True)
    state = serializers.CharField(max_length=2, required=False, allow_blank=True)
    zip_code = serializers.CharField(max_length=10, required=False, allow_blank=True)


@method_decorator(csrf_exempt, name='dispatch')
class LoginView(APIView):
    """Login endpoint to obtain authentication token."""
    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(
        summary="Login",
        description="Authenticate user and obtain token",
        request=LoginSerializer,
        responses={200: TokenSerializer}
    )
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        identifier = serializer.validated_data['email'].strip()
        password = serializer.validated_data['password']
        
        # Find user by email
        normalized_email = identifier.lower()
        user_obj = User.objects.filter(email__iexact=normalized_email).first()
        if not user_obj:
            user_obj = User.objects.filter(username__iexact=identifier).first()

        if user_obj:
            user = authenticate(username=user_obj.username, password=password)
        else:
            user = None
        
        if user is None:
            return Response(
                {'error': 'Invalid credentials'},
                status=status.HTTP_401_UNAUTHORIZED
            )
        
        if not user.is_active:
            return Response(
                {'error': 'User account is disabled'},
                status=status.HTTP_401_UNAUTHORIZED
            )
        
        token, _ = Token.objects.get_or_create(user=user)
        
        return Response({
            'token': token.key,
            'user_id': user.id,
            'username': user.username,
            'email': user.email,
            'first_name': user.first_name,
            'last_name': user.last_name,
        })


class LogoutView(APIView):
    """Logout endpoint to invalidate token."""
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Logout",
        description="Invalidate authentication token",
        responses={200: dict}
    )
    def post(self, request):
        try:
            request.user.auth_token.delete()
        except (AttributeError, ObjectDoesNotExist):
            # Token doesn't exist or user has no token - this is fine for logout
            pass
        
        return Response({'message': 'Successfully logged out'})


class CurrentUserView(APIView):
    """Get current authenticated user information."""
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Current User",
        description="Get current authenticated user information",
        responses={200: UserSerializer}
    )
    def get(self, request):
        user = request.user
        return Response({
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'is_staff': user.is_staff,
            'is_superuser': user.is_superuser,
            'date_joined': user.date_joined.isoformat(),
        })


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, min_length=8)


class ChangePasswordView(APIView):
    """Change password for authenticated user."""
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Change Password",
        description="Change password for authenticated user",
        request=ChangePasswordSerializer,
        responses={200: dict}
    )
    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        user = request.user
        
        if not user.check_password(serializer.validated_data['old_password']):
            return Response(
                {'error': 'Invalid old password'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        user.set_password(serializer.validated_data['new_password'])
        user.save()
        
        # Regenerate token
        Token.objects.filter(user=user).delete()
        new_token = Token.objects.create(user=user)
        
        return Response({
            'message': 'Password changed successfully',
            'token': new_token.key,
        })


class RegisterView(APIView):
    """Register a new user."""
    permission_classes = [AllowAny]
    authentication_classes = []

    def _trigger_new_user_automation(self, user, store_slug=None):
        """Trigger email automation for new user registration."""
        try:
            from apps.marketing.services.email_automation_service import email_automation_service
            from apps.stores.models import Store
            
            # Get store by slug or use default (pastita)
            store = None
            if store_slug:
                store = Store.objects.filter(slug=store_slug, is_active=True).first()
            
            if not store:
                # Try to get default store (pastita)
                store = Store.objects.filter(slug='pastita', is_active=True).first()
            
            if not store:
                # Get any active store
                store = Store.objects.filter(is_active=True).first()
            
            if store:
                customer_name = f"{user.first_name} {user.last_name}".strip() or user.email.split('@')[0]
                result = email_automation_service.on_new_user(
                    store_id=str(store.id),
                    email=user.email,
                    name=customer_name,
                )
                logger.info(f"New user automation triggered for {user.email}: {result}")
            else:
                logger.warning(f"No active store found for new user automation: {user.email}")
                
        except Exception as e:
            logger.error(f"Failed to trigger new user automation: {e}")

    @extend_schema(
        summary="Register",
        description="Register a new user account",
        request=RegisterSerializer,
        responses={201: TokenSerializer}
    )
    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        data = serializer.validated_data
        
        # Get name and split into first/last name
        full_name = data['name'].strip()
        name_parts = full_name.split(' ', 1)
        first_name = name_parts[0]
        last_name = name_parts[1] if len(name_parts) > 1 else ''
        
        # Get phone and create email from it if not provided
        phone = data.get('phone', '').strip()
        email = data.get('email', '').strip().lower() if data.get('email') else ''
        
        if not email and phone:
            # Create email from phone: +5511999999999 -> 5511999999999@pastita.local
            email = f"{phone.replace('+', '').replace('-', '').replace(' ', '')}@pastita.local"
        
        if not email:
            return Response(
                {'error': 'Email ou celular é obrigatório'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Check if email already exists
        if User.objects.filter(email__iexact=email).exists():
            return Response(
                {'email': ['Este e-mail já está cadastrado']},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Check if phone already exists
        if phone and UserProfile.objects.filter(phone=phone).exists():
            return Response(
                {'phone': ['Este celular já está cadastrado']},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Generate username from email
        base_username = email.split('@')[0][:20]  # Limit to 20 chars
        username = base_username
        counter = 1
        while User.objects.filter(username=username).exists():
            username = f"{base_username}{counter}"
            counter += 1
        
        # Create user
        user = User.objects.create_user(
            username=username,
            email=email,
            password=data['password'],
            first_name=first_name,
            last_name=last_name,
        )
        
        # Update profile with phone
        if phone:
            profile, _ = UserProfile.objects.get_or_create(user=user)
            profile.phone = phone
            profile.save()
        
        # Create token
        token = Token.objects.create(user=user)

        coupon_code = (data.get('coupon_code') or '').strip()
        if coupon_code.upper() == 'PASTITA10':
            subject = 'Cupom PASTITA10 confirmado'
            greeting_name = user.first_name or user.email
            html = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="utf-8">
                <style>
                    body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                    .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                    .header {{ background: #722F37; color: white; padding: 24px; text-align: center; border-radius: 10px 10px 0 0; }}
                    .content {{ background: #fff; padding: 24px; border: 1px solid #eee; }}
                    .coupon {{ font-size: 20px; font-weight: bold; color: #722F37; }}
                    .footer {{ background: #f9f9f9; padding: 16px; text-align: center; font-size: 12px; color: #666; border-radius: 0 0 10px 10px; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1 style="margin: 0;">Pastita</h1>
                        <p style="margin: 10px 0 0;">Cupom ativado no cadastro</p>
                    </div>
                    <div class="content">
                        <p>Ola, <strong>{greeting_name}</strong>!</p>
                        <p>Seu cadastro foi concluido com o cupom:</p>
                        <p class="coupon">PASTITA10</p>
                        <p>Use o cupom na sua primeira compra para obter o desconto.</p>
                    </div>
                    <div class="footer">
                        <p>Pastita - Massas Artesanais</p>
                    </div>
                </div>
            </body>
            </html>
            """
            email_service.send_email(user.email, subject, html)
        
        # Trigger new user email automation for all stores (or default store)
        self._trigger_new_user_automation(user, data.get('store_slug'))
        
        return Response({
            'token': token.key,
            'user_id': user.id,
            'username': user.username,
            'email': user.email,
            'first_name': user.first_name,
            'last_name': user.last_name,
        }, status=status.HTTP_201_CREATED)


class ProfileView(APIView):
    """Get and update user profile with extended fields."""
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Get Profile",
        description="Get current user profile with extended fields",
        responses={200: UserProfileSerializer}
    )
    def get(self, request):
        user = request.user
        profile, _ = UserProfile.objects.get_or_create(user=user)
        
        return Response({
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'phone': profile.phone,
            'cpf': profile.cpf,
            'address': profile.address,
            'city': profile.city,
            'state': profile.state,
            'zip_code': profile.zip_code,
        })

    @extend_schema(
        summary="Update Profile",
        description="Update current user profile",
        request=UpdateProfileSerializer,
        responses={200: UserProfileSerializer}
    )
    def patch(self, request):
        serializer = UpdateProfileSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        
        user = request.user
        data = serializer.validated_data
        
        # Update user fields
        if 'first_name' in data:
            user.first_name = data['first_name']
        if 'last_name' in data:
            user.last_name = data['last_name']
        if 'email' in data:
            # Check if email is already taken by another user
            if User.objects.filter(email=data['email']).exclude(id=user.id).exists():
                return Response(
                    {'error': 'Email already exists'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            user.email = data['email']
        user.save()
        
        # Update profile fields
        profile, _ = UserProfile.objects.get_or_create(user=user)
        if 'phone' in data:
            profile.phone = data['phone']
        if 'cpf' in data:
            profile.cpf = data['cpf']
        if 'address' in data:
            profile.address = data['address']
        if 'city' in data:
            profile.city = data['city']
        if 'state' in data:
            profile.state = data['state']
        if 'zip_code' in data:
            profile.zip_code = data['zip_code']
        profile.save()
        
        return Response({
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'phone': profile.phone,
            'cpf': profile.cpf,
            'address': profile.address,
            'city': profile.city,
            'state': profile.state,
            'zip_code': profile.zip_code,
        })


class CSRFTokenView(APIView):
    """Get CSRF token for frontend."""
    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(
        summary="Get CSRF Token",
        description="Get CSRF token for frontend forms",
        responses={200: dict}
    )
    def get(self, request):
        csrf_token = get_token(request)
        return Response({'csrfToken': csrf_token})
