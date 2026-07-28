"""
Regressão de segurança: campo `account` gravável em InstagramMediaSerializer
e InstagramConversationSerializer — IDOR cross-tenant [P1].

Vetores de ataque (antes da correção):
  POST /api/v1/instagram/media/ {"account": victim_account_id, ...}
    → cria mídia na fila de publicação da vítima.
  PATCH /api/v1/instagram/media/{id}/ {"account": victim_account_id}
    → move mídia existente para a conta da vítima.
  POST /api/v1/instagram/conversations/ {"account": victim_account_id, ...}
    → injeta conversa na inbox DM da vítima.
  PATCH /api/v1/instagram/conversations/{id}/ {"account": victim_account_id}
    → move conversa para inbox da vítima.

Correção esperada:
  - 'account' em read_only_fields nos dois serializers (bloqueia PATCH).
  - perform_create em ambos os ViewSets valida user=request.user antes de
    injetar o account em serializer.save(account=...) (bloqueia POST cross-tenant).
"""
import os
import re

from django.test import SimpleTestCase

_SERIALIZERS_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', 'api', 'serializers.py')
)
_VIEWS_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', 'api', 'views.py')
)


def _read(path):
    with open(path) as f:
        return f.read()


def _extract_class(source, class_name):
    """Extrai o bloco de uma classe até a próxima classe de nível raiz ou EOF."""
    match = re.search(
        rf"^class {re.escape(class_name)}\b.*?(?=\n^class |\Z)",
        source,
        re.DOTALL | re.MULTILINE,
    )
    return match.group(0) if match else None


# ──────────────────────────────────────────────────────────────────────────────
# Serializer: InstagramMediaSerializer
# ──────────────────────────────────────────────────────────────────────────────

class InstagramMediaSerializerAccountReadOnlyTest(SimpleTestCase):
    """InstagramMediaSerializer.account deve ser read_only (bloqueia PATCH cross-tenant)."""

    def setUp(self):
        self.block = _extract_class(_read(_SERIALIZERS_PATH), "InstagramMediaSerializer")

    def test_class_exists(self):
        self.assertIsNotNone(self.block, "InstagramMediaSerializer não encontrado em serializers.py")

    def test_account_in_read_only_fields(self):
        ro = re.search(r"read_only_fields\s*=\s*\[([^\]]+)\]", self.block)
        self.assertIsNotNone(ro, "InstagramMediaSerializer não possui read_only_fields")
        self.assertIn(
            "'account'",
            ro.group(1),
            "InstagramMediaSerializer.Meta.read_only_fields não contém 'account' — "
            "PATCH /instagram/media/{id}/ {\"account\": victim_id} é aceito sem validação",
        )

    def test_existing_read_only_fields_preserved(self):
        ro = re.search(r"read_only_fields\s*=\s*\[([^\]]+)\]", self.block)
        for field in ("'id'", "'created_at'", "'updated_at'"):
            self.assertIn(field, ro.group(1),
                          f"Regressão: {field} removido de InstagramMediaSerializer.read_only_fields")


# ──────────────────────────────────────────────────────────────────────────────
# Serializer: InstagramConversationSerializer
# ──────────────────────────────────────────────────────────────────────────────

class InstagramConversationSerializerAccountReadOnlyTest(SimpleTestCase):
    """InstagramConversationSerializer.account deve ser read_only."""

    def setUp(self):
        self.block = _extract_class(_read(_SERIALIZERS_PATH), "InstagramConversationSerializer")

    def test_class_exists(self):
        self.assertIsNotNone(self.block, "InstagramConversationSerializer não encontrado em serializers.py")

    def test_account_in_read_only_fields(self):
        ro = re.search(r"read_only_fields\s*=\s*\[([^\]]+)\]", self.block)
        self.assertIsNotNone(ro, "InstagramConversationSerializer não possui read_only_fields")
        self.assertIn(
            "'account'",
            ro.group(1),
            "InstagramConversationSerializer.Meta.read_only_fields não contém 'account' — "
            "PATCH /instagram/conversations/{id}/ {\"account\": victim_id} transfere conversa DM",
        )

    def test_existing_read_only_fields_preserved(self):
        ro = re.search(r"read_only_fields\s*=\s*\[([^\]]+)\]", self.block)
        for field in ("'id'", "'created_at'", "'updated_at'"):
            self.assertIn(field, ro.group(1),
                          f"Regressão: {field} removido de InstagramConversationSerializer.read_only_fields")


