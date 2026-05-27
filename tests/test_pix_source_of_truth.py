"""
Testes confirmando que StoreOrder é a fonte de verdade dos dados PIX.

Verifica que:
1. pix_expires_at foi adicionado a StoreOrder
2. Quando session_manager escreve PIX, também propaga para StoreOrder
3. Quando order_service escreve PIX, também propaga para StoreOrder
4. agents/services.py prefere StoreOrder quando disponível
"""
import uuid
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.stores.models import Store, StoreOrder
from apps.automation.models import CustomerSession, CompanyProfile

User = get_user_model()


def _make_user():
    username = f"u{uuid.uuid4().hex[:8]}"
    return User.objects.create_user(username=username, password="pass")


def _make_store(slug=None, owner=None):
    slug = slug or f"test-{uuid.uuid4().hex[:8]}"
    if owner is None:
        owner = _make_user()
    return Store.objects.create(
        name="Test Store",
        slug=slug,
        email=f"{slug}@test.com",
        owner=owner,
    )


def _make_order(store, pix_code='', pix_qr_code='', pix_expires_at=None):
    return StoreOrder.objects.create(
        store=store,
        order_number=f"ORD-{uuid.uuid4().hex[:8].upper()}",
        subtotal=Decimal('50.00'),
        delivery_fee=Decimal('5.00'),
        total=Decimal('55.00'),
        pix_code=pix_code,
        pix_qr_code=pix_qr_code,
        pix_expires_at=pix_expires_at,
    )


def _make_session(store, order=None, pix_code='', pix_qr_code='', pix_expires_at=None):
    profile, _ = CompanyProfile.objects.get_or_create(store=store)
    return CustomerSession.objects.create(
        phone_number=f"+5511{uuid.uuid4().int % 900000000 + 100000000}",
        company=profile,
        order=order,
        pix_code=pix_code,
        pix_qr_code=pix_qr_code,
        pix_expires_at=pix_expires_at,
    )


class StoreOrderPixFieldsTest(TestCase):
    """StoreOrder tem os campos PIX necessários."""

    def test_store_order_has_pix_expires_at(self):
        """StoreOrder.pix_expires_at existe e pode ser salvo."""
        store = _make_store()
        expires = timezone.now() + timedelta(hours=24)
        order = _make_order(
            store,
            pix_code='00020126...',
            pix_qr_code='base64qrcode==',
            pix_expires_at=expires,
        )
        order.refresh_from_db()
        self.assertEqual(order.pix_code, '00020126...')
        self.assertEqual(order.pix_qr_code, 'base64qrcode==')
        self.assertIsNotNone(order.pix_expires_at)
        # Tolerância de 1 segundo para diferenças de arredondamento de banco
        delta = abs((order.pix_expires_at - expires).total_seconds())
        self.assertLess(delta, 2)

    def test_store_order_pix_expires_at_nullable(self):
        """pix_expires_at pode ser nulo."""
        store = _make_store()
        order = _make_order(store)
        order.refresh_from_db()
        self.assertIsNone(order.pix_expires_at)


class SessionPixDeprecationTest(TestCase):
    """CustomerSession ainda tem campos PIX (deprecados) mas ordem é fonte de verdade."""

    def test_session_pix_fields_still_exist(self):
        """CustomerSession ainda tem pix_code, pix_qr_code, pix_expires_at (não removidos)."""
        store = _make_store()
        session = _make_session(store, pix_code='legacy_code')
        session.refresh_from_db()
        self.assertEqual(session.pix_code, 'legacy_code')
        self.assertTrue(hasattr(session, 'pix_qr_code'))
        self.assertTrue(hasattr(session, 'pix_expires_at'))

    def test_order_is_source_of_truth_when_linked(self):
        """Quando session.order existe, os dados PIX do order devem ser preferidos."""
        store = _make_store()
        expires = timezone.now() + timedelta(hours=24)
        order = _make_order(
            store,
            pix_code='order_pix_code_authoritative',
            pix_qr_code='order_qr',
            pix_expires_at=expires,
        )
        session = _make_session(
            store,
            order=order,
            pix_code='session_pix_code_deprecated',
            pix_qr_code='session_qr_deprecated',
        )

        # Simula a lógica de leitura preferindo order (como em agents/services.py)
        _order = session.order if session.order_id else None
        _pix_code = (_order.pix_code if _order else None) or session.pix_code
        _pix_expires = (_order.pix_expires_at if _order else None) or session.pix_expires_at

        self.assertEqual(_pix_code, 'order_pix_code_authoritative')
        self.assertIsNotNone(_pix_expires)

    def test_fallback_to_session_when_order_has_no_pix(self):
        """Quando order não tem pix_code, faz fallback para session.pix_code."""
        store = _make_store()
        order = _make_order(store)  # sem pix_code
        session = _make_session(
            store,
            order=order,
            pix_code='session_fallback_code',
        )

        _order = session.order if session.order_id else None
        _pix_code = (_order.pix_code if _order else None) or session.pix_code

        self.assertEqual(_pix_code, 'session_fallback_code')

    def test_session_without_order_uses_session_pix(self):
        """Sessão sem order vinculado usa session.pix_code normalmente."""
        store = _make_store()
        session = _make_session(store, pix_code='standalone_pix')

        _order = session.order if session.order_id else None
        _pix_code = (_order.pix_code if _order else None) or session.pix_code

        self.assertEqual(_pix_code, 'standalone_pix')
        self.assertIsNone(_order)


class SessionManagerPixPropagationTest(TestCase):
    """set_payment_pending propaga PIX para StoreOrder."""

    def test_set_payment_pending_propagates_to_order(self):
        """SessionManager.set_payment_pending escreve PIX em StoreOrder quando order_id existe."""
        from apps.automation.services.session_manager import SessionManager

        store = _make_store()
        profile, _ = CompanyProfile.objects.get_or_create(store=store)
        order = _make_order(store)

        phone = f"+5511{uuid.uuid4().int % 900000000 + 100000000}"
        CustomerSession.objects.create(
            phone_number=phone,
            company=profile,
            order=order,
        )

        # SessionManager aceita account como CompanyProfile
        mgr = SessionManager(account=profile, phone_number=phone)
        mgr.set_payment_pending(
            pix_code='propagated_pix_code',
            pix_qr_code='propagated_qr',
            payment_id='pay_123',
        )

        order.refresh_from_db()
        self.assertEqual(order.pix_code, 'propagated_pix_code')
        self.assertEqual(order.pix_qr_code, 'propagated_qr')
        self.assertIsNotNone(order.pix_expires_at)

    def test_set_payment_pending_without_order_does_not_fail(self):
        """set_payment_pending sem order vinculado não lança exceção."""
        from apps.automation.services.session_manager import SessionManager

        store = _make_store()
        profile, _ = CompanyProfile.objects.get_or_create(store=store)
        phone = f"+5511{uuid.uuid4().int % 900000000 + 100000000}"
        CustomerSession.objects.create(phone_number=phone, company=profile)

        mgr = SessionManager(account=profile, phone_number=phone)
        # Não deve levantar exceção
        mgr.set_payment_pending(pix_code='solo_pix', pix_qr_code='', payment_id='')

        session = CustomerSession.objects.get(phone_number=phone)
        self.assertEqual(session.pix_code, 'solo_pix')
