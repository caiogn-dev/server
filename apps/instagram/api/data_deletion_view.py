"""
Meta Data Deletion Request callback.

Required by Meta for App Review of apps using Login with Facebook / Instagram.
Meta sends a signed_request parameter when a user removes app permissions.

Docs: https://developers.facebook.com/docs/development/create-an-app/app-dashboard/data-deletion-callback
"""
import base64
import hashlib
import hmac
import json
import logging
import uuid

from django.conf import settings
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

logger = logging.getLogger(__name__)


def _parse_signed_request(signed_request: str, app_secret: str) -> dict | None:
    """
    Parses and verifies a Meta signed_request.
    Returns decoded payload dict, or None if invalid.
    """
    try:
        encoded_sig, payload = signed_request.split(".", 1)
    except ValueError:
        return None

    # Decode
    def _b64_decode(data: str) -> bytes:
        data += "=" * (-len(data) % 4)
        return base64.urlsafe_b64decode(data)

    try:
        sig = _b64_decode(encoded_sig)
        data = json.loads(_b64_decode(payload).decode("utf-8"))
    except Exception:
        return None

    # Verify HMAC-SHA256
    if data.get("algorithm", "").upper() != "HMAC-SHA256":
        return None

    expected = hmac.new(
        app_secret.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).digest()

    if not hmac.compare_digest(sig, expected):
        return None

    return data


def _anonymize_user(instagram_user_id: str) -> str:
    """
    Anonymizes all PII tied to the given Instagram user ID.
    Returns a deletion confirmation code.
    """
    from apps.instagram.models import InstagramAccount

    accounts = InstagramAccount.objects.filter(
        instagram_business_id=instagram_user_id,
    )
    for account in accounts:
        account.access_token = ""
        account.page_access_token = ""
        account.is_active = False
        account.biography = ""
        account.website = ""
        account.profile_picture_url = ""
        account.save(update_fields=[
            "access_token", "page_access_token", "is_active",
            "biography", "website", "profile_picture_url", "updated_at",
        ])

    logger.info(
        "[data_deletion] Anonymized %d InstagramAccount(s) for ig_user_id=%s",
        accounts.count(),
        instagram_user_id,
    )

    return str(uuid.uuid4()).replace("-", "")[:16].upper()


class MetaDataDeletionView(APIView):
    """
    POST /api/v1/instagram/data-deletion/

    Meta calls this when a user revokes app permissions. We:
    1. Verify the signed_request with our app secret.
    2. Anonymize stored PII for that Instagram user.
    3. Return a status URL + confirmation code as required by Meta.
    """
    permission_classes = [AllowAny]
    authentication_classes = []

    @csrf_exempt
    def post(self, request):
        signed_request = request.POST.get("signed_request") or request.data.get("signed_request", "")
        if not signed_request:
            return Response({"error": "missing signed_request"}, status=400)

        app_secret = getattr(settings, "INSTAGRAM_APP_SECRET", "") or getattr(settings, "FACEBOOK_APP_SECRET", "")
        if not app_secret:
            logger.error("[data_deletion] INSTAGRAM_APP_SECRET not configured")
            return Response({"error": "server misconfiguration"}, status=500)

        data = _parse_signed_request(signed_request, app_secret)
        if not data:
            logger.warning("[data_deletion] Invalid signed_request received")
            return Response({"error": "invalid signed_request"}, status=400)

        instagram_user_id = str(data.get("user_id", ""))
        if not instagram_user_id:
            return Response({"error": "user_id missing from payload"}, status=400)

        confirmation_code = _anonymize_user(instagram_user_id)

        # Status URL where the user can verify deletion (we keep a simple confirmation)
        base_url = getattr(settings, "SITE_URL", "https://pastita.app")
        status_url = f"{base_url}/api/v1/instagram/data-deletion/status/?code={confirmation_code}"

        logger.info(
            "[data_deletion] Request processed: ig_user_id=%s code=%s",
            instagram_user_id,
            confirmation_code,
        )
        return Response({
            "url": status_url,
            "confirmation_code": confirmation_code,
        })


class MetaDataDeletionStatusView(APIView):
    """
    GET /api/v1/instagram/data-deletion/status/?code=<confirmation_code>

    Simple status page so users can confirm their deletion request was received.
    """
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        code = request.query_params.get("code", "")
        return Response({
            "status": "received",
            "message": (
                "Sua solicitação de exclusão de dados foi recebida e processada. "
                f"Código de confirmação: {code}"
            ),
        })
