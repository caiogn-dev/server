"""Entregador da loja — para atribuir no pedido e ranquear (do Prefiro)."""
from django.db import models

from apps.core.models import BaseModel


class Entregador(BaseModel):
    """`is_active` (BaseModel) = ainda trabalha na loja. Desligar não apaga:
    o histórico de entregas continua com o nome dele."""

    store = models.ForeignKey('stores.Store', on_delete=models.CASCADE, related_name='entregadores')
    nome = models.CharField(max_length=120)
    telefone = models.CharField(max_length=20, blank=True)

    class Meta:
        db_table = 'store_entregadores'
        ordering = ['nome']

    def __str__(self):
        return self.nome
