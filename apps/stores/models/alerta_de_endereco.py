"""Aviso de endereço divergente — numa tabela própria (01/10).

Morava em `StoreOrder.metadata['endereco_divergente']`. A task gravava 0,2 s
depois de criar o pedido, e o checkout salvava o pedido de novo com o
`metadata` que tinha em memória, sem o aviso: 0 pedidos marcados em 30 dias,
inclusive o Thiago (407 Sul escrito, pin na 106 Norte), que o log detectou.

Numa tabela à parte, salvar o pedido não tem como apagar o aviso.
"""
from django.db import models


class AlertaDeEndereco(models.Model):
    order = models.OneToOneField(
        'stores.StoreOrder', on_delete=models.CASCADE, related_name='alerta_de_endereco',
    )
    #: {'digitado', 'pin', 'lat', 'lng', 'aviso', 'distancia_km'?}
    dados = models.JSONField(default=dict)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'store_alerta_de_endereco'
        verbose_name = 'Alerta de endereço'
        verbose_name_plural = 'Alertas de endereço'

    def __str__(self):
        return f'{self.order_id}: {self.dados.get("aviso", "")[:60]}'
