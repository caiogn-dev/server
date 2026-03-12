# Models and Serializers Audit and Refactor Plan

Date: 2026-02-27
Scope: `server/apps/**/models*.py`, `server/apps/**/serializers*.py`, and frontend contract surface in `pastita-dash/src/**`
Author: Codex

## 1. Audit scope and method

This audit reviewed the full Django model and serializer surface of the backend.

Quantitative inventory:

- 26 model files reviewed
- 14 serializer files reviewed
- 110 persistent model classes detected with declared fields
- 171 serializer classes detected

Objective findings were extracted from the source by enumerating:

- model classes and field declarations
- serializer classes and model bindings
- repeated field names across domains
- near-duplicate model pairs
- duplicate serializer surfaces for the same logical entity
- frontend references to backend concepts that are structurally redundant

## 2. Executive summary

The project already has a strong business aggregate in `Store`, but the rest of the architecture does not consistently treat it as the system of record.

The main structural problems are:

1. `Store` and `CompanyProfile` overlap semantically.
2. Messenger exists twice, in `apps.messaging` and `apps.messenger`.
3. Handover exists twice, in `apps.conversations` and `apps.handover`.
4. Flow models exist twice, in `apps.automation.models` and `apps.automation.models.flow`.
5. Several automation records point to `CompanyProfile` when they should point to `Store`.
6. Base abstractions already exist in `apps.core.models`, but are not actually used by the domains that duplicate those same shapes.
7. The frontend still exposes the automation domain as `CompanyProfile` and `company_id`, even though the real business ownership is store-centric.

The recommended target architecture is:

- `Store` remains the canonical business aggregate.
- `CompanyProfile` is replaced by a store-owned automation profile with no duplicated business fields.
- `apps.handover` becomes the only handover state authority.
- `apps.messenger` becomes the only Messenger app; `apps.messaging` is removed after data migration.
- flow models are kept in one place only.
- automation operational records become `store`-owned.
- serializers and frontend contracts switch from `company_id` to `store_id`.

## 3. App-by-app findings

| App | Role | Structural assessment |
| --- | --- | --- |
| `stores` | Canonical business domain | Best-structured domain. Already owns identity, contact, address, location, hours, delivery, commerce. |
| `automation` | Automation config and operational records | Mixed responsibilities. Holds valid automation entities, but `CompanyProfile` leaks store data and anchors too many downstream records. |
| `whatsapp` | WhatsApp channel | Valid channel domain, but business/automation toggles still live here and overlap with automation profile responsibilities. |
| `conversations` | Conversation lifecycle | Valid conversation aggregate, but contains a duplicate handover model that should not exist. |
| `handover` | Bot/human support transfer | Correct canonical place for handover; should absorb all ownership state. |
| `agents` | LLM agent configs and sessions | Generally coherent. Ownership should be attached through store/channel automation policy, not duplicated in multiple places. |
| `messaging` | Old Messenger integration | Legacy duplicate of Messenger domain. Contains profile/extension/webhook models not present in `apps.messenger`. |
| `messenger` | Newer Messenger integration | Closer to the desired shape, but incomplete relative to `apps.messaging`. Should become canonical and absorb missing features. |
| `marketing` | Email marketing | Mostly coherent and already store-centric. Good candidate for shared abstract bases. |
| `campaigns` | WhatsApp campaigns | Valid domain, but overlaps structurally with scheduled messaging and broadcast patterns. |
| `instagram` | Instagram integration | Good candidate for channel base abstractions. |
| `webhooks` | External event intake/outbox | Valid domain, but overlaps with per-channel webhook event logs. |
| `notifications` | Internal app notifications | Fine. |
| `audit` | Audit/export logs | Fine. |
| `users` | Unified user/customer view | Fine, but overlaps conceptually with `StoreCustomer` and `Subscriber`. |
| `core` | Base abstractions | Has useful abstractions that are currently underused. |

## 4. Redundancy and duplication matrix

### 4.1 Repeated field names across the model graph

Top repeated field names found across the audited models:

- `created_at`: 60 occurrences
- `id`: 55
- `status`: 45
- `updated_at`: 44
- `name`: 38
- `account`: 26
- `is_active`: 26
- `store`: 23
- `error_message`: 23
- `description`: 21
- `conversation`: 15
- `metadata`: 15
- `sent_at`: 13
- `content`: 11
- `user`: 11
- `created_by`: 10
- `message_type`: 9
- `scheduled_at`: 9
- `event_type`: 8
- `media_url`: 8
- `payload`: 8
- `phone_number`: 8

This is expected in part, but many of these repeated shapes are not abstracted even though the project already has `BaseModel`, `TimestampedModel`, `BaseMessageModel`, and `TenantModel`.

### 4.2 Store vs CompanyProfile

`Store` is already the business source of truth. `CompanyProfile` still persists business-facing fields and proxies them back to `Store` through properties.

Observed overlap:

- `Store` owns: `name`, `description`, `email`, `phone`, `whatsapp_number`, `address`, `city`, `state`, `zip_code`, `latitude`, `longitude`, `operating_hours`, branding, currency, taxes, delivery settings.
- `CompanyProfile` still persists: `_company_name`, `_description`, `_business_type`, `_business_hours`, `website_url`, `menu_url`, `order_url` and automation flags.

Technical problem:

