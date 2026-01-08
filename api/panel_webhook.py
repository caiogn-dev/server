import hashlib
import hmac
import json
import logging
from typing import Any, Dict

import requests
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)


def _sign_payload(payload: bytes, secret: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    return f"v1={digest}"


def send_panel_webhook(event_type: str, data: Dict[str, Any]) -> None:
    url = getattr(settings, "PANEL_WEBHOOK_URL", "")
    secret = getattr(settings, "PANEL_WEBHOOK_SECRET", "")

    if not url or not secret:
        logger.warning("Panel webhook not configured (missing URL or SECRET).")
        return

    body = {
        "event": event_type,
        "data": data,
        "sent_at": timezone.now().isoformat(),
    }
    payload = json.dumps(body, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    signature = _sign_payload(payload, secret)

    try:
        response = requests.post(
            url,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "X-Pastita-Signature": signature,
            },
            timeout=5,
        )
        if response.status_code >= 400:
            logger.warning("Panel webhook failed: %s %s", response.status_code, response.text)
    except Exception as exc:
        logger.warning("Panel webhook request error: %s", exc)
