"""
Link na Bio: links customizados por loja + estatísticas de clique/visualização.
"""
import uuid

from django.db import models
from django.db.models import F
from django.utils import timezone


class StoreBioLink(models.Model):
    """Link customizado da página Link na Bio de uma loja."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    store = models.ForeignKey('stores.Store', on_delete=models.CASCADE, related_name='bio_links')
    title = models.CharField(max_length=80)
    url = models.URLField(max_length=500)
    icon = models.CharField(max_length=8, blank=True, default='')
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['sort_order', 'created_at']
        indexes = [models.Index(fields=['store', 'is_active'], name='biolink_store_active_idx')]

    def __str__(self):
        return f'{self.title} ({self.store.slug})'


class BioClickStat(models.Model):
    """Agregado diário de views/cliques da página bio. link_key: page:view, auto:*, custom:<uuid>."""

    store = models.ForeignKey('stores.Store', on_delete=models.CASCADE, related_name='bio_click_stats')
    date = models.DateField()
    link_key = models.CharField(max_length=64)
    clicks = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['store', 'date', 'link_key'], name='bioclick_store_date_key_uniq')
        ]
        indexes = [models.Index(fields=['store', 'date'], name='bioclick_store_date_idx')]

    @classmethod
    def bump(cls, store, link_key):
        obj, _created = cls.objects.get_or_create(
            store=store, date=timezone.localdate(), link_key=link_key, defaults={'clicks': 0}
        )
        cls.objects.filter(pk=obj.pk).update(clicks=F('clicks') + 1)

    def __str__(self):
        return f'{self.store.slug} {self.date} {self.link_key}={self.clicks}'
