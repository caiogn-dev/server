""" Commerce - Models completos e independentes. """
import uuid
from django.db import models
from django.conf import settings
from apps.core_v2.models import BaseModel


class Store(BaseModel):
    """Loja/Empresa."""
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=100, unique=True, db_index=True)
    description = models.TextField(blank=True)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='stores'
    )
    # Business info
    business_name = models.CharField(max_length=255, blank=True)
    business_type = models.CharField(max_length=50, default='retail')
    # Contact
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    # Address
    address = models.TextField(blank=True)
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=100, blank=True)
    # Settings
    settings = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.name


class Category(BaseModel):
    """Categoria de produtos."""
    store = models.ForeignKey(
        Store, on_delete=models.CASCADE, related_name='categories'
    )
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=100, db_index=True)
    description = models.TextField(blank=True)
    image = models.URLField(blank=True)
    parent = models.ForeignKey(
        'self', on_delete=models.CASCADE, null=True, blank=True,
        related_name='children'
    )

    class Meta:
        ordering = ['name']
        unique_together = ['store', 'slug']

    def __str__(self):
        return self.name


class Product(BaseModel):
    """Produto."""
    store = models.ForeignKey(
        Store, on_delete=models.CASCADE, related_name='products'
    )
    category = models.ForeignKey(
        Category, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='products'
    )
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=100, db_index=True)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    cost_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    stock_quantity = models.IntegerField(default=0)
    sku = models.CharField(max_length=100, blank=True)
    images = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ['-created_at']
        unique_together = ['store', 'slug']

    def __str__(self):
        return self.name


class Customer(BaseModel):
    """Cliente."""
    store = models.ForeignKey(
        Store, on_delete=models.CASCADE, related_name='customers'
    )
    name = models.CharField(max_length=255)
    phone = models.CharField(max_length=20, db_index=True)
    email = models.EmailField(blank=True)
    # IDs externos
    whatsapp_id = models.CharField(max_length=100, blank=True)
    instagram_id = models.CharField(max_length=100, blank=True)
    # Dados
    cpf = models.CharField(max_length=14, blank=True)
    address = models.TextField(blank=True)
    # Stats
    total_orders = models.IntegerField(default=0)
    total_spent = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.name


class Order(BaseModel):
    """Pedido."""
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pendente'
        CONFIRMED = 'confirmed', 'Confirmado'
        PAID = 'paid', 'Pago'
        SHIPPED = 'shipped', 'Enviado'
        DELIVERED = 'delivered', 'Entregue'
        CANCELLED = 'cancelled', 'Cancelado'

    store = models.ForeignKey(
        Store, on_delete=models.CASCADE, related_name='orders'
    )
    customer = models.ForeignKey(
        Customer, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='orders'
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING
    )
    # Valores
    subtotal = models.DecimalField(max_digits=10, decimal_places=2)
    shipping_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    discount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=10, decimal_places=2)
    # Dados do cliente (snapshot)
    customer_name = models.CharField(max_length=255)
    customer_phone = models.CharField(max_length=20)
    customer_email = models.EmailField(blank=True)
    shipping_address = models.TextField()
    # Pagamento
    payment_method = models.CharField(max_length=50, blank=True)
    payment_status = models.CharField(max_length=20, default='pending')
    # Timestamps
    paid_at = models.DateTimeField(null=True, blank=True)
    shipped_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'Pedido {self.id}'


class OrderItem(models.Model):
    """Item de pedido."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(
        Order, on_delete=models.CASCADE, related_name='items'
    )
    product = models.ForeignKey(
        Product, on_delete=models.SET_NULL, null=True, blank=True
    )
    product_name = models.CharField(max_length=255)
    product_price = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.PositiveIntegerField()
    total = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        ordering = ['-id']

    def __str__(self):
        return f'{self.product_name} x{self.quantity}'


class Payment(BaseModel):
    """Pagamento."""
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pendente'
        APPROVED = 'approved', 'Aprovado'
        REJECTED = 'rejected', 'Rejeitado'
        REFUNDED = 'refunded', 'Reembolsado'

    order = models.ForeignKey(
        Order, on_delete=models.CASCADE, related_name='payments'
    )
    provider = models.CharField(max_length=50, default='mercadopago')
    provider_payment_id = models.CharField(max_length=255, blank=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_method = models.CharField(max_length=50, blank=True)
    installments = models.PositiveIntegerField(default=1)
    paid_at = models.DateTimeField(null=True, blank=True)
    provider_response = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'Pagamento {self.id}'