# ──────────────────────────────────────────────────────────────────────────────
# ViewSet: InstagramMediaViewSet.perform_create
# ──────────────────────────────────────────────────────────────────────────────

class InstagramMediaViewSetPerformCreateTest(SimpleTestCase):
    """InstagramMediaViewSet.perform_create deve validar ownership da conta antes de criar."""

    def setUp(self):
        self.block = _extract_class(_read(_VIEWS_PATH), "InstagramMediaViewSet")

    def test_perform_create_defined(self):
        self.assertIn(
            "def perform_create",
            self.block,
            "InstagramMediaViewSet não possui perform_create — "
            "POST /instagram/media/ com account alheio não é validado",
        )

    def test_perform_create_validates_user_ownership(self):
        has_guard = (
            "user=self.request.user" in self.block
            or "filter(user=" in self.block
        )
        self.assertTrue(
            has_guard,
            "perform_create de InstagramMediaViewSet não filtra por user=request.user — "
            "POST com account_id da vítima seria aceito",
        )

    def test_perform_create_injects_account_into_save(self):
        self.assertIn(
            "serializer.save",
            self.block,
            "perform_create não chama serializer.save",
        )
        self.assertIn(
            "account=",
            self.block,
            "perform_create não injeta account em serializer.save(account=...) — "
            "objeto criado sem FK para a conta validada",
        )

    def test_perform_create_has_guard_against_missing_account(self):
        has_guard = (
            "ValidationError" in self.block
            or "get_object_or_404" in self.block
            or "Http404" in self.block
        )
        self.assertTrue(
            has_guard,
            "perform_create não rejeita request sem account — "
            "criação sem account geraria IntegrityError em produção",
        )


# ──────────────────────────────────────────────────────────────────────────────
# ViewSet: InstagramConversationViewSet.perform_create
# ──────────────────────────────────────────────────────────────────────────────

class InstagramConversationViewSetPerformCreateTest(SimpleTestCase):
    """InstagramConversationViewSet.perform_create deve validar ownership da conta."""

    def setUp(self):
        self.block = _extract_class(_read(_VIEWS_PATH), "InstagramConversationViewSet")

    def test_perform_create_defined(self):
        self.assertIn(
            "def perform_create",
            self.block,
            "InstagramConversationViewSet não possui perform_create — "
            "POST /instagram/conversations/ com account alheio não é validado",
        )

    def test_perform_create_validates_user_ownership(self):
        has_guard = (
            "user=self.request.user" in self.block
            or "filter(user=" in self.block
        )
        self.assertTrue(
            has_guard,
            "perform_create de InstagramConversationViewSet não filtra por user=request.user",
        )

    def test_perform_create_injects_account_into_save(self):
        self.assertIn(
            "serializer.save",
            self.block,
            "perform_create não chama serializer.save",
        )
        self.assertIn(
            "account=",
            self.block,
            "perform_create não injeta account em serializer.save(account=...)",
        )

    def test_perform_create_has_guard_against_missing_account(self):
        has_guard = (
            "ValidationError" in self.block
            or "get_object_or_404" in self.block
            or "Http404" in self.block
        )
        self.assertTrue(
            has_guard,
            "perform_create não rejeita request sem account",
        )


# ──────────────────────────────────────────────────────────────────────────────
# Testes funcionais DRF (import direto do módulo, sem DB/Docker)
# ──────────────────────────────────────────────────────────────────────────────

class InstagramSerializerFieldBehaviorTest(SimpleTestCase):
    """Testes funcionais DRF via importlib (sem DB/Docker)."""

    def _load_serializers(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            'instagram_api_serializers_direct',
            _SERIALIZERS_PATH,
        )
        mod = importlib.util.module_from_spec(spec)
        mod.__package__ = 'apps.instagram.api'
        spec.loader.exec_module(mod)
        return mod

    def test_media_serializer_account_is_read_only(self):
        mod = self._load_serializers()
        field = mod.InstagramMediaSerializer().fields['account']
        self.assertTrue(
            field.read_only,
            "InstagramMediaSerializer.account não é read_only — PATCH aceita account alheio (IDOR)",
        )

    def test_conversation_serializer_account_is_read_only(self):
        mod = self._load_serializers()
        field = mod.InstagramConversationSerializer().fields['account']
        self.assertTrue(
            field.read_only,
            "InstagramConversationSerializer.account não é read_only — PATCH aceita account alheio (IDOR)",
        )

    def test_media_account_absent_from_writable_fields(self):
        mod = self._load_serializers()
        s = mod.InstagramMediaSerializer()
        writable = {n for n, f in s.fields.items() if not getattr(f, 'read_only', False)}
        self.assertNotIn(
            'account',
            writable,
            "campo 'account' está em writable_fields de InstagramMediaSerializer — IDOR via PATCH",
        )

    def test_conversation_account_absent_from_writable_fields(self):
        mod = self._load_serializers()
        s = mod.InstagramConversationSerializer()
        writable = {n for n, f in s.fields.items() if not getattr(f, 'read_only', False)}
        self.assertNotIn(
            'account',
            writable,
            "campo 'account' está em writable_fields de InstagramConversationSerializer — IDOR via PATCH",
        )


