"""
Shared customer identity helpers for storefront checkout and WhatsApp auth.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional, Tuple

from django.contrib.auth import get_user_model

from apps.core.models import UserProfile
from apps.core.utils import clean_cpf, normalize_phone_number

if TYPE_CHECKING:
    from apps.stores.models import Store

logger = logging.getLogger(__name__)


class CustomerIdentityService:
    """Resolve and persist customer identity across checkout and auth flows."""

    PLACEHOLDER_DOMAIN = "@pastita.local"

    @staticmethod
    def digits_only(value: str) -> str:
        return "".join(ch for ch in str(value or "") if ch.isdigit())

    @classmethod
    def phone_candidates(cls, phone_number: str) -> list[str]:
        digits = cls.digits_only(phone_number)
        if not digits:
            return []

        normalized = normalize_phone_number(digits)
        candidates = {digits, normalized, f"+{digits}", f"+{normalized}"}

        if normalized.startswith("55") and len(normalized) > 11:
            local_digits = normalized[2:]
            candidates.add(local_digits)
            candidates.add(f"+{local_digits}")

        return [candidate for candidate in candidates if candidate]

    @staticmethod
    def split_name(full_name: str) -> Tuple[str, str]:
        parts = (full_name or "").strip().split(" ", 1)
        first_name = parts[0] if parts and parts[0] else ""
        last_name = parts[1] if len(parts) > 1 else ""
        return first_name, last_name

    @staticmethod
    def normalize_state(state: str, fallback: str = "") -> str:
        value = str(state or fallback or "").strip()
        if not value:
            return ""

        if len(value) == 2 and value.isalpha():
            return value.upper()

        letters_only = "".join(ch for ch in value if ch.isalpha())
        if len(letters_only) >= 2:
            return letters_only[:2].upper()

        return value.upper()[:2]

    @classmethod
    def generate_unique_username(cls, base_username: str) -> str:
        user_model = get_user_model()
        cleaned = "".join(
            ch if ch.isalnum() else "_"
            for ch in (base_username or "cliente")
        ).strip("_").lower() or "cliente"
        cleaned = cleaned[:24]

        username = cleaned
        counter = 1
        while user_model.objects.filter(username=username).exists():
            suffix = str(counter)
            username = f"{cleaned[:max(1, 24 - len(suffix))]}{suffix}"
            counter += 1

        return username

    @classmethod
    def _placeholder_email(cls, phone_number: str, username: str) -> str:
        phone_digits = cls.digits_only(phone_number)
        if phone_digits:
            return f"{phone_digits}{cls.PLACEHOLDER_DOMAIN}"
        return f"{username}{cls.PLACEHOLDER_DOMAIN}"

    @classmethod
    def resolve_user(
        cls,
        *,
        email: str = "",
        phone: str = "",
        full_name: str = "",
        user=None,
        create: bool = True,
    ):
        """
        Resolve or create a Django auth user using email and phone.

        Phone match has priority because WhatsApp auth is phone-based.
        """
        user_model = get_user_model()
        normalized_email = (email or "").strip().lower()
        normalized_phone = normalize_phone_number(phone) if cls.digits_only(phone) else ""
        first_name, last_name = cls.split_name(full_name)

        if user and getattr(user, "is_authenticated", False):
            profile, _ = UserProfile.objects.get_or_create(user=user)
            return user, profile, False

        profile = None
        phone_user = None
        email_user = None
        user_created = False

        if normalized_phone:
            profile = (
                UserProfile.objects.select_related("user")
                .filter(phone__in=cls.phone_candidates(normalized_phone))
                .first()
            )
            if profile:
                phone_user = profile.user

        if normalized_email:
            email_user = user_model.objects.filter(email__iexact=normalized_email).first()

        if phone_user and email_user and phone_user.id != email_user.id:
            logger.warning(
                "Customer identity conflict between phone and email. "
                "Prioritizing phone-matched user for WhatsApp continuity. "
                "phone=%s email=%s phone_user_id=%s email_user_id=%s",
                normalized_phone,
                normalized_email,
                phone_user.id,
                email_user.id,
            )

        resolved_user = phone_user or email_user

        if not resolved_user and create:
            username = cls.generate_unique_username(
                f"cliente_{normalized_phone or normalized_email.split('@')[0] or 'guest'}"
            )
            resolved_user = user_model.objects.create(
                username=username,
                email=normalized_email or cls._placeholder_email(normalized_phone, username),
                first_name=first_name,
                last_name=last_name,
                is_active=True,
            )
            resolved_user.set_unusable_password()
            resolved_user.save(update_fields=["password"])
            user_created = True

        if not resolved_user:
            return None, None, False

        profile = profile or UserProfile.objects.select_related("user").filter(user=resolved_user).first()
        if not profile:
            profile = UserProfile.objects.create(user=resolved_user)

        user_updates = []
        if first_name and resolved_user.first_name != first_name:
            resolved_user.first_name = first_name
            user_updates.append("first_name")
        if last_name and resolved_user.last_name != last_name:
            resolved_user.last_name = last_name
            user_updates.append("last_name")

        if normalized_email and normalized_email != (resolved_user.email or "").strip().lower():
            email_in_use = user_model.objects.filter(email__iexact=normalized_email).exclude(id=resolved_user.id).exists()
            if not email_in_use:
                resolved_user.email = normalized_email
                user_updates.append("email")

        if user_updates:
            resolved_user.save(update_fields=user_updates)

        profile_updates = []
        if normalized_phone and profile.phone != normalized_phone:
            profile.phone = normalized_phone
            profile_updates.append("phone")

        if profile_updates:
            profile.save(update_fields=profile_updates)

        return resolved_user, profile, user_created

    @classmethod
    def _build_address_record(cls, delivery_address: Optional[dict], store: Optional["Store"] = None) -> Optional[dict]:
        address = dict(delivery_address or {})
        normalized = {
            "street": (address.get("street") or address.get("address") or "").strip(),
            "number": str(address.get("number") or "").strip(),
            "complement": str(address.get("complement") or "").strip(),
            "neighborhood": str(address.get("neighborhood") or "").strip(),
            "city": str(address.get("city") or getattr(store, "city", "") or "").strip(),
            "state": cls.normalize_state(
                address.get("state") or "",
                fallback=getattr(store, "state", ""),
            ),
            "zip_code": cls.digits_only(address.get("zip_code") or ""),
            "reference": str(address.get("reference") or address.get("landmark") or "").strip(),
        }

        if not any(normalized.values()):
            return None

        line_1 = normalized["street"]
        if normalized["number"]:
            line_1 = f"{line_1}, {normalized['number']}" if line_1 else normalized["number"]

        extras = [normalized["complement"], normalized["neighborhood"]]
        line_2 = " - ".join([value for value in extras if value])
        normalized["formatted"] = ", ".join(
            [part for part in [line_1, line_2, normalized["city"], normalized["state"]] if part]
        )
        return normalized

    @classmethod
    def sync_checkout_customer(
        cls,
        *,
        store: "Store",
        customer_name: str = "",
        email: str = "",
        phone: str = "",
        cpf: str = "",
        delivery_method: str = "",
        delivery_address: Optional[dict] = None,
        user=None,
    ) -> dict:
        """
        Persist checkout customer data across User, UserProfile and StoreCustomer.
        """
        resolved_user, profile, user_created = cls.resolve_user(
            email=email,
            phone=phone,
            full_name=customer_name,
            user=user,
            create=True,
        )

        if not resolved_user or not profile:
            return {
                "user": None,
                "profile": None,
                "store_customer": None,
                "user_created": False,
            }

        normalized_phone = normalize_phone_number(phone) if cls.digits_only(phone) else ""
        normalized_cpf = clean_cpf(cpf or "")
        normalized_address = (
            cls._build_address_record(delivery_address, store=store)
            if delivery_method == "delivery"
            else None
        )

        profile_updates = []
        if normalized_phone and profile.phone != normalized_phone:
            profile.phone = normalized_phone
            profile_updates.append("phone")
        if normalized_cpf and profile.cpf != normalized_cpf:
            profile.cpf = normalized_cpf
            profile_updates.append("cpf")
        if normalized_address:
            if normalized_address["formatted"] and profile.address != normalized_address["formatted"]:
                profile.address = normalized_address["formatted"]
                profile_updates.append("address")
            if normalized_address["city"] and profile.city != normalized_address["city"]:
                profile.city = normalized_address["city"]
                profile_updates.append("city")
            if normalized_address["state"] and profile.state != normalized_address["state"]:
                profile.state = normalized_address["state"]
                profile_updates.append("state")
            if normalized_address["zip_code"] and profile.zip_code != normalized_address["zip_code"]:
                profile.zip_code = normalized_address["zip_code"]
                profile_updates.append("zip_code")

        if profile_updates:
            profile.save(update_fields=profile_updates)

        from apps.stores.models import StoreCustomer

        store_customer, _ = StoreCustomer.objects.get_or_create(
            store=store,
            user=resolved_user,
            defaults={
                "phone": normalized_phone,
                "whatsapp": normalized_phone,
            },
        )

        store_customer_updates = []
        if normalized_phone and store_customer.phone != normalized_phone:
            store_customer.phone = normalized_phone
            store_customer_updates.append("phone")
        if normalized_phone and store_customer.whatsapp != normalized_phone:
            store_customer.whatsapp = normalized_phone
            store_customer_updates.append("whatsapp")

        if normalized_address:
            addresses = list(store_customer.addresses or [])
            existing_index = next(
                (
                    index for index, current in enumerate(addresses)
                    if cls._build_address_record(current, store=store) == normalized_address
                ),
                None,
            )
            if existing_index is None:
                addresses.insert(0, normalized_address)
                store_customer.addresses = addresses
                store_customer.default_address_index = 0
                store_customer_updates.extend(["addresses", "default_address_index"])
            elif store_customer.default_address_index != existing_index:
                store_customer.default_address_index = existing_index
                store_customer_updates.append("default_address_index")

        if store_customer_updates:
            store_customer.save(update_fields=store_customer_updates)

        return {
            "user": resolved_user,
            "profile": profile,
            "store_customer": store_customer,
            "user_created": user_created,
        }