- the same business identity is represented twice
- the profile file defines duplicate properties for `company_name`, `description`, and `business_type`
- the profile acts as a shadow aggregate instead of a configuration extension
- many services still filter or reference `company_id`

Conclusion:

- `CompanyProfile` should not exist as an independent business entity
- it should be replaced by a pure automation/configuration extension owned by `Store`

### 4.3 Duplicate handover model

Duplicate pair:

- `server/apps/conversations/models.py` -> `ConversationHandover`
- `server/apps/handover/models.py` -> `ConversationHandover`

Shared field core:

- `conversation`
- `status`

Why this is wrong:

- state can diverge between two tables
- serializers and services need fallback logic
- the UI cannot trust one source for ownership bot/human state

Decision:

- keep only `apps.handover.ConversationHandover`
- remove the duplicate from `apps.conversations`
- keep `Conversation.mode` as derived state or remove it after application cutover

### 4.4 Duplicate flow models

Exact duplicates detected:

- `AgentFlow`
- `FlowSession`
- `FlowExecutionLog`

Locations:

- `server/apps/automation/models.py`
- `server/apps/automation/models/flow.py`

Decision:

- keep only one canonical module, preferably `server/apps/automation/models/flow.py`
- export it through `server/apps/automation/models/__init__.py`
- remove duplicate declarations from `server/apps/automation/models.py`

### 4.5 Duplicate Messenger domain

Duplicate domain roots:

- `server/apps/messaging/*`
- `server/apps/messenger/*`

Observed overlaps:

- account models duplicated
- conversation models duplicated
- message models duplicated
- broadcast models duplicated
- sponsored message models duplicated
- serializers duplicated
- viewsets duplicated

Current split:

- `apps.messaging` has richer Facebook page profile/extension/webhook structures
- `apps.messenger` has better alignment with support automation and `BaseModel`

Decision:

- keep `apps.messenger` as the canonical Messenger domain
- migrate missing models from `apps.messaging` into `apps.messenger`
- migrate data from old tables to new tables
- remove `apps.messaging` from installed apps after cutover

### 4.6 Serializer duplication

Duplicate serializer surfaces were found for the same logical entity in two apps:

- `MessengerAccountSerializer`
- `MessengerConversationSerializer`
- `MessengerMessageSerializer`
- `MessengerBroadcastSerializer`
- `MessengerSponsoredMessageSerializer`

This causes:

- duplicated API contracts
- inconsistent field sets
- frontend ambiguity about which app is authoritative

### 4.7 Unused base abstractions

Defined but not materially used by the audited domains:

- `BaseMessageModel`
- `TimestampedModel`
- `TenantModel`

This is a design smell because the codebase already knows the repeated shapes, but keeps re-implementing them manually.

## 5. Exact refactor decisions

### 5.1 Canonical ownership rules

| Concern | Canonical owner |
| --- | --- |
| business identity | `stores.Store` |
| store contact/address/location/hours | `stores.Store` |
| automation policy | `automation.StoreAutomationProfile` |
| channel account config | channel app account model, always store-owned |
| bot/human ownership state | `handover.ConversationHandover` |
| automated templates/rules | `automation.AutomationRule` |
| operational automation session | `automation.AutomationSession` |
| automation execution/audit | `automation.AutomationEventLog` |
| WhatsApp messages | `whatsapp.Message` |
| Messenger messages | `messenger.MessengerMessage` |
| report ownership | `Store` |

### 5.2 Models to remove or replace

Remove or phase out completely:

- `automation.CompanyProfile` -> replace with `automation.StoreAutomationProfile`
- `conversations.ConversationHandover` -> remove
- `apps.messaging.*` -> merge into `apps.messenger`
- duplicate flow declarations in `automation.models.py` -> remove

### 5.3 Models to keep but re-anchor

Keep with foreign keys changed from `company` to `store`:

- `AutoMessage` -> `AutomationRule`
- `CustomerSession` -> `AutomationSession`
- `AutomationLog` -> `AutomationEventLog`
- `ReportSchedule` -> add `store`, remove `company`
- `GeneratedReport` -> remains via schedule

### 5.4 New abstract hierarchy

Recommended abstract bases:

- `StoreBoundModel`
- `ChannelAccountBase`
- `ChannelConversationBase`
- `ChannelMessageBase`
- `ProviderEventLogBase`

These reduce repeated ownership, status, delivery and payload structures.

## 6. Proposed target model architecture

### 6.1 Proposed backend model code

