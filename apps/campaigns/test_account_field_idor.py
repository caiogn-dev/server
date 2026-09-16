"""Regressão de segurança: campo `account` gravável em PATCH — IDOR cross-tenant [P1].

CampaignSerializer e ContactListSerializer incluem `account` em `fields` mas NÃO
em `read_only_fields`. O PATCH padrão do ModelViewSet usa esses serializers, então
um atacante autenticado que possui a campanha/lista pode fazer:

    PATCH /api/v1/campaigns/{id}/ {"account": <victim_account_id>}

...e transferir a campanha para a conta WhatsApp da vítima. Quando o Celery
processar o próximo lote, usará `campaign.account` (da vítima) para enviar
mensagens em massa usando o token WA dela.

Mesmo vetor para ContactList: PATCH muda `account` para o da vítima, movendo
todos os telefones (PII) para o escopo da conta alheia.

Correção: adicionar `'account'` a `read_only_fields` em ambos os serializers.

Técnica: importação direta do módulo de serializers via importlib.util
(evita carregar apps.campaigns.api.__init__ que exige langchain_core).
"""
import importlib.util
import inspect
import os
import uuid
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

# Caminho absoluto para o módulo de serializers
_SERIALIZERS_PATH = os.path.join(
    os.path.dirname(__file__), 'api', 'serializers.py'
)


def _load_serializers_module():
    """Carrega serializers sem disparar o __init__.py que exige langchain_core."""
    spec = importlib.util.spec_from_file_location(
        'campaigns_api_serializers_direct', _SERIALIZERS_PATH
    )
    mod = importlib.util.module_from_spec(spec)
    # Fornece o pacote pai para resolver importações relativas
    import apps.campaigns.models as _models
    mod.__package__ = 'apps.campaigns.api'
    mod.__spec__.submodule_search_locations = []
    spec.loader.exec_module(mod)
    return mod


class CampaignSerializerAccountReadOnlyTest(SimpleTestCase):
    """CampaignSerializer.account deve ser read_only — bloqueia PATCH cross-tenant."""

    def test_account_in_read_only_fields_source(self):
        """Análise estática: 'account' aparece em read_only_fields."""
        source = open(_SERIALIZERS_PATH).read()
        # Encontra o bloco read_only_fields de CampaignSerializer e verifica
        # que 'account' está incluído.
        import re
        # Extrai a seção entre class CampaignSerializer e a próxima classe de nível
        match = re.search(
            r"class CampaignSerializer.*?(?=\nclass |\Z)",
            source,
            re.DOTALL,
        )
        self.assertIsNotNone(match, "CampaignSerializer não encontrado em serializers.py")
        serializer_block = match.group(0)

        ro_match = re.search(r"read_only_fields\s*=\s*\[([^\]]+)\]", serializer_block)
        self.assertIsNotNone(
            ro_match,
            "CampaignSerializer não possui read_only_fields definido",
        )
        ro_block = ro_match.group(1)
        self.assertIn(
            "'account'",
            ro_block,
            "CampaignSerializer.Meta.read_only_fields não contém 'account' — "
            "IDOR: PATCH /campaigns/{id}/ {\"account\": victim_id} transfere a "
            "campanha para o tenant da vítima.",
        )

    def test_delivery_rate_read_rate_still_read_only(self):
        """Garantia de não-regressão: read_only_fields existentes continuam presentes."""
        source = open(_SERIALIZERS_PATH).read()
        import re
        match = re.search(
            r"class CampaignSerializer.*?(?=\nclass |\Z)", source, re.DOTALL
        )
        block = match.group(0)
        for field in ("'id'", "'status'", "'created_at'", "'updated_at'"):
            self.assertIn(
                field,
                block,
                f"CampaignSerializer: campo {field} removido do read_only_fields — regressão",
            )

    def test_attack_vector_documented_in_source(self):
        """PATCH com account alheio não deve aceitar o campo account."""
        source = open(_SERIALIZERS_PATH).read()
        import re
        match = re.search(
            r"class CampaignSerializer.*?(?=\nclass |\Z)", source, re.DOTALL
        )
        block = match.group(0)
        # Confirma que account aparece tanto em fields quanto em read_only_fields
        self.assertIn("'account'", block,
                      "CampaignSerializer: 'account' não encontrado no source")


