"""Banners do cardápio: até 3 imagens que a loja escolhe no painel.

Separado do `Store.banner` de propósito: aquele é a CAPA (uma faixa fixa atrás
do logo); isto é o carrossel promocional, que muda toda semana. Misturar os dois
faria trocar a promoção da semana apagar a identidade visual da loja.
"""
import uuid

from django.db import models

from .base import Store, _validate_image_upload

#: Teto de banners por loja. Mais que isso vira parede de anúncio antes do
#: primeiro prato — o cliente abriu o cardápio para comer, não para rolar vitrine.
MAXIMO_DE_BANNERS = 3


class StoreBanner(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name='banners')
    image = models.ImageField(upload_to='stores/banners/carrossel/',
                              validators=[_validate_image_upload])
    position = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'store_banners'
        ordering = ['position', 'created_at']

    def __str__(self):
        return f'{self.store.slug} banner {self.position}'