```python
# server/apps/core/domain_models.py
from django.conf import settings
from django.db import models
from apps.core.models import BaseModel, BaseMessageModel


class StoreBoundModel(BaseModel):
    """Any domain record owned by a Store."""

    store = models.ForeignKey(
        'stores.Store',
        on_delete=models.CASCADE,
        related_name='%(class)s_records',
    )

    class Meta:
        abstract = True


class ChannelAccountBase(StoreBoundModel):
    """Shared automation-capable channel account fields."""

    class AccountStatus(models.TextChoices):
        ACTIVE = 'active', 'Active'
        INACTIVE = 'inactive', 'Inactive'
        PENDING = 'pending', 'Pending'
        ERROR = 'error', 'Error'

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='%(class)s_owned',
    )
    name = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=AccountStatus.choices, default=AccountStatus.PENDING)
    default_agent = models.ForeignKey(
        'agents.Agent',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='%(class)s_default_for',
    )
    auto_response_enabled = models.BooleanField(default=True)
    human_handoff_enabled = models.BooleanField(default=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        abstract = True


class ChannelConversationBase(BaseModel):
    """Shared participant/support fields for channel conversations."""

    class ConversationStatus(models.TextChoices):
        OPEN = 'open', 'Open'
        CLOSED = 'closed', 'Closed'
        ARCHIVED = 'archived', 'Archived'

    participant_external_id = models.CharField(max_length=120, db_index=True)
    participant_name = models.CharField(max_length=255, blank=True)
    participant_avatar_url = models.URLField(blank=True)
    status = models.CharField(max_length=20, choices=ConversationStatus.choices, default=ConversationStatus.OPEN)
    unread_count = models.PositiveIntegerField(default=0)
    last_message_preview = models.TextField(blank=True)
    last_message_at = models.DateTimeField(null=True, blank=True)
    tags = models.JSONField(default=list, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        abstract = True


class ChannelMessageBase(BaseMessageModel):
    """Shared normalized channel message fields."""

    sender_external_id = models.CharField(max_length=120, blank=True)
    sender_name = models.CharField(max_length=255, blank=True)
    payload = models.JSONField(default=dict, blank=True)
    attachments = models.JSONField(default=list, blank=True)

    class Meta:
        abstract = True


class ProviderEventLogBase(StoreBoundModel):
    """Shared inbound provider event logging."""

    provider = models.CharField(max_length=50)
    event_type = models.CharField(max_length=80)
    payload = models.JSONField()
    headers = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=30, default='pending')
    processed_at = models.DateTimeField(null=True, blank=True)
    retry_count = models.PositiveIntegerField(default=0)
    error_message = models.TextField(blank=True)

    class Meta:
        abstract = True
```

```python
# server/apps/automation/models/canonical.py
from django.conf import settings
from django.db import models
from apps.core.models import BaseModel
from apps.core.domain_models import StoreBoundModel


class StoreAutomationProfile(StoreBoundModel):
    """Pure automation config. No business identity duplication."""

    class BusinessType(models.TextChoices):
        RESTAURANT = 'restaurant', 'Restaurant'
        ECOMMERCE = 'ecommerce', 'E-commerce'
        SERVICES = 'services', 'Services'
        RETAIL = 'retail', 'Retail'
        HEALTHCARE = 'healthcare', 'Healthcare'
        EDUCATION = 'education', 'Education'
        OTHER = 'other', 'Other'

    business_type = models.CharField(max_length=20, choices=BusinessType.choices, default=BusinessType.OTHER)
    website_url = models.URLField(blank=True)
    menu_url = models.URLField(blank=True)
    order_url = models.URLField(blank=True)
    external_api_key = models.CharField(max_length=255, blank=True)
    webhook_secret = models.CharField(max_length=255, blank=True)

    auto_reply_enabled = models.BooleanField(default=True)
    welcome_message_enabled = models.BooleanField(default=True)
    menu_auto_send = models.BooleanField(default=True)
    abandoned_cart_notification = models.BooleanField(default=True)
    abandoned_cart_delay_minutes = models.PositiveIntegerField(default=30)
    pix_notification_enabled = models.BooleanField(default=True)
    payment_confirmation_enabled = models.BooleanField(default=True)
    order_status_notification_enabled = models.BooleanField(default=True)
    delivery_notification_enabled = models.BooleanField(default=True)
    use_ai_agent = models.BooleanField(default=False)
    default_agent = models.ForeignKey(
        'agents.Agent',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='automation_profiles',
    )
    settings = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = 'store_automation_profiles'
        constraints = [
            models.UniqueConstraint(fields=['store'], name='uq_store_automation_profile_store'),
        ]

    @property
    def company_name(self):
        return self.store.name

    @property
    def description(self):
        return self.store.description

    @property
    def phone_number(self):
        return self.store.whatsapp_number or self.store.phone

    @property
    def email(self):
        return self.store.email

    @property
    def address(self):
        return self.store.address

    @property
    def city(self):
        return self.store.city

    @property
    def state(self):
        return self.store.state

    @property
    def business_hours(self):
        return self.store.operating_hours or {}


class AutomationRule(StoreBoundModel):
    """Normalized automated response and notification rules."""

    class Channel(models.TextChoices):
        WHATSAPP = 'whatsapp', 'WhatsApp'
        MESSENGER = 'messenger', 'Messenger'
        INSTAGRAM = 'instagram', 'Instagram'
        EMAIL = 'email', 'Email'

    class EventType(models.TextChoices):
        WELCOME = 'welcome', 'Welcome'
        MENU = 'menu', 'Menu'
        BUSINESS_HOURS = 'business_hours', 'Business Hours'
        OUT_OF_HOURS = 'out_of_hours', 'Out of Hours'
        CART_ABANDONED = 'cart_abandoned', 'Cart Abandoned'
        PIX_GENERATED = 'pix_generated', 'Pix Generated'
        PAYMENT_CONFIRMED = 'payment_confirmed', 'Payment Confirmed'
        ORDER_RECEIVED = 'order_received', 'Order Received'
        ORDER_CONFIRMED = 'order_confirmed', 'Order Confirmed'
        ORDER_PREPARING = 'order_preparing', 'Order Preparing'
        ORDER_DELIVERED = 'order_delivered', 'Order Delivered'
        HUMAN_HANDOFF = 'human_handoff', 'Human Handoff'
        CUSTOM = 'custom', 'Custom'

    channel = models.CharField(max_length=20, choices=Channel.choices, default=Channel.WHATSAPP)
    event_type = models.CharField(max_length=40, choices=EventType.choices)
    name = models.CharField(max_length=255)
    payload = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)
    delay_seconds = models.PositiveIntegerField(default=0)
    priority = models.PositiveIntegerField(default=100)
    conditions = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = 'automation_rules'
        indexes = [
            models.Index(fields=['store', 'channel', 'event_type', 'is_active']),
            models.Index(fields=['store', 'priority']),
        ]


class AutomationSession(StoreBoundModel):
    """Automation execution context tied to a store, not to CompanyProfile."""

    class SessionStatus(models.TextChoices):
        ACTIVE = 'active', 'Active'
        CART_CREATED = 'cart_created', 'Cart Created'
        CART_ABANDONED = 'cart_abandoned', 'Cart Abandoned'
        PAYMENT_PENDING = 'payment_pending', 'Payment Pending'
        PAYMENT_CONFIRMED = 'payment_confirmed', 'Payment Confirmed'
        ORDER_CREATED = 'order_created', 'Order Created'
        COMPLETED = 'completed', 'Completed'
        EXPIRED = 'expired', 'Expired'

    conversation = models.ForeignKey(
        'conversations.Conversation',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='automation_sessions',
    )
    order = models.ForeignKey(
        'stores.StoreOrder',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='automation_sessions',
    )
    phone_number = models.CharField(max_length=20, db_index=True)
    customer_name = models.CharField(max_length=255, blank=True)
    customer_email = models.EmailField(blank=True)
    external_customer_id = models.CharField(max_length=120, blank=True)
    status = models.CharField(max_length=30, choices=SessionStatus.choices, default=SessionStatus.ACTIVE)
    cart_snapshot = models.JSONField(default=dict, blank=True)
    payment_snapshot = models.JSONField(default=dict, blank=True)
    notifications_sent = models.JSONField(default=list, blank=True)
    last_activity_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'automation_sessions'
        indexes = [
            models.Index(fields=['store', 'phone_number', 'status']),
            models.Index(fields=['status', 'expires_at']),
        ]


class AutomationEventLog(StoreBoundModel):
    """Automation audit trail owned by Store."""

    session = models.ForeignKey(
        AutomationSession,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='logs',
    )
    conversation = models.ForeignKey(
        'conversations.Conversation',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='automation_logs',
    )
    message = models.ForeignKey(
        'whatsapp.Message',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='automation_logs',
    )
    action_type = models.CharField(max_length=40)
    event_type = models.CharField(max_length=40, blank=True)
    description = models.TextField(blank=True)
    phone_number = models.CharField(max_length=20, blank=True)
    request_payload = models.JSONField(default=dict, blank=True)
    response_payload = models.JSONField(default=dict, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    is_error = models.BooleanField(default=False)
    error_message = models.TextField(blank=True)

    class Meta:
        db_table = 'automation_event_logs'
        indexes = [
            models.Index(fields=['store', 'action_type', 'created_at']),
            models.Index(fields=['store', 'is_error', 'created_at']),
        ]
```