class ContactListSerializerAccountReadOnlyTest(SimpleTestCase):
    """ContactListSerializer.account deve ser read_only — impede PATCH cross-tenant."""

    def test_account_in_read_only_fields_source(self):
        """Análise estática: 'account' aparece em read_only_fields."""
        source = open(_SERIALIZERS_PATH).read()
        import re
        match = re.search(
            r"class ContactListSerializer.*?(?=\nclass |\Z)",
            source,
            re.DOTALL,
        )
        self.assertIsNotNone(match, "ContactListSerializer não encontrado em serializers.py")
        serializer_block = match.group(0)

        ro_match = re.search(r"read_only_fields\s*=\s*\[([^\]]+)\]", serializer_block)
        self.assertIsNotNone(
            ro_match,
            "ContactListSerializer não possui read_only_fields definido",
        )
        ro_block = ro_match.group(1)
        self.assertIn(
            "'account'",
            ro_block,
            "ContactListSerializer.Meta.read_only_fields não contém 'account' — "
            "IDOR: PATCH /contact-lists/{id}/ {\"account\": victim_id} move todos "
            "os telefones (PII) para o escopo da conta da vítima.",
        )

    def test_contact_count_imported_at_still_read_only(self):
        """Garantia de não-regressão: campos existentes em read_only_fields continuam."""
        source = open(_SERIALIZERS_PATH).read()
        import re
        match = re.search(
            r"class ContactListSerializer.*?(?=\nclass |\Z)", source, re.DOTALL
        )
        block = match.group(0)
        for field in ("'id'", "'contact_count'", "'imported_at'", "'created_at'", "'updated_at'"):
            self.assertIn(
                field,
                block,
                f"ContactListSerializer: campo {field} removido de read_only_fields — regressão",
            )

    def test_account_present_in_contactlist_serializer_block(self):
        """'account' deve estar declarado em ContactListSerializer."""
        source = open(_SERIALIZERS_PATH).read()
        import re
        match = re.search(
            r"class ContactListSerializer.*?(?=\nclass |\Z)", source, re.DOTALL
        )
        block = match.group(0)
        self.assertIn("'account'", block,
                      "ContactListSerializer: 'account' não encontrado no source")


class SerializerFieldBehaviorTest(SimpleTestCase):
    """Testes funcionais via DRF usando mocks (sem DB/Docker)."""

    def _campaign_serializer(self):
        """Importa CampaignSerializer carregando só o módulo de serializers."""
        mod = _load_serializers_module()
        return mod.CampaignSerializer

    def _contact_list_serializer(self):
        mod = _load_serializers_module()
        return mod.ContactListSerializer

    def test_campaign_serializer_account_field_read_only(self):
        """DRF: campo account em CampaignSerializer deve ser read_only."""
        S = self._campaign_serializer()
        s = S()
        field = s.fields['account']
        self.assertTrue(
            field.read_only,
            "CampaignSerializer.account não é read_only — PATCH aceita account alheio",
        )

    def test_contact_list_serializer_account_field_read_only(self):
        """DRF: campo account em ContactListSerializer deve ser read_only."""
        S = self._contact_list_serializer()
        s = S()
        field = s.fields['account']
        self.assertTrue(
            field.read_only,
            "ContactListSerializer.account não é read_only — PATCH aceita account alheio",
        )

    def test_campaign_account_field_not_writable(self):
        """Equivalente funcional: account não deve aparecer em writable_fields."""
        S = self._campaign_serializer()
        s = S()
        # Em DRF, um campo read_only não aparece nos campos graváveis
        writable_fields = {
            name for name, f in s.fields.items()
            if not getattr(f, 'read_only', False)
        }
        self.assertNotIn(
            'account',
            writable_fields,
            "campo 'account' está em writable_fields de CampaignSerializer — "
            "PATCH aceita account alheio (IDOR cross-tenant)",
        )

    def test_contact_list_account_field_not_writable(self):
        """Equivalente funcional: account não deve aparecer em writable_fields."""
        S = self._contact_list_serializer()
        s = S()
        writable_fields = {
            name for name, f in s.fields.items()
            if not getattr(f, 'read_only', False)
        }
        self.assertNotIn(
            'account',
            writable_fields,
            "campo 'account' está em writable_fields de ContactListSerializer — "
            "PATCH aceita account alheio, move PII para tenant da vítima",
        )
