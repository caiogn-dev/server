"""Caixa de PDV — abertura, movimentos (sangria/reforço) e fechamento."""
from decimal import Decimal, InvalidOperation

from django.utils import timezone
from rest_framework import permissions, serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.stores.models import Store, StoreCashMovement, StoreCashSession
from .base import IsStoreOwnerOrStaff


class CashMovementSerializer(serializers.ModelSerializer):
    class Meta:
        model = StoreCashMovement
        fields = ['id', 'kind', 'amount', 'reason', 'created_by', 'created_at']
        read_only_fields = ['id', 'created_by', 'created_at']


class CashSessionSerializer(serializers.ModelSerializer):
    movements = CashMovementSerializer(many=True, read_only=True)
    expected_cash = serializers.SerializerMethodField()

    class Meta:
        model = StoreCashSession
        fields = [
            'id', 'status', 'opening_amount', 'opened_by', 'opened_at',
            'counted_amount', 'expected_amount', 'difference',
            'closed_by', 'closed_at', 'notes', 'movements', 'expected_cash',
        ]

    def get_expected_cash(self, obj):
        return str(obj.expected_cash())


def _get_store(store_slug):
    return Store.objects.filter(slug=store_slug).first()


def _get_open_session(store):
    return StoreCashSession.objects.filter(store=store, status='open').first()


def _parse_amount(raw):
    try:
        amount = Decimal(str(raw))
    except (InvalidOperation, TypeError):
        return None
    return amount if amount >= 0 else None


class CashSessionBaseView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsStoreOwnerOrStaff]


class CashOpenView(CashSessionBaseView):
    def post(self, request, store_slug):
        store = _get_store(store_slug)
        if not store:
            return Response({'detail': 'Loja não encontrada.'}, status=status.HTTP_404_NOT_FOUND)
        if _get_open_session(store):
            return Response({'detail': 'Já existe um caixa aberto nesta loja.'}, status=status.HTTP_409_CONFLICT)

        amount = _parse_amount(request.data.get('opening_amount', 0))
        if amount is None:
            return Response({'detail': 'opening_amount inválido.'}, status=status.HTTP_400_BAD_REQUEST)

        session = StoreCashSession.objects.create(
            store=store, opening_amount=amount, opened_by=request.user,
        )
        return Response(CashSessionSerializer(session).data, status=status.HTTP_201_CREATED)


class CashCurrentView(CashSessionBaseView):
    def get(self, request, store_slug):
        store = _get_store(store_slug)
        session = _get_open_session(store) if store else None
        if not session:
            return Response({'detail': 'Nenhum caixa aberto.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(CashSessionSerializer(session).data)


class CashMovementView(CashSessionBaseView):
    def post(self, request, store_slug):
        store = _get_store(store_slug)
        session = _get_open_session(store) if store else None
        if not session:
            return Response({'detail': 'Nenhum caixa aberto.'}, status=status.HTTP_400_BAD_REQUEST)

        kind = request.data.get('kind')
        if kind not in StoreCashMovement.Kind.values:
            return Response({'detail': 'kind deve ser sangria ou reforco.'}, status=status.HTTP_400_BAD_REQUEST)
        amount = _parse_amount(request.data.get('amount'))
        if not amount:
            return Response({'detail': 'amount inválido.'}, status=status.HTTP_400_BAD_REQUEST)

        movement = StoreCashMovement.objects.create(
            session=session, kind=kind, amount=amount,
            reason=request.data.get('reason', ''), created_by=request.user,
        )
        return Response(CashMovementSerializer(movement).data, status=status.HTTP_201_CREATED)


class CashCloseView(CashSessionBaseView):
    def post(self, request, store_slug):
        store = _get_store(store_slug)
        session = _get_open_session(store) if store else None
        if not session:
            return Response({'detail': 'Nenhum caixa aberto.'}, status=status.HTTP_400_BAD_REQUEST)

        counted = _parse_amount(request.data.get('counted_amount'))
        if counted is None:
            return Response({'detail': 'counted_amount inválido.'}, status=status.HTTP_400_BAD_REQUEST)

        expected = session.expected_cash()
        session.counted_amount = counted
        session.expected_amount = expected
        session.difference = counted - expected
        session.status = StoreCashSession.Status.CLOSED
        session.closed_by = request.user
        session.closed_at = timezone.now()
        session.notes = request.data.get('notes', session.notes)
        session.save()
        return Response(CashSessionSerializer(session).data)