```python
# server/apps/handover/models/canonical.py
from django.conf import settings
from django.db import models
from apps.core.models import BaseModel


class ConversationHandover(BaseModel):
    """Single canonical ownership state for a conversation."""

    class Status(models.TextChoices):
        BOT = 'bot', 'Bot'
        HUMAN = 'human', 'Human'
        PENDING = 'pending', 'Pending'

    conversation = models.OneToOneField(
        'conversations.Conversation',
        on_delete=models.CASCADE,
        related_name='handover',
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.BOT)
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='conversation_handovers',
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='handover_requests_created',
    )
    last_transfer_at = models.DateTimeField(null=True, blank=True)
    last_transfer_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='handover_transfers_made',
    )
    transfer_reason = models.TextField(blank=True)

    class Meta:
        db_table = 'conversation_handovers'
```

```python
# server/apps/messenger/models/canonical.py
from django.db import models
from apps.core.domain_models import ChannelAccountBase, ChannelConversationBase, ChannelMessageBase, ProviderEventLogBase


class MessengerAccount(ChannelAccountBase):
    page_id = models.CharField(max_length=255, unique=True, db_index=True)
    page_name = models.CharField(max_length=255)
    page_access_token = models.TextField()
    app_id = models.CharField(max_length=255, blank=True)
    app_secret = models.CharField(max_length=255, blank=True)
    webhook_verified = models.BooleanField(default=False)
    category = models.CharField(max_length=255, blank=True)
    followers_count = models.IntegerField(default=0)
    last_sync_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'messenger_accounts'


class MessengerProfile(models.Model):
    account = models.OneToOneField(MessengerAccount, on_delete=models.CASCADE, related_name='profile')
    greeting_text = models.TextField(blank=True)
    get_started_payload = models.CharField(max_length=1000, blank=True, default='GET_STARTED')
    persistent_menu = models.JSONField(default=dict, blank=True)
    ice_breakers = models.JSONField(default=list, blank=True)
    whitelisted_domains = models.JSONField(default=list, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'messenger_profiles'


class MessengerConversation(ChannelConversationBase):
    account = models.ForeignKey(MessengerAccount, on_delete=models.CASCADE, related_name='conversations')

    class Meta:
        db_table = 'messenger_conversations'
        constraints = [
            models.UniqueConstraint(fields=['account', 'participant_external_id'], name='uq_messenger_account_participant'),
        ]


class MessengerMessage(ChannelMessageBase):
    account = models.ForeignKey(MessengerAccount, on_delete=models.CASCADE, related_name='messages')
    conversation = models.ForeignKey(MessengerConversation, on_delete=models.CASCADE, related_name='messages')
    external_message_id = models.CharField(max_length=255, db_index=True, blank=True)

    class Meta:
        db_table = 'messenger_messages'
        indexes = [
            models.Index(fields=['account', 'status', 'created_at']),
            models.Index(fields=['conversation', 'created_at']),
        ]


class MessengerWebhookLog(ProviderEventLogBase):
    account = models.ForeignKey(MessengerAccount, on_delete=models.CASCADE, related_name='webhook_logs')

    class Meta:
        db_table = 'messenger_webhook_logs'
```

