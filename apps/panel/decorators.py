"""
Decorators for the Pastita Panel views.
"""
from functools import wraps
from django.shortcuts import redirect


def panel_login_required(view_func):
    """Redirect to panel login if user is not authenticated."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('panel:login')
        return view_func(request, *args, **kwargs)
    return wrapper


def store_required(view_func):
    """Redirect to store selector if no store is selected in session."""
    @wraps(view_func)
    @panel_login_required
    def wrapper(request, *args, **kwargs):
        if not request.session.get('panel_store_id'):
            return redirect('panel:stores')
        return view_func(request, *args, **kwargs)
    return wrapper
