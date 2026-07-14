from django.contrib.auth import get_user_model
from django.db import models

from apps.core.models import BaseModel
from apps.core.utils import mask_token, token_encryption

User = get_user_model()


class WhatsAppAccount(BaseModel):
    """WhatsApp Business Account configuration."""

    class AccountStatus(models.TextChoices):
        ACTIVE = 'active', 'Active'
        INACTIVE = 'inactive', 'Inactive'
        SUSPENDED = 'suspended', 'Suspended'
        PENDING = 'pending', 'Pending Verification'

    name = models.CharField(max_length=255)
    phone_number_id = models.CharField(max_length=50, unique=True, db_index=True)
    waba_id = models.CharField(max_length=50, db_index=True)
    phone_number = models.CharField(max_length=20)
    display_phone_number = models.CharField(max_length=30, blank=True)

    access_token_encrypted = models.TextField()
    token_expires_at = models.DateTimeField(null=True, blank=True)
    token_version = models.PositiveIntegerField(default=1)

    status = models.CharField(
        max_length=20,
        choices=AccountStatus.choices,
        default=AccountStatus.PENDING,
    )

    webhook_verify_token = models.CharField(max_length=255, blank=True)

    default_agent = models.ForeignKey(
        'agents.Agent',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='whatsapp_accounts',
        help_text='Agente IA padrão para respostas automáticas',
    )
    auto_response_enabled = models.BooleanField(default=True)
    human_handoff_enabled = models.BooleanField(default=True)

    metadata = models.JSONField(default=dict, blank=True)
    owner = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='whatsapp_accounts',
        null=True,
        blank=True,
    )

    class Meta:
        app_label = 'whatsapp'
        db_table = 'whatsapp_accounts'
        verbose_name = 'WhatsApp Account'
        verbose_name_plural = 'WhatsApp Accounts'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} ({self.display_phone_number or self.phone_number})"

    @property
    def access_token(self) -> str:
        return token_encryption.decrypt(self.access_token_encrypted)

    @access_token.setter
    def access_token(self, value: str):
        self.access_token_encrypted = token_encryption.encrypt(value)
        self.token_version += 1

    @property
    def masked_token(self) -> str:
        # Token ilegível (chave Fernet trocada / registro legado) não pode
        # derrubar a listagem de contas do painel com 500.
        try:
            return mask_token(self.access_token)
        except Exception:
            return '<token inválido — reconecte a conta>'

    def rotate_token(self, new_token: str):
        self.access_token = new_token
        self.save(update_fields=['access_token_encrypted', 'token_version', 'updated_at'])