### 6.2 Proposed serializer code

```python
# server/apps/automation/api/serializers/canonical.py
from rest_framework import serializers
from apps.automation.models.canonical import (
    StoreAutomationProfile,
    AutomationRule,
    AutomationSession,
    AutomationEventLog,
)
from apps.handover.models.canonical import ConversationHandover


class StoreAutomationProfileSerializer(serializers.ModelSerializer):
    store_name = serializers.CharField(source='store.name', read_only=True)
    store_slug = serializers.CharField(source='store.slug', read_only=True)
    phone_number = serializers.CharField(read_only=True)
    company_name = serializers.CharField(read_only=True)
    description = serializers.CharField(read_only=True)
    email = serializers.CharField(read_only=True)
    address = serializers.CharField(read_only=True)
    city = serializers.CharField(read_only=True)
    state = serializers.CharField(read_only=True)
    business_hours = serializers.JSONField(read_only=True)
    default_agent_name = serializers.CharField(source='default_agent.name', read_only=True)

    class Meta:
        model = StoreAutomationProfile
        fields = [
            'id',
            'store',
            'store_name',
            'store_slug',
            'company_name',
            'description',
            'phone_number',
            'email',
            'address',
            'city',
            'state',
            'business_hours',
            'business_type',
            'website_url',
            'menu_url',
            'order_url',
            'external_api_key',
            'webhook_secret',
            'auto_reply_enabled',
            'welcome_message_enabled',
            'menu_auto_send',
            'abandoned_cart_notification',
            'abandoned_cart_delay_minutes',
            'pix_notification_enabled',
            'payment_confirmation_enabled',
            'order_status_notification_enabled',
            'delivery_notification_enabled',
            'use_ai_agent',
            'default_agent',
            'default_agent_name',
            'settings',
            'created_at',
            'updated_at',
            'is_active',
        ]
        read_only_fields = [
            'id',
            'store_name',
            'store_slug',
            'company_name',
            'description',
            'phone_number',
            'email',
            'address',
            'city',
            'state',
            'business_hours',
            'external_api_key',
            'webhook_secret',
            'created_at',
            'updated_at',
        ]


class StoreAutomationProfileWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = StoreAutomationProfile
        fields = [
            'store',
            'business_type',
            'website_url',
            'menu_url',
            'order_url',
            'auto_reply_enabled',
            'welcome_message_enabled',
            'menu_auto_send',
            'abandoned_cart_notification',
            'abandoned_cart_delay_minutes',
            'pix_notification_enabled',
            'payment_confirmation_enabled',
            'order_status_notification_enabled',
            'delivery_notification_enabled',
            'use_ai_agent',
            'default_agent',
            'settings',
        ]


class AutomationRuleSerializer(serializers.ModelSerializer):
    store_name = serializers.CharField(source='store.name', read_only=True)

    class Meta:
        model = AutomationRule
        fields = [
            'id',
            'store',
            'store_name',
            'channel',
            'event_type',
            'name',
            'payload',
            'is_active',
            'delay_seconds',
            'priority',
            'conditions',
            'created_at',
            'updated_at',
            'is_active',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class AutomationSessionSerializer(serializers.ModelSerializer):
    store_name = serializers.CharField(source='store.name', read_only=True)
    conversation_phone_number = serializers.CharField(source='conversation.phone_number', read_only=True)
    order_number = serializers.CharField(source='order.order_number', read_only=True)

    class Meta:
        model = AutomationSession
        fields = [
            'id',
            'store',
            'store_name',
            'conversation',
            'conversation_phone_number',
            'order',
            'order_number',
            'phone_number',
            'customer_name',
            'customer_email',
            'external_customer_id',
            'status',
            'cart_snapshot',
            'payment_snapshot',
            'notifications_sent',
            'last_activity_at',
            'expires_at',
            'created_at',
            'updated_at',
            'is_active',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class AutomationEventLogSerializer(serializers.ModelSerializer):
    store_name = serializers.CharField(source='store.name', read_only=True)
    session_phone_number = serializers.CharField(source='session.phone_number', read_only=True)

    class Meta:
        model = AutomationEventLog
        fields = [
            'id',
            'store',
            'store_name',
            'session',
            'session_phone_number',
            'conversation',
            'message',
            'action_type',
            'event_type',
            'description',
            'phone_number',
            'request_payload',
            'response_payload',
            'metadata',
            'is_error',
            'error_message',
            'created_at',
        ]
        read_only_fields = ['id', 'created_at']


class ConversationHandoverSerializer(serializers.ModelSerializer):
    assigned_to_name = serializers.CharField(source='assigned_to.get_full_name', read_only=True)
    last_transfer_by_name = serializers.CharField(source='last_transfer_by.get_full_name', read_only=True)

    class Meta:
        model = ConversationHandover
        fields = [
            'id',
            'conversation',
            'status',
            'assigned_to',
            'assigned_to_name',
            'requested_by',
            'last_transfer_at',
            'last_transfer_by',
            'last_transfer_by_name',
            'transfer_reason',
            'created_at',
            'updated_at',
            'is_active',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
```

