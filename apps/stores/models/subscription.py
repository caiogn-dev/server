"""
StoreSubscription — assinatura SaaS de uma loja (1:1 com Store).
A cobrança MercadoPago é wired no sub-projeto Billing; aqui é só o estado.
"""
import uuid
from django.db import models


class StoreSubscription(models.Model):
    class Status(models.TextChoices):
        TRIALING = 'trialing', 'Em trial'
        ACTIVE = 'active', 'Ativa'
        PAST_DUE = 'past_due', 'Pagamento atrasado'
        SUSPENDED = 'suspended', 'Suspensa'
        CANCELED = 'canceled', 'Cancelada'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    store = models.OneToOneField(
        'stores.Store', on_delete=models.CASCADE, related_name='subscription'
    )
    class BillingCycle(models.TextChoices):
        MONTHLY = "monthly", "Mensal"
        ANNUAL = "annual", "Anual"

    plan = models.CharField(max_length=20, default='starter')
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.TRIALING)
    billing_cycle = models.CharField(
        max_length=10, choices=BillingCycle.choices, default=BillingCycle.MONTHLY
    )
    # Distingue quem caiu pro Grátis por inadimplência (mostra aviso) de quem
    # escolheu o Grátis.
    downgraded_for_nonpayment = models.BooleanField(default=False)

    # MercadoPago (preenchidos quando a cobrança for ligada)
    mp_preapproval_id = models.CharField(max_length=255, blank=True, default='')
    # INFORMACIONAL apenas — nunca usado como portão/guard de acesso ou feature.
    # O sinal canônico de adesão aprovada é mark_setup_fee_paid() (via webhook).
    setup_fee_paid = models.BooleanField(default=False)

    current_period_end = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    canceled_at = models.DateTimeField(null=True, blank=True)

    # Ciclo de vida do billing (Fase 1)
    grace_until = models.DateTimeField(null=True, blank=True)      # fim da carência pós-trial
    dunning_since = models.DateTimeField(null=True, blank=True)    # início do past_due
    mp_setup_payment_id = models.CharField(max_length=255, blank=True, default='')  # pagamento da adesão

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'store_subscriptions'
        verbose_name = 'Store Subscription'
        verbose_name_plural = 'Store Subscriptions'

    def __str__(self):
        return f"{self.store.name} — {self.plan} ({self.status})"
