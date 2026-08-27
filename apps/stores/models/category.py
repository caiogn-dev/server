"""
Store category model.
"""
import uuid
from django.core.validators import MinValueValidator
from django.db import models
from apps.core.utils import build_absolute_media_url
from .base import Store


class StoreCategory(models.Model):
    """Product categories specific to a store."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    store = models.ForeignKey(
        Store,
        on_delete=models.CASCADE,
        related_name='categories'
    )

    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=100)
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to='stores/categories/', blank=True, null=True)
    image_url = models.URLField(blank=True)

    parent = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='children'
    )

    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    # Categoria interna do Salad Builder (base, complemento, proteína, molhos):
    # usada só dentro do componente de montagem, escondida do cardápio normal.
    is_builder_group = models.BooleanField(
        default=False,
        help_text="Categoria usada apenas no Salad Builder; não aparece como seção do cardápio.",
    )

    # ─── Configuração do montador ("monte o seu") ───
    # Estes campos existem porque o storefront cravava no código os quatro
    # passos da Cê Saladas — base/proteína/complemento/molho, com rótulo,
    # máximo e obrigatoriedade fixos. Numa plataforma multi-loja isso é o
    # domínio de UMA loja dentro do produto de todas: quem monta pizza, açaí
    # ou marmita precisa dos próprios passos. Quem decide é a loja, então a
    # configuração mora na categoria.
    builder_step_order = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text=(
            "Posição desta categoria como passo do montador (0 = primeiro). "
            "Vazio significa que a categoria não participa do montador. "
            "É independente de `sort_order`, que ordena a vitrine."
        ),
    )
    builder_max_selections = models.PositiveSmallIntegerField(
        default=1,
        validators=[MinValueValidator(1)],
        help_text="Quantos itens o cliente pode escolher neste passo.",
    )
    builder_required = models.BooleanField(
        default=False,
        help_text="O cliente precisa escolher algo aqui para fechar a montagem.",
    )
    builder_included = models.BooleanField(
        default=False,
        help_text="Itens deste passo não são cobrados à parte (já inclusos no preço base).",
    )
    builder_expand_variants = models.BooleanField(
        default=False,
        help_text=(
            "Cada variante do produto vira uma opção própria — é assim que "
            "um único produto 'Molho' oferece seus 4 sabores como escolhas."
        ),
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'store_categories'
        verbose_name = 'Store Category'
        verbose_name_plural = 'Store Categories'
        unique_together = ['store', 'slug']
        ordering = ['store', 'sort_order', 'name']
        constraints = [
            # Dois passos na mesma posição deixariam a ordem da montagem a
            # cargo do acaso. Vazio pode repetir: NULL nunca conflita.
            models.UniqueConstraint(
                fields=['store', 'builder_step_order'],
                name='passo_unico_por_loja_no_montador',
            ),
        ]

    @property
    def is_builder_step(self):
        """A categoria participa do montador?"""
        return self.builder_step_order is not None

    def __str__(self):
        return f"{self.store.name} - {self.name}"

    def get_image_url(self):
        if self.image:
            return build_absolute_media_url(self.image.url)
        return build_absolute_media_url(self.image_url or '')
