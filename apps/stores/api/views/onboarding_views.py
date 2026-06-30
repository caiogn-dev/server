"""Endpoint read-only do checklist de onboarding ("Primeiros passos")."""
from django.shortcuts import get_object_or_404
from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.stores.models import Store
from apps.stores.api.views.subscription_views import _can_manage
from apps.stores.services.onboarding_checklist import build_checklist


class StoreOnboardingChecklistView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, store_slug):
        store = get_object_or_404(Store, slug=store_slug)
        if not _can_manage(store, request.user):
            return Response({'detail': 'Sem permissão.'}, status=403)
        return Response(build_checklist(store))
