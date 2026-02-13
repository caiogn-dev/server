"""
Core app for Pastita Platform.

Contains shared utilities, models, permissions, and middleware.
"""

from .permissions import (
    IsStoreOwner,
    IsStoreStaff,
    HasStoreAccess,
    IsOwnerOrReadOnly,
    IsSuperUserOrReadOnly,
    ReadOnly,
    IsWhatsAppAccountOwner,
    IsCompanyProfileOwner,
)

__all__ = [
    'IsStoreOwner',
    'IsStoreStaff',
    'HasStoreAccess',
    'IsOwnerOrReadOnly',
    'IsSuperUserOrReadOnly',
    'ReadOnly',
    'IsWhatsAppAccountOwner',
    'IsCompanyProfileOwner',
]
