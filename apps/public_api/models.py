"""
Lead capture model — public form submissions from /cadastro.
"""
import uuid
from django.db import models


class Lead(models.Model):
    STATUS_CHOICES = [
        ('new', 'Novo'),
        ('contacted', 'Contatado'),
        ('converted', 'Convertido'),
        ('lost', 'Perdido'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    phone = models.CharField(max_length=30)
    email = models.EmailField(blank=True)
    city = models.CharField(max_length=100, blank=True)
    business_type = models.CharField(max_length=100, blank=True)
    message = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='new')
    source = models.CharField(max_length=50, default='cadastro')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Lead'
        verbose_name_plural = 'Leads'

    def __str__(self):
        return f'{self.name} ({self.phone})'
