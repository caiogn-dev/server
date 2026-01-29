"""
Store category model.
"""
import uuid
from django.db import models
from .base import Store


class StoreCategory(models.Model):
    """Product categories specific to a store."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    store = models.ForeignKey(
        Store,
        on_delete=models.CASCADE,
        related_name='categories'
    )

    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=100)
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to='stores/categories/', blank=True, null=True)
    image_url = models.URLField(blank=True)

    parent = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='children'
    )

    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'store_categories'
        verbose_name = 'Store Category'
        verbose_name_plural = 'Store Categories'
        unique_together = ['store', 'slug']
        ordering = ['store', 'sort_order', 'name']

    def __str__(self):
        return f"{self.store.name} - {self.name}"

    def get_image_url(self):
        if self.image:
            return self.image.url
        return self.image_url or ''