## 7. Data migration plan

### 7.1 Migration principles

- migrate forward only
- no dual-write period longer than one release train
- no new feature work on old models after migration branch starts
- application cutover happens only after parity validation

### 7.2 Data migration script proposal

```python
# server/apps/core/management/commands/migrate_to_store_canonical_architecture.py
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.automation.models import CompanyProfile, AutoMessage, CustomerSession, AutomationLog, ReportSchedule
from apps.conversations.models import ConversationHandover as LegacyConversationHandover
from apps.handover.models import ConversationHandover, HandoverStatus
from apps.messaging.models import (
    MessengerAccount as LegacyMessengerAccount,
    MessengerConversation as LegacyMessengerConversation,
    MessengerMessage as LegacyMessengerMessage,
    MessengerBroadcast as LegacyMessengerBroadcast,
    MessengerSponsoredMessage as LegacyMessengerSponsoredMessage,
)
from apps.messenger.models import (
    MessengerAccount,
    MessengerConversation,
    MessengerMessage,
    MessengerBroadcast,
    MessengerSponsoredMessage,
)
from apps.stores.models import Store

# Proposed canonical models
from apps.automation.models.canonical import (
    StoreAutomationProfile,
    AutomationRule,
    AutomationSession,
    AutomationEventLog,
)


class Command(BaseCommand):
    help = 'Migrate legacy company-centric and duplicated channel data to canonical store-centric architecture'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true')
        parser.add_argument('--skip-messenger', action='store_true')
        parser.add_argument('--skip-handover', action='store_true')

    def handle(self, *args, **options):
        self.dry_run = options['dry_run']
        self.skip_messenger = options['skip_messenger']
        self.skip_handover = options['skip_handover']

        with transaction.atomic():
            self.migrate_automation_profiles()
            self.migrate_auto_messages()
            self.migrate_customer_sessions()
            self.migrate_automation_logs()
            self.migrate_report_schedules()
            if not self.skip_handover:
                self.migrate_handover_state()
            if not self.skip_messenger:
                self.migrate_messenger_domain()

            if self.dry_run:
                raise RuntimeError('Dry-run completed. Rolling back transaction on purpose.')

    def migrate_automation_profiles(self):
        for profile in CompanyProfile.objects.select_related('store').all():
            store = profile.store
            if not store:
                continue

            target, _ = StoreAutomationProfile.objects.update_or_create(
                store=store,
                defaults={
                    'business_type': profile.business_type or StoreAutomationProfile.BusinessType.OTHER,
                    'website_url': profile.website_url,
                    'menu_url': profile.menu_url,
                    'order_url': profile.order_url,
                    'external_api_key': profile.external_api_key,
                    'webhook_secret': profile.webhook_secret,
                    'auto_reply_enabled': profile.auto_reply_enabled,
                    'welcome_message_enabled': profile.welcome_message_enabled,
                    'menu_auto_send': profile.menu_auto_send,
                    'abandoned_cart_notification': profile.abandoned_cart_notification,
                    'abandoned_cart_delay_minutes': profile.abandoned_cart_delay_minutes,
                    'pix_notification_enabled': profile.pix_notification_enabled,
                    'payment_confirmation_enabled': profile.payment_confirmation_enabled,
                    'order_status_notification_enabled': profile.order_status_notification_enabled,
                    'delivery_notification_enabled': profile.delivery_notification_enabled,
                    'use_ai_agent': profile.use_ai_agent,
                    'default_agent': profile.default_agent,
                    'settings': profile.settings,
                    'is_active': profile.is_active,
                },
            )
            self.stdout.write(f'profile -> automation_profile: {profile.id} -> {target.id}')

    def migrate_auto_messages(self):
        for message in AutoMessage.objects.select_related('company', 'company__store').all():
            if not message.company_id or not message.company.store_id:
                continue
            AutomationRule.objects.update_or_create(
                store=message.company.store,
                channel='whatsapp',
                event_type=message.event_type,
                name=message.name,
                defaults={
                    'payload': {
                        'text': message.message_text,
                        'media_url': message.media_url,
                        'media_type': message.media_type,
                        'buttons': message.buttons,
                    },
                    'is_active': message.is_active,
                    'delay_seconds': message.delay_seconds,
                    'priority': message.priority,
                    'conditions': message.conditions,
                    'is_active': message.is_active,
                },
            )

    def migrate_customer_sessions(self):
        for session in CustomerSession.objects.select_related('company', 'company__store', 'conversation', 'order').all():
            if not session.company_id or not session.company.store_id:
                continue
            AutomationSession.objects.update_or_create(
                store=session.company.store,
                conversation=session.conversation,
                phone_number=session.phone_number,
                defaults={
                    'order': session.order,
                    'customer_name': session.customer_name,
                    'customer_email': session.customer_email,
                    'external_customer_id': session.external_customer_id,
                    'status': session.status,
                    'cart_snapshot': {
                        'cart_data': session.cart_data,
                        'cart_total': str(session.cart_total),
                        'cart_items_count': session.cart_items_count,
                        'cart_created_at': session.cart_created_at.isoformat() if session.cart_created_at else None,
                        'cart_updated_at': session.cart_updated_at.isoformat() if session.cart_updated_at else None,
                    },
                    'payment_snapshot': {
                        'pix_code': session.pix_code,
                        'pix_qr_code': session.pix_qr_code,
                        'pix_expires_at': session.pix_expires_at.isoformat() if session.pix_expires_at else None,
                        'payment_id': session.payment_id,
                        'external_order_id': session.external_order_id,
                    },
                    'notifications_sent': session.notifications_sent,
                    'last_activity_at': session.last_activity_at,
                    'expires_at': session.expires_at,
                    'is_active': session.is_active,
                },
            )

    def migrate_automation_logs(self):
        for log in AutomationLog.objects.select_related('company', 'company__store', 'session').all():
            if not log.company_id or not log.company.store_id:
                continue
            target_session = None
            if log.session_id:
                target_session = AutomationSession.objects.filter(
                    store=log.company.store,
                    phone_number=log.phone_number,
                ).order_by('-created_at').first()
            AutomationEventLog.objects.create(
                store=log.company.store,
                session=target_session,
                action_type=log.action_type,
                event_type=log.event_type,
                description=log.description,
                phone_number=log.phone_number,
                request_payload=log.request_data,
                response_payload=log.response_data,
                is_error=log.is_error,
                error_message=log.error_message,
                created_at=log.created_at,
                updated_at=log.created_at,
                is_active=True,
            )

    def migrate_report_schedules(self):
        for schedule in ReportSchedule.objects.select_related('company', 'company__store').all():
            if schedule.company_id and schedule.company.store_id and not getattr(schedule, 'store_id', None):
                schedule.store = schedule.company.store
                schedule.save(update_fields=['store'])

    def migrate_handover_state(self):
        for legacy in LegacyConversationHandover.objects.select_related('conversation').all():
            status_map = {
                'active': HandoverStatus.HUMAN if legacy.current_owner == 'human' else HandoverStatus.BOT,
                'pending': HandoverStatus.PENDING,
                'completed': HandoverStatus.BOT,
                'expired': HandoverStatus.BOT,
            }
            canonical, _ = ConversationHandover.objects.update_or_create(
                conversation=legacy.conversation,
                defaults={
                    'status': status_map.get(legacy.status, HandoverStatus.BOT),
                    'transfer_reason': legacy.reason or '',
                    'last_transfer_at': legacy.ended_at or legacy.started_at,
                },
            )
            self.stdout.write(f'handover -> canonical: {legacy.id} -> {canonical.id}')

    def migrate_messenger_domain(self):
        account_map = {}

        for legacy in LegacyMessengerAccount.objects.all():
            store = Store.objects.filter(owner=legacy.user).order_by('created_at').first()
            if not store:
                continue

            target, _ = MessengerAccount.objects.update_or_create(
                page_id=legacy.page_id,
                defaults={
                    'store': store,
                    'owner': legacy.user,
                    'name': legacy.page_name,
                    'page_name': legacy.page_name,
                    'page_access_token': legacy.page_access_token,
                    'app_id': legacy.app_id or '',
                    'app_secret': legacy.app_secret or '',
                    'status': 'active' if legacy.is_active else 'inactive',
                    'webhook_verified': legacy.webhook_verified,
                    'category': legacy.category,
                    'followers_count': legacy.followers_count,
                    'last_sync_at': legacy.last_sync_at,
                    'is_active': legacy.is_active,
                },
            )
            account_map[str(legacy.id)] = target

        for legacy in LegacyMessengerConversation.objects.select_related('account').all():
            target_account = account_map.get(str(legacy.account_id))
            if not target_account:
                continue
            target_conversation, _ = MessengerConversation.objects.update_or_create(
                account=target_account,
                participant_external_id=legacy.psid,
                defaults={
                    'participant_name': legacy.participant_name,
                    'participant_avatar_url': legacy.participant_profile_pic or '',
                    'status': 'open' if legacy.is_active else 'archived',
                    'unread_count': legacy.unread_count,
                    'last_message_at': legacy.last_message_at,
                    'is_active': legacy.is_active,
                },
            )

            for legacy_message in legacy.messages.all():
                MessengerMessage.objects.update_or_create(
                    conversation=target_conversation,
                    external_message_id=legacy_message.messenger_message_id or '',
                    defaults={
                        'account': target_account,
                        'direction': 'outbound' if legacy_message.is_from_page else 'inbound',
                        'status': 'read' if legacy_message.is_read else 'sent',
                        'message_type': (legacy_message.message_type or 'TEXT').lower(),
                        'text_content': legacy_message.content or '',
                        'media_url': legacy_message.attachment_url or '',
                        'payload': legacy_message.template_payload or {},
                        'attachments': legacy_message.quick_replies or [],
                        'sender_external_id': target_account.page_id if legacy_message.is_from_page else target_conversation.participant_external_id,
                        'sender_name': target_account.page_name if legacy_message.is_from_page else target_conversation.participant_name,
                        'sent_at': legacy_message.sent_at,
                        'delivered_at': legacy_message.delivered_at,
                        'read_at': legacy_message.read_at,
                        'is_active': True,
                    },
                )
```

