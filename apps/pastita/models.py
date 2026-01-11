"""
Pastita Models - Massas Artesanais Premium
Product inheritance system with specialized product types.
"""
import os
from decimal import Decimal
from django.conf import settings
from django.db import models
from django.templatetags.static import static
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin


# =============================================================================
# USER MODEL
# =============================================================================

class CustomUserManager(BaseUserManager):
    """Custom user manager using email as identifier."""
    
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("O email é obrigatório")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser precisa ter is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser precisa ter is_superuser=True.')

        return self.create_user(email, password, **extra_fields)


class CustomUser(AbstractBaseUser, PermissionsMixin):
    """Custom user model with email as username."""
    
    email = models.EmailField('Email', unique=True)
    first_name = models.CharField('Nome', max_length=30, blank=True)
    last_name = models.CharField('Sobrenome', max_length=30, blank=True)
    phone = models.CharField('Telefone', max_length=20, blank=True)
    is_active = models.BooleanField('Ativo', default=True)
    is_staff = models.BooleanField('Staff', default=False)
    date_joined = models.DateTimeField('Data de cadastro', auto_now_add=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    objects = CustomUserManager()

    class Meta:
        verbose_name = 'Usuário'
        verbose_name_plural = 'Usuários'

    def __str__(self):
        return self.email

    def get_full_name(self):
        return f"{self.first_name} {self.last_name}".strip() or self.email

    def get_short_name(self):
        return self.first_name or self.email.split('@')[0]


# =============================================================================
# PRODUTO BASE
# =============================================================================

class Produto(models.Model):
    """Base product model with common fields."""
    
    nome = models.CharField("Nome do produto", max_length=100)
    descricao = models.TextField("Descrição", blank=True)
    preco = models.DecimalField("Preço (R$)", max_digits=8, decimal_places=2)
    imagem = models.ImageField("Imagem", upload_to='produtos/', blank=True, null=True)
    ativo = models.BooleanField("Ativo", default=True)
    criado_em = models.DateTimeField("Criado em", auto_now_add=True)
    atualizado_em = models.DateTimeField("Atualizado em", auto_now=True)

    class Meta:
        verbose_name = "Produto"
        verbose_name_plural = "Produtos"
        ordering = ['-criado_em']

    def __str__(self):
        return self.nome

    @property
    def imagem_url_segura(self):
        """Return safe image URL with fallback."""
        try:
            if self.imagem and hasattr(self.imagem, 'path'):
                if os.path.exists(self.imagem.path):
                    return self.imagem.url
        except Exception:
            pass
        return static('img/padrao.png')


# =============================================================================
# MOLHO (Sauce)
# =============================================================================

class Molho(Produto):
    """Sauce product with type and quantity."""
    
    MOLHO_CHOICES = [
        ('4queijos', '4 Queijos'),
        ('sugo', 'Sugo'),
        ('branco', 'Molho Branco'),
        ('pesto', 'Pesto'),
        ('bolonhesa', 'Bolonhesa'),
        ('carbonara', 'Carbonara'),
    ]
    
    tipo = models.CharField("Tipo de Molho", max_length=20, choices=MOLHO_CHOICES)
    quantidade = models.CharField("Quantidade", max_length=50, help_text="Ex.: 150g, 300g")

    class Meta:
        unique_together = ('tipo', 'quantidade')
        verbose_name = "Molho"
        verbose_name_plural = "Molhos"

    def __str__(self):
        return f"{self.get_tipo_display()} ({self.quantidade})"

    def save(self, *args, **kwargs):
        if not self.nome:
            self.nome = f"Molho {self.get_tipo_display()}"
        super().save(*args, **kwargs)


# =============================================================================
# CARNE (Meat)
# =============================================================================

class Carne(Produto):
    """Meat product with type, quantity and compatible sauces."""
    
    CARNE_CHOICES = [
        ('isca_file', 'Iscas de Filé'),
        ('frango_grelhado', 'Frango Grelhado'),
        ('carne_moida', 'Carne Moída'),
        ('linguica_calabresa', 'Linguiça Calabresa'),
        ('bacon', 'Bacon'),
        ('costela', 'Costela Desfiada'),
        ('picanha', 'Picanha'),
    ]
    
    tipo = models.CharField("Tipo de Carne", max_length=30, choices=CARNE_CHOICES)
    quantidade = models.CharField("Quantidade", max_length=50, help_text="Ex.: 200g, 300g")
    molhos = models.ManyToManyField(
        Molho,
        verbose_name="Molhos disponíveis",
        blank=True,
        related_name='carnes_compativeis',
        help_text="Selecione os molhos que podem acompanhar esta carne"
    )

    class Meta:
        unique_together = ('tipo', 'quantidade')
        verbose_name = "Carne"
        verbose_name_plural = "Carnes"

    def __str__(self):
        return f"{self.get_tipo_display()} ({self.quantidade})"

    def save(self, *args, **kwargs):
        if not self.nome:
            self.nome = f"{self.get_tipo_display()}"
        super().save(*args, **kwargs)


# =============================================================================
# RONDELLI (Pasta)
# =============================================================================

class Rondelli(Produto):
    """Rondelli pasta with flavor and category (Classic/Gourmet)."""
    
    CLASSICOS = 'classicos'
    GOURMET = 'gourmet'
    CATEGORIA_CHOICES = [
        (CLASSICOS, 'Clássicos'),
        (GOURMET, 'Gourmet'),
    ]
    
    RONDELLI_CHOICES = [
        # Clássicos
        ('presunto_e_queijo', 'Presunto e Queijo'),
        ('calabresa_com_requeijao', 'Calabresa com Requeijão'),
        ('frango_requeijao_mucarela', 'Frango, Requeijão e Muçarela'),
        ('linguica_toscana_erva_doce', 'Linguiça Toscana e Erva-Doce'),
        ('queijo_brocolis', 'Queijo e Brócolis'),
        ('tomate_seco_rucula', 'Tomate Seco com Rúcula'),
        ('4queijos', '4 Queijos'),
        ('queijos_manjericao', 'Queijos com Manjericão'),
        ('palmito', 'Palmito'),
        # Gourmet
        ('bacalhau_cremoso', 'Bacalhau Cremoso'),
        ('queijo_brie_damasco_castanha', 'Queijo Brie, Damasco e Castanha'),
        ('chambari_especiarias', 'Chambari com Especiarias'),
        ('camarao_catupiry', 'Camarão com Catupiry'),
        ('carne_seca_abobora', 'Carne Seca com Abóbora'),
    ]
    
    categoria = models.CharField(
        "Categoria",
        max_length=10,
        choices=CATEGORIA_CHOICES,
        default=CLASSICOS,
        help_text="Defina se este sabor é Clássico ou Gourmet"
    )
    sabor = models.CharField(
        "Sabor de Rondelli",
        max_length=50,
        choices=RONDELLI_CHOICES
    )
    quantidade = models.CharField(
        "Quantidade",
        max_length=50,
        help_text="Ex.: 500g, 1kg"
    )

    class Meta:
        unique_together = ('sabor', 'quantidade')
        verbose_name = "Rondelli"
        verbose_name_plural = "Rondellis"

    def __str__(self):
        return f"{self.get_sabor_display()} ({self.quantidade})"

    def save(self, *args, **kwargs):
        if not self.nome:
            self.nome = f"Rondelli {self.get_sabor_display()}"
        super().save(*args, **kwargs)

    @property
    def is_gourmet(self):
        return self.categoria == self.GOURMET


# =============================================================================
# COMBO (Bundle)
# =============================================================================

class Combo(models.Model):
    """Combo bundle with molhos, carne and rondelli."""
    
    nome = models.CharField("Nome do combo", max_length=100)
    descricao = models.TextField("Descrição", blank=True)
    molhos = models.ManyToManyField(
        Molho,
        verbose_name="Molhos inclusos",
        blank=True,
        related_name='combos',
        help_text="Selecione os molhos inclusos neste combo"
    )
    carne = models.ForeignKey(
        Carne,
        verbose_name="Carne",
        on_delete=models.SET_NULL,
        related_name='combos',
        blank=True,
        null=True
    )
    rondelli = models.ForeignKey(
        Rondelli,
        verbose_name="Rondelli",
        on_delete=models.SET_NULL,
        related_name='combos',
        blank=True,
        null=True
    )
    preco = models.DecimalField("Preço (R$)", max_digits=8, decimal_places=2)
    preco_original = models.DecimalField(
        "Preço Original (R$)", 
        max_digits=8, 
        decimal_places=2,
        blank=True,
        null=True,
        help_text="Preço sem desconto (para mostrar economia)"
    )
    imagem = models.ImageField("Imagem do combo", upload_to='combos/', blank=True, null=True)
    ativo = models.BooleanField("Ativo", default=True)
    destaque = models.BooleanField("Destaque", default=False, help_text="Mostrar como 'Mais Pedido'")
    criado_em = models.DateTimeField("Criado em", auto_now_add=True)
    atualizado_em = models.DateTimeField("Atualizado em", auto_now=True)

    class Meta:
        verbose_name = "Combo"
        verbose_name_plural = "Combos"
        ordering = ['-destaque', '-criado_em']

    def __str__(self):
        return self.nome

    @property
    def imagem_url_segura(self):
        """Return safe image URL with fallback."""
        try:
            if self.imagem and hasattr(self.imagem, 'path'):
                if os.path.exists(self.imagem.path):
                    return self.imagem.url
        except Exception:
            pass
        return static('img/padrao.png')

    @property
    def economia(self):
        """Calculate savings if original price is set."""
        if self.preco_original and self.preco_original > self.preco:
            return self.preco_original - self.preco
        return Decimal('0.00')

    @property
    def percentual_desconto(self):
        """Calculate discount percentage."""
        if self.preco_original and self.preco_original > 0:
            return int(((self.preco_original - self.preco) / self.preco_original) * 100)
        return 0


# =============================================================================
# CARRINHO (Cart)
# =============================================================================

class Carrinho(models.Model):
    """Shopping cart - user-based only."""
    
    usuario = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='carrinho_pastita'
    )
    criado_em = models.DateTimeField("Criado em", auto_now_add=True)
    atualizado_em = models.DateTimeField("Atualizado em", auto_now=True)

    class Meta:
        verbose_name = "Carrinho"
        verbose_name_plural = "Carrinhos"

    def __str__(self):
        return f"Carrinho de {self.usuario.email}"

    @property
    def total_produtos(self):
        """Total of regular products."""
        return sum(item.subtotal for item in self.itens.all())

    @property
    def total_combos(self):
        """Total of combos."""
        return sum(item.subtotal for item in self.combos.all())

    @property
    def total(self):
        """Grand total."""
        return self.total_produtos + self.total_combos

    @property
    def quantidade_itens(self):
        """Total item count."""
        produtos = sum(item.quantidade for item in self.itens.all())
        combos = sum(item.quantidade for item in self.combos.all())
        return produtos + combos

    @property
    def tem_itens(self):
        """Check if cart has any items."""
        return self.itens.exists() or self.combos.exists()


