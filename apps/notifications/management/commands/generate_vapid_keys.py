"""
Management command to generate VAPID key pair for Web Push notifications.

Usage:
    python manage.py generate_vapid_keys

Output: prints VAPID_PRIVATE_KEY and VAPID_PUBLIC_KEY ready to paste into .env
"""
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Generate a VAPID key pair for Web Push notifications"

    def handle(self, *args, **options):
        try:
            from py_vapid import Vapid
        except ImportError:
            try:
                from pywebpush import Vapid
            except ImportError:
                self.stderr.write(self.style.ERROR(
                    "pywebpush is not installed. Run: pip install pywebpush"
                ))
                return

        vapid = Vapid()
        vapid.generate_keys()

        private_key = vapid.private_pem().decode("utf-8").strip()
        public_key = vapid.public_key.public_bytes(
            encoding=__import__("cryptography.hazmat.primitives.serialization", fromlist=["Encoding"]).Encoding.PEM,
            format=__import__("cryptography.hazmat.primitives.serialization", fromlist=["PublicFormat"]).PublicFormat.SubjectPublicKeyInfo,
        ).decode("utf-8").strip()

        # Also get the URL-safe base64 public key (used in the browser)
        try:
            public_key_b64 = vapid.public_key.public_bytes(
                encoding=__import__("cryptography.hazmat.primitives.serialization", fromlist=["Encoding"]).Encoding.X962,
                format=__import__("cryptography.hazmat.primitives.serialization", fromlist=["PublicFormat"]).PublicFormat.UncompressedPoint,
            )
            import base64
            public_key_url_safe = base64.urlsafe_b64encode(public_key_b64).decode("utf-8").rstrip("=")
        except Exception:
            public_key_url_safe = "(could not derive URL-safe key)"

        self.stdout.write(self.style.SUCCESS("\n=== VAPID Keys Generated ===\n"))
        self.stdout.write("Add these to your .env file:\n")
        self.stdout.write(f"VAPID_PRIVATE_KEY={private_key}")
        self.stdout.write(f"VAPID_PUBLIC_KEY={public_key_url_safe}")
        self.stdout.write(f"VAPID_CLAIMS_EMAIL=admin@yourdomain.com\n")
        self.stdout.write(
            "The VAPID_PUBLIC_KEY (URL-safe base64) is what you pass to "
            "PushManager.subscribe() in the browser as applicationServerKey.\n"
        )
