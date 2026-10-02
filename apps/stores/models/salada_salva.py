"""Salada criada pelo cliente no montador e guardada pelo número dele (02/10).

A chave é `telefone`: o número PROVADO pelo código do WhatsApp, em dígitos.
Não é FK de usuário de propósito — o pedido do dono é que todo login feito com
o código daquele número veja as saladas, e um número pode ter mais de uma conta
(legado `cliente_<dígitos>` e conta de e-mail que depois confirmou o número).

`client_id` nasce no aparelho: a salada montada antes do login é gravada lá e
sobe depois. Sincronizar de novo atualiza, não duplica.
"""
import uuid

from django.db import models


class SaladaSalva(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    store = models.ForeignKey('stores.Store', on_delete=models.CASCADE, related_name='saladas_salvas')
    telefone = models.CharField(max_length=20, db_index=True)
    client_id = models.UUIDField()
    nome = models.CharField(max_length=40)
    #: [{'id', 'name', 'role', 'role_label', 'image_url'}] — o preço NÃO mora
    #: aqui: ao pedir de novo, o backend precifica pelo id, como sempre.
    ingredientes = models.JSONField(default=list)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'store_saladas_salvas'
        verbose_name = 'Salada salva'
        verbose_name_plural = 'Saladas salvas'
        ordering = ['-atualizado_em']
        constraints = [
            models.UniqueConstraint(fields=['store', 'telefone', 'client_id'], name='salada_salva_unica_por_aparelho'),
        ]

    def __str__(self):
        return f'{self.nome} ({self.telefone})'