class ItemCarrinho(models.Model):
    """Cart item for regular products."""
    
    carrinho = models.ForeignKey(
        Carrinho,
        on_delete=models.CASCADE,
        related_name='itens'
    )
    produto = models.ForeignKey(
        Produto,
        on_delete=models.CASCADE,
        related_name='itens_carrinho'
    )
    quantidade = models.PositiveIntegerField("Quantidade", default=1)
    criado_em = models.DateTimeField("Adicionado em", auto_now_add=True)

    class Meta:
        verbose_name = "Item do Carrinho"
        verbose_name_plural = "Itens do Carrinho"
        unique_together = ('carrinho', 'produto')

    def __str__(self):
        return f"{self.quantidade}× {self.produto.nome}"

    @property
    def subtotal(self):
        return self.produto.preco * self.quantidade


class ItemComboCarrinho(models.Model):
    """Cart item for combos - SEPARATE from regular products."""
    
    carrinho = models.ForeignKey(
        Carrinho,
        on_delete=models.CASCADE,
        related_name='combos'
    )
    combo = models.ForeignKey(
        Combo,
        on_delete=models.CASCADE,
        related_name='itens_carrinho'
    )
    quantidade = models.PositiveIntegerField("Quantidade", default=1)
    criado_em = models.DateTimeField("Adicionado em", auto_now_add=True)

    class Meta:
        verbose_name = "Combo no Carrinho"
        verbose_name_plural = "Combos no Carrinho"
        unique_together = ('carrinho', 'combo')

    def __str__(self):
        return f"{self.quantidade}× {self.combo.nome}"

    @property
    def subtotal(self):
        return self.combo.preco * self.quantidade