### 7.3 Migration sequence

1. Create new canonical tables.
2. Backfill store-owned automation profile.
3. Backfill automation rules, sessions and logs.
4. Backfill canonical handover state.
5. Backfill Messenger canonical app from `apps.messaging`.
6. Switch services, serializers and routers.
7. Switch frontend contracts.
8. Remove old models and dead serializers.

## 8. Frontend update plan

The frontend currently exposes the old company-centric contract.

Required updates in `pastita-dash`:

1. Rename `CompanyProfile` type to `AutomationProfile`.
2. Rename `CreateCompanyProfile` and `UpdateCompanyProfile` to store-centric names.
3. Replace `company_id` filters and params with `store_id`.
4. Rename service `companyProfileService` to `automationProfileService`.
5. Rename pages:
   - `CompanyProfilesPage` -> `AutomationProfilesPage`
   - `CompanyProfileDetailPage` -> `AutomationProfileDetailPage`
6. Make the automation UI show store data as read-only source-of-truth fields.
7. Move all handover status rendering to `Conversation.handover_status` from the canonical API only.
8. Remove any frontend dependency on the old Messenger app shape.
9. Create one normalized messaging DTO per channel.
10. In Chakra UI v3, standardize layouts around these sections:
   - Store identity
   - Automation profile
   - Auto rules
   - Live conversations
   - Human handover queue
   - Channel accounts

