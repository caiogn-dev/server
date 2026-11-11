"""Cotação do Uber Direct guardada contra o frete que o cliente pagou.

Cotar não cria entrega nem custa nada. É a base para decidir se vale ligar o
despacho pela Uber e qual tabela de frete cobre o custo dela.
"""
from django.db import models

from apps.core.models import BaseModel


class UberCotacao(BaseModel):
    class Origem(models.TextChoices):
        SOMBRA = 'sombra', 'Pedido novo (modo sombra)'
        HISTORICO = 'historico', 'Pedido antigo cotado depois'
        DESPACHO = 'despacho', 'Cotação usada para despachar'

    store = models.ForeignKey('stores.Store', on_delete=models.CASCADE, related_name='uber_cotacoes')
    order = models.ForeignKey(
        'stores.StoreOrder', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='uber_cotacoes',
    )
    origem = models.CharField(max_length=12, choices=Origem.choices, default=Origem.SOMBRA)
    quote_id = models.CharField(max_length=80, blank=True, default='')
    fee = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True,
                              help_text='Quanto a Uber cobraria (R$). Vazio = Uber recusou.')
    taxa_cobrada = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True,
                                       help_text='Frete que o cliente pagou no pedido.')
    distancia_km = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True,
                                       help_text='Linha reta loja → cliente.')
    duracao_min = models.PositiveSmallIntegerField(null=True, blank=True)
    coleta_min = models.PositiveSmallIntegerField(null=True, blank=True)
    erro = models.TextField(blank=True, default='')

    class Meta:
        db_table = 'store_uber_cotacoes'
        ordering = ['-created_at']
        indexes = [models.Index(fields=['store', 'created_at'])]

    @property
    def diferenca(self):
        """Positivo = a loja paga do bolso essa diferença."""
        if self.fee is None or self.taxa_cobrada is None:
            return None
        return self.fee - self.taxa_cobrada

    def __str__(self):
        return f'{self.store_id} {self.fee} vs {self.taxa_cobrada}'