# =============================================================================
# PEDIDO (Order)
# =============================================================================

class Pedido(models.Model):
    """Order model with Mercado Pago integration."""
    
    STATUS_CHOICES = [
        ('pendente', 'Pendente'),
        ('processando', 'Processando'),
        ('aprovado', 'Aprovado'),
        ('pago', 'Pago'),
        ('preparando', 'Preparando'),
        ('enviado', 'Enviado'),
        ('entregue', 'Entregue'),
        ('cancelado', 'Cancelado'),
        ('falhou', 'Falhou'),
        ('reembolsado', 'Reembolsado'),
        ('em_mediacao', 'Em Mediação'),
        ('estornado', 'Estornado'),
    ]
    
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='pedidos_pastita'
    )
    
    # Payment info
    payment_id = models.CharField("ID do Pagamento MP", max_length=100, blank=True, null=True)
    preference_id = models.CharField("ID da Preferência MP", max_length=100, blank=True, null=True)
    
    # Order info
    status = models.CharField("Status", max_length=20, choices=STATUS_CHOICES, default='pendente')
    total = models.DecimalField("Total (R$)", max_digits=10, decimal_places=2, default=0)
    
    # Delivery info
    endereco_entrega = models.TextField("Endereço de Entrega", blank=True)
    observacoes = models.TextField("Observações", blank=True)
    
    # Timestamps
    criado_em = models.DateTimeField("Criado em", auto_now_add=True)
    atualizado_em = models.DateTimeField("Atualizado em", auto_now=True)
    data_pagamento = models.DateTimeField("Data do Pagamento", blank=True, null=True)

    class Meta:
        verbose_name = "Pedido"
        verbose_name_plural = "Pedidos"
        ordering = ['-criado_em']

    def __str__(self):
        return f"Pedido #{self.id} - {self.usuario.email}"

    @property
    def status_display_class(self):
        """Return CSS class for status badge."""
        classes = {
            'pendente': 'bg-yellow-100 text-yellow-800',
            'processando': 'bg-blue-100 text-blue-800',
            'aprovado': 'bg-green-100 text-green-800',
            'pago': 'bg-green-100 text-green-800',
            'preparando': 'bg-purple-100 text-purple-800',
            'enviado': 'bg-indigo-100 text-indigo-800',
            'entregue': 'bg-green-100 text-green-800',
            'cancelado': 'bg-red-100 text-red-800',
            'falhou': 'bg-red-100 text-red-800',
            'reembolsado': 'bg-gray-100 text-gray-800',
        }
        return classes.get(self.status, 'bg-gray-100 text-gray-800')


