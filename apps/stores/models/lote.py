"""Lote de produção: um por prato por dia (Agrião, 09/10).

Sai impresso na etiqueta (`{lote}`) e fica consultável no painel para recolher
um lote específico. `produto_nome` é foto do nome no dia: renomear ou apagar o
prato não pode apagar a rastreabilidade do que já foi vendido.
"""
import uuid

from django.db import models


class StoreLote(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    store = models.ForeignKey('stores.Store', on_delete=models.CASCADE, related_name='lotes')
    product = models.ForeignKey('stores.StoreProduct', null=True, blank=True, on_delete=models.SET_NULL, related_name='lotes')
    produto_nome = models.CharField(max_length=255)
    codigo = models.CharField(max_length=40, db_index=True)
    fabricacao = models.DateField(db_index=True)
    validade = models.DateField()
    #: ordem do prato no dia, na loja (01, 02…) — parte do código
    sequencia = models.PositiveIntegerField()
    #: etiquetas impressas com este lote (reimpressão soma)
    etiquetas = models.PositiveIntegerField(default=0)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'store_lotes'
        ordering = ('-fabricacao', '-sequencia')
        constraints = [
            models.UniqueConstraint(fields=('store', 'codigo'), name='uniq_lote_codigo_por_loja'),
            models.UniqueConstraint(fields=('store', 'product', 'fabricacao'), name='uniq_lote_prato_por_dia'),
        ]

    def __str__(self):
        return self.codigo