## 9. Ordered tasklist

### P0 - Structural correctness

1. Freeze the canonical architecture decision in ADR form.
2. Create `StoreAutomationProfile` and stop adding fields to `CompanyProfile`.
3. Move all `company` FKs in automation operational models to `store`.
4. Remove the duplicate handover model from `apps.conversations`.
5. Remove the duplicate flow declarations from `apps.automation.models.py`.
6. Choose `apps.messenger` as the canonical Messenger app and stop feature work in `apps.messaging`.

### P1 - Contract cutover

1. Add canonical serializers and viewsets for store-owned automation resources.
2. Add `store_id` filtering everywhere automation APIs currently require `company_id`.
3. Expose store-derived identity fields read-only from automation profile serializers.
4. Align report schedules and exports to `store_id`.
5. Update websocket/SSE channels to publish store-scoped automation events.

### P2 - Frontend cutover

1. Rename automation types and services.
2. Replace `company_id` routes, query params and filter state.
3. Refactor pages to read store identity from store endpoints and automation config from profile endpoint.
4. Normalize Messenger and handover UI contracts.
5. Remove dead pages/components bound to old model names.

### P3 - Cleanup and deletion

1. Delete `CompanyProfile` once all reads/writes are migrated.
2. Delete `apps.messaging` once Messenger cutover is complete.
3. Delete duplicate serializers and dead imports.
4. Delete compatibility code paths and fallback logic.
5. Remove obsolete docs and commands.

## 10. Test plan

### 10.1 Database migration tests

- migrate stores with linked company profile
- migrate stores with no company profile
- migrate company profiles with no linked store
- migrate active and inactive auto messages
- migrate sessions with cart and payment snapshots
- migrate mixed legacy handover rows
- migrate Messenger rows from `apps.messaging` into canonical `apps.messenger`

### 10.2 Backend behavior tests

- create store automation profile from store
- update automation profile without mutating store business identity incorrectly
- list automation rules by `store_id`
- create automation session on inbound WhatsApp message
- fetch conversation handover from canonical model only
- transfer bot to human and back with canonical handover state
- ensure message processing respects handover status
- ensure reports filter by `store_id`

### 10.3 API contract tests

- `GET /automation/profiles/` returns store-derived identity fields
- `POST /automation/profiles/` requires `store`
- `GET /automation/rules/?store_id=` works
- `GET /automation/sessions/?store_id=` works
- `GET /automation/logs/?store_id=` works
- conversations API exposes canonical handover status
- messenger API uses a single serializer set only

### 10.4 Frontend integration tests

- automation profile pages load from store + automation profile without company duplication
- filters use `store_id`
- handover actions update conversation UI correctly
- Messenger inbox works against only one backend app contract
- no screen relies on `company_name` as editable business identity

### 10.5 Non-functional tests

- query count comparison before and after serializer cutover
- index validation for `store`, `status`, `created_at`, `phone_number`
- regression test for real-time conversation updates
- migration performance on production-like dataset

## 11. Final recommendation

This refactor should not be approached as incremental cleanup of random files. It needs one explicit domain decision:

- `Store` is the only business source of truth.
- automation is a store extension, not a parallel company aggregate.
- handover has one table only.
- Messenger has one app only.
- operational automation records are store-owned.

Anything short of that preserves ambiguity and guarantees more duplicate code later.
