import uuid
from django.core.validators import RegexValidator
from django.db import models


class PostadoClient(models.Model):
    class Niche(models.TextChoices):
        RESTAURANT = 'restaurant', 'Restaurante'
        SALON = 'salon', 'Salão'
        STORE = 'store', 'Loja'

    class Tone(models.TextChoices):
        PROFESSIONAL = 'professional', 'Profissional'
        CASUAL = 'casual', 'Descontraído'
        LUXURY = 'luxury', 'Luxo'

    class Status(models.TextChoices):
        ACTIVE = 'active', 'Ativo'
        PAUSED = 'paused', 'Pausado'
        CANCELLED = 'cancelled', 'Cancelado'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business_name = models.CharField(max_length=255)
    niche = models.CharField(max_length=20, choices=Niche.choices)
    tone = models.CharField(max_length=20, choices=Tone.choices, default=Tone.CASUAL)
    brand_colors = models.JSONField(default=list)
    logo_url = models.URLField(blank=True)
    photos = models.JSONField(default=list)
    description = models.TextField(blank=True, help_text='Descrição do negócio — usado pelo LLM pra contextualizar os posts')
    products = models.JSONField(default=list, help_text='Lista de produtos/serviços destaque: ["Pizza margherita", "Corte feminino"]')
    target_audience = models.CharField(max_length=255, blank=True, help_text='Ex: "Jovens 25-35, classe A/B, zona sul"')
    instagram_handle = models.CharField(max_length=50, blank=True)
    contact_info = models.JSONField(default=dict, help_text='{"phone": "...", "address": "...", "delivery_link": "..."}')
    reference_images = models.JSONField(default=list, help_text='URLs de fotos reais do negócio')
    brand_guidelines = models.TextField(blank=True, help_text='Instruções de voz: "nunca use gírias", "sempre mencione delivery grátis"')
    email = models.EmailField(unique=True)
    whatsapp = models.CharField(max_length=20, unique=True)
    drive_folder_id = models.CharField(max_length=255, blank=True)
    mp_subscription_id = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.business_name} ({self.niche})"

    class Meta:
        ordering = ['-created_at']


class PostadoPack(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pendente'
        GENERATING = 'generating', 'Gerando'
        REVIEW = 'review', 'Em Revisão'
        APPROVED = 'approved', 'Aprovado'
        DELIVERED = 'delivered', 'Entregue'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    client = models.ForeignKey(PostadoClient, on_delete=models.CASCADE, related_name='packs')
    month = models.CharField(max_length=7, validators=[RegexValidator(r'^\d{4}-\d{2}$', 'Format must be YYYY-MM')])
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    drive_folder_url = models.URLField(blank=True)
    generated_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def total_posts(self):
        return self.posts.count()

    def __str__(self):
        return f"{self.client.business_name} — {self.month}"

    class Meta:
        ordering = ['-created_at']
        unique_together = [('client', 'month')]


class PostadoPost(models.Model):
    class PostType(models.TextChoices):
        PROMO = 'promo', 'Promoção'
        PRODUCT = 'product', 'Produto/Serviço'
        TESTIMONIAL = 'testimonial', 'Depoimento'
        ENGAGEMENT = 'engagement', 'Engajamento'
        BEHIND_SCENES = 'behind_scenes', 'Bastidor'
        DATE = 'date', 'Data Comemorativa'

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pendente'
        GENERATED = 'generated', 'Gerado'
        APPROVED = 'approved', 'Aprovado'
        REJECTED = 'rejected', 'Rejeitado'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    pack = models.ForeignKey(PostadoPack, on_delete=models.CASCADE, related_name='posts')
    post_number = models.PositiveSmallIntegerField()
    post_type = models.CharField(max_length=20, choices=PostType.choices)
    caption = models.TextField(blank=True)
    hashtags = models.TextField(blank=True)
    cta = models.CharField(max_length=255, blank=True)
    image_prompt = models.TextField(blank=True)
    feed_image_url = models.URLField(blank=True)
    stories_image_url = models.URLField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    revision_notes = models.TextField(blank=True)

    def __str__(self):
        return f"Post {self.post_number} — {self.pack}"

    class Meta:
        ordering = ['post_number']
        unique_together = [('pack', 'post_number')]