class ItemPedido(models.Model):
    """Order item for regular products."""
    
    pedido = models.ForeignKey(
        Pedido,
        on_delete=models.CASCADE,
        related_name='itens'
    )
    produto = models.ForeignKey(
        Produto,
        on_delete=models.SET_NULL,
        null=True
    )
    nome_produto = models.CharField("Nome do Produto", max_length=100)
    quantidade = models.PositiveIntegerField("Quantidade", default=1)
    preco_unitario = models.DecimalField("Preço Unitário (R$)", max_digits=8, decimal_places=2)

    class Meta:
        verbose_name = "Item do Pedido"
        verbose_name_plural = "Itens do Pedido"

    def __str__(self):
        return f"{self.quantidade}× {self.nome_produto}"

    @property
    def subtotal(self):
        return self.preco_unitario * self.quantidade


class ItemComboPedido(models.Model):
    """Order item for combos."""
    
    pedido = models.ForeignKey(
        Pedido,
        on_delete=models.CASCADE,
        related_name='combos'
    )
    combo = models.ForeignKey(
        Combo,
        on_delete=models.SET_NULL,
        null=True
    )
    nome_combo = models.CharField("Nome do Combo", max_length=100)
    quantidade = models.PositiveIntegerField("Quantidade", default=1)
    preco_unitario = models.DecimalField("Preço Unitário (R$)", max_digits=8, decimal_places=2)

    class Meta:
        verbose_name = "Combo do Pedido"
        verbose_name_plural = "Combos do Pedido"

    def __str__(self):
        return f"{self.quantidade}× {self.nome_combo}"

    @property
    def subtotal(self):
        return self.preco_unitario * self.quantidade
