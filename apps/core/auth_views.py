"""
Authentication views for the API.
"""
from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.core.exceptions import ObjectDoesNotExist
from django.middleware.csrf import get_token
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.authtoken.models import Token
from rest_framework import serializers
from drf_spectacular.utils import extend_schema
from .models import UserProfile
from apps.notifications.services import email_service


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)


class RegisterSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=8)
    first_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    phone = serializers.CharField(max_length=20, required=False, allow_blank=True)
    coupon_code = serializers.CharField(max_length=50, required=False, allow_blank=True)


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
        
        email = serializer.validated_data['email']
        password = serializer.validated_data['password']
        
        # Find user by email
        try:
            user_obj = User.objects.get(email=email)
            user = authenticate(username=user_obj.username, password=password)
        except User.DoesNotExist:
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
        
        # Check if email already exists
        if User.objects.filter(email=data['email']).exists():
            return Response(
                {'error': 'Email already exists'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Generate username from email (use part before @)
        base_username = data['email'].split('@')[0]
        username = base_username
        counter = 1
        while User.objects.filter(username=username).exists():
            username = f"{base_username}{counter}"
            counter += 1
        
        # Create user
        user = User.objects.create_user(
            username=username,
            email=data['email'],
            password=data['password'],
            first_name=data.get('first_name', ''),
            last_name=data.get('last_name', ''),
        )
        
        # Update profile with phone if provided
        if data.get('phone'):
            profile, _ = UserProfile.objects.get_or_create(user=user)
            profile.phone = data['phone']
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