# ──────────────────────────────────────────────────────────────────────────────
# Testes dos serializers de criação (schema drf-spectacular / COMPONENT_SPLIT_REQUEST)
# ──────────────────────────────────────────────────────────────────────────────

class InstagramCreateSerializersSchemaTest(SimpleTestCase):
    """InstagramMediaCreateSerializer e InstagramConversationCreateSerializer devem
    declarar 'account' como UUIDField — garante presença no request schema com
    COMPONENT_SPLIT_REQUEST=True."""

    def setUp(self):
        self.source = _read(_SERIALIZERS_PATH)

    def test_media_create_serializer_exists(self):
        self.assertIsNotNone(
            _extract_class(self.source, "InstagramMediaCreateSerializer"),
            "InstagramMediaCreateSerializer não encontrado em serializers.py",
        )

    def test_conversation_create_serializer_exists(self):
        self.assertIsNotNone(
            _extract_class(self.source, "InstagramConversationCreateSerializer"),
            "InstagramConversationCreateSerializer não encontrado em serializers.py",
        )

    def test_media_create_serializer_declares_account_uuid(self):
        block = _extract_class(self.source, "InstagramMediaCreateSerializer")
        self.assertIn("account", block)
        self.assertIn(
            "UUIDField",
            block,
            "InstagramMediaCreateSerializer.account não é UUIDField — schema incorreto",
        )

    def test_conversation_create_serializer_declares_account_uuid(self):
        block = _extract_class(self.source, "InstagramConversationCreateSerializer")
        self.assertIn("account", block)
        self.assertIn("UUIDField", block)

    def test_extend_schema_used_on_media_create(self):
        block = _extract_class(_read(_VIEWS_PATH), "InstagramMediaViewSet")
        self.assertIn(
            "extend_schema",
            block,
            "InstagramMediaViewSet.create não usa @extend_schema — account ausente do OpenAPI request schema",
        )
        self.assertIn("InstagramMediaCreateSerializer", block)

    def test_extend_schema_used_on_conversation_create(self):
        block = _extract_class(_read(_VIEWS_PATH), "InstagramConversationViewSet")
        self.assertIn("extend_schema", block)
        self.assertIn("InstagramConversationCreateSerializer", block)


# ──────────────────────────────────────────────────────────────────────────────
# Testes: UUID malformado → 404, não 500
# ──────────────────────────────────────────────────────────────────────────────

class InstagramPerformCreateUUIDValidationTest(SimpleTestCase):
    """perform_create deve capturar DjangoValidationError de UUID inválido e
    retornar 404, não propagar como 500."""

    def setUp(self):
        self.source = _read(_VIEWS_PATH)

    def test_media_perform_create_catches_django_validation_error(self):
        block = _extract_class(self.source, "InstagramMediaViewSet")
        self.assertIn(
            "DjangoValidationError",
            block,
            "InstagramMediaViewSet.perform_create não captura DjangoValidationError — "
            "UUID malformado em 'account' causa 500 em vez de 404",
        )

    def test_media_perform_create_raises_http404(self):
        block = _extract_class(self.source, "InstagramMediaViewSet")
        self.assertIn(
            "Http404",
            block,
            "perform_create não levanta Http404 para UUID inválido",
        )

    def test_conversation_perform_create_catches_django_validation_error(self):
        block = _extract_class(self.source, "InstagramConversationViewSet")
        self.assertIn(
            "DjangoValidationError",
            block,
            "InstagramConversationViewSet.perform_create não captura DjangoValidationError",
        )

    def test_conversation_perform_create_raises_http404(self):
        block = _extract_class(self.source, "InstagramConversationViewSet")
        self.assertIn("Http404", block)
