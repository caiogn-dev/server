"""
Core v2 - Serializers.

Django REST Framework serializers for core models.
"""
from rest_framework import serializers
from .models import User


class UserSerializer(serializers.ModelSerializer):
    """
    Serializer for User model.
    
    Used for reading and updating user data.
    """
    full_name = serializers.CharField(source='get_full_name', read_only=True)
    
    class Meta:
        model = User
        fields = [
            'id',
            'email',
            'username',
            'first_name',
            'last_name',
            'full_name',
            'phone',
            'is_active',
            'is_staff',
            'date_joined',
            'last_login',
            'timezone',
            'language',
            'metadata',
        ]
        read_only_fields = ['id', 'date_joined', 'last_login']


class UserCreateSerializer(serializers.ModelSerializer):
    """
    Serializer for creating new users.
    
    Includes password field which is write-only.
    """
    password = serializers.CharField(
        write_only=True,
        required=True,
        style={'input_type': 'password'}
    )
    password_confirm = serializers.CharField(
        write_only=True,
        required=True,
        style={'input_type': 'password'}
    )
    
    class Meta:
        model = User
        fields = [
            'email',
            'username',
            'password',
            'password_confirm',
            'first_name',
            'last_name',
            'phone',
        ]
    
    def validate(self, data):
        """Validate that passwords match."""
        if data['password'] != data['password_confirm']:
            raise serializers.ValidationError({
                'password_confirm': 'Passwords do not match.'
            })
        return data
    
    def create(self, validated_data):
        """Create user with hashed password."""
        validated_data.pop('password_confirm')
        password = validated_data.pop('password')
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user


class UserUpdateSerializer(serializers.ModelSerializer):
    """
    Serializer for updating user profile.
    """
    
    class Meta:
        model = User
        fields = [
            'first_name',
            'last_name',
            'phone',
            'timezone',
            'language',
            'metadata',
        ]


class ChangePasswordSerializer(serializers.Serializer):
    """
    Serializer for password change.
    """
    old_password = serializers.CharField(
        required=True,
        style={'input_type': 'password'}
    )
    new_password = serializers.CharField(
        required=True,
        style={'input_type': 'password'},
        min_length=8
    )
    new_password_confirm = serializers.CharField(
        required=True,
        style={'input_type': 'password'}
    )
    
    def validate(self, data):
        """Validate that new passwords match."""
        if data['new_password'] != data['new_password_confirm']:
            raise serializers.ValidationError({
                'new_password_confirm': 'New passwords do not match.'
            })
        return data
