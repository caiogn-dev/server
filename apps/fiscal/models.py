import uuid

from django.db import models


class FiscalDocument(models.Model):
    """Documento fiscal emitido para um pedido — NFC-e (65) ou NF-e (55).

    A configuração fiscal vive em `store.metadata['fiscal']`:
        provider: 'focus' | 'sefaz'
        ambiente: 'homologacao' | 'producao'
        focus_token: token da API Focus NFe (provider focus)
        cnpj, inscricao_estadual, serie
        ncm_padrao (ex.: 21069090), cfop_padrao (ex.: 5102)
    """

    class Provider(models.TextChoices):
        FOCUS = 'focus', 'Focus NFe'
        SEFAZ = 'sefaz', 'SEFAZ direto'

    class Modelo(models.TextChoices):
        """65 = NFC-e (consumidor final, balcão/delivery).
        55 = NF-e (venda a empresa; exige destinatário e endereço completos)."""

        NFCE = '65', 'NFC-e'
        NFE = '55', 'NF-e'

    class Status(models.TextChoices):
        PENDING = 'pending', 'Processando'
        AUTHORIZED = 'authorized', 'Autorizada'
        REJECTED = 'rejected', 'Rejeitada'
        CANCELLED = 'cancelled', 'Cancelada'
        ERROR = 'error', 'Erro'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    store = models.ForeignKey('stores.Store', on_delete=models.CASCADE, related_name='fiscal_documents')
    order = models.ForeignKey('stores.StoreOrder', on_delete=models.PROTECT, related_name='fiscal_documents')

    provider = models.CharField(max_length=20, choices=Provider.choices)
    modelo = models.CharField(max_length=2, choices=Modelo.choices, default=Modelo.NFCE)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    # Nota de homologação não tem valor fiscal: não pode contar como "já
    # emitida" quando a loja vira para produção.
    ambiente = models.CharField(max_length=12, default='homologacao')

    # ref idempotente enviada ao provedor (re-emissão consulta em vez de duplicar)
    ref = models.CharField(max_length=64, unique=True)
    chave_acesso = models.CharField(max_length=44, blank=True)
    numero = models.CharField(max_length=20, blank=True)
    serie = models.CharField(max_length=10, blank=True)
    qrcode_url = models.TextField(blank=True)
    danfe_url = models.TextField(blank=True)
    xml_url = models.TextField(blank=True)
    error_message = models.TextField(blank=True)
    response = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['store', 'status']),
            models.Index(fields=['order']),
        ]

    def __str__(self):
        return f'{self.get_modelo_display()} {self.status} pedido={self.order_id}'


class DestinatarioFiscal(models.Model):
    """Para quem a nota sai — cadastro da loja, não endereço de entrega.

    A NF-e lia o destinatário de `order.delivery_address`. Pedido de retirada
    para empresa não tem endereço de entrega completo, e o endereço de entrega
    de um pedido com frete não é necessariamente a sede de quem compra. Aqui o
    operador registra uma vez e reaproveita na próxima nota.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    store = models.ForeignKey('stores.Store', on_delete=models.CASCADE, related_name='destinatarios_fiscais')
    customer = models.ForeignKey(
        'stores.StoreCustomer', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='destinatarios_fiscais',
    )

    # Só dígitos: CPF (11) ou CNPJ (14).
    documento = models.CharField(max_length=14)
    nome = models.CharField(max_length=255)
    inscricao_estadual = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    telefone = models.CharField(max_length=20, blank=True)

    street = models.CharField(max_length=255, blank=True)
    number = models.CharField(max_length=20, blank=True)
    complement = models.CharField(max_length=120, blank=True)
    neighborhood = models.CharField(max_length=120, blank=True)
    city = models.CharField(max_length=120, blank=True)
    state = models.CharField(max_length=2, blank=True)
    zip_code = models.CharField(max_length=8, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['nome']
        constraints = [
            models.UniqueConstraint(fields=['store', 'documento'], name='destinatario_unico_por_loja'),
        ]

    def __str__(self):
        return f'{self.nome} ({self.documento})'
