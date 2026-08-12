from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from apps.core.models import BaseModel
from apps.nutrition.allergens import validar as validar_alergenicos


NUTRIENT_FIELDS = (
    "energy_kcal", "carbohydrates_g", "total_sugars_g", "added_sugars_g",
    "protein_g", "total_fat_g", "saturated_fat_g", "trans_fat_g",
    "fiber_g", "sodium_mg",
)


class NutritionIngredient(BaseModel):
    class Source(models.TextChoices):
        TACO = "taco", "TACO/NEPA-Unicamp"
        TBCA = "tbca", "TBCA"
        # POF/IBGE: compilação do que o brasileiro come de fato, com preparo
        # como dimensão própria e — ao contrário da TACO — açúcar de adição,
        # gordura trans e saturada medidos.
        POF = "pof", "POF/IBGE (Composição Nutricional)"
        MANUFACTURER = "manufacturer", "Fabricante"
        LAB = "lab", "Laudo laboratorial"
        MANUAL = "manual", "Manual"

    store = models.ForeignKey("stores.Store", null=True, blank=True, on_delete=models.CASCADE, related_name="nutrition_ingredients")
    canonical_name = models.CharField(max_length=255, db_index=True)
    display_name = models.CharField(max_length=255)
    category = models.CharField(max_length=80, blank=True, db_index=True)
    preparation_state = models.CharField(max_length=80, blank=True)
    default_unit = models.CharField(max_length=4, choices=(("g", "g"), ("ml", "ml")), default="g")
    density_g_ml = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)
    source = models.CharField(max_length=20, choices=Source.choices, default=Source.MANUAL)
    source_code = models.CharField(max_length=80, blank=True)
    source_edition = models.CharField(max_length=80, blank=True)
    source_reference = models.URLField(blank=True)
    source_accessed_at = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    # RDC 26/2015. `allergens` é o que o ingrediente TEM; `may_contain` é
    # contaminação cruzada do fornecedor. Listas separadas porque a norma
    # proíbe declarar como "pode conter" o que de fato está lá.
    allergens = models.JSONField(default=list, blank=True)
    may_contain = models.JSONField(default=list, blank=True)
    # Lista vazia é ambígua: pode ser "não tem alergênico" ou "ninguém olhou".
    # A etiqueta não pode afirmar "NÃO CONTÉM GLÚTEN" em cima da segunda —
    # por isso a revisão é explícita, e o import automático não a marca.
    allergens_reviewed = models.BooleanField(default=False, db_index=True)
    # RDC 136/2017. Lactose NÃO é alergênico — intolerância é deficiência de
    # enzima, não resposta imune —, então tem norma e campo próprios. É estado
    # declarado, não miligrama: nem TACO nem POF medem lactose, e o dado real
    # é o que vem impresso na embalagem.
    lactose = models.CharField(max_length=20, default="nao_revisado", db_index=True, choices=(
        ("contem", "Contém lactose"), ("baixo_teor", "Baixo teor de lactose"),
        ("zero", "Zero lactose"), ("isento", "Não contém lactose"),
        ("nao_revisado", "Não revisado"),
    ))
    # Peso do preparo PRONTO, quando o ingrediente é composto. Bobó feito com
    # 1 kg de insumos não rende 1 kg: a água evapora. Dividir pela soma do cru
    # dilui todos os valores. Nulo = sem perda declarada.
    prepared_weight_g = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True)
    energy_kcal = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    carbohydrates_g = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    total_sugars_g = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    added_sugars_g = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    protein_g = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    total_fat_g = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    saturated_fat_g = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    trans_fat_g = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    fiber_g = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    sodium_mg = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)

    class Meta:
        ordering = ("display_name",)
        constraints = [
            models.UniqueConstraint(fields=("store", "canonical_name", "preparation_state"), name="uniq_nutrition_ingredient_store_name_state"),
            models.CheckConstraint(condition=Q(density_g_ml__isnull=True) | Q(density_g_ml__gt=0), name="nutrition_density_positive"),
        ]

    def clean(self):
        errors = {field: "O valor não pode ser negativo." for field in NUTRIENT_FIELDS if getattr(self, field) is not None and getattr(self, field) < 0}
        for campo in ("allergens", "may_contain"):
            valor = getattr(self, campo) or []
            if not isinstance(valor, list):
                errors[campo] = "Informe uma lista de alergênicos."
                continue
            desconhecidos = validar_alergenicos(valor)
            if desconhecidos:
                errors[campo] = f"Alergênico não previsto na RDC 26/2015: {', '.join(desconhecidos)}."
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return self.display_name


class IngredientComponent(BaseModel):
    """Um ingrediente que é feito de outros — bobó, purê, molho da casa.

    Sem isto, "Bobó de frango" só existe como nome sem número: tabela nenhuma
    mede o bobó DA SUA cozinha, porque a proporção de leite de coco é sua. A
    saída era o lojista estimar à mão, que é a fonte de erro que este app
    inteiro tenta evitar.

    Os valores do composto são CALCULADOS e gravados nos campos dele, então
    todo o resto da cadeia — etiqueta, lupa, alergênico — continua funcionando
    sem saber que aquele ingrediente é composto.
    """
    composto = models.ForeignKey(
        "NutritionIngredient", on_delete=models.CASCADE, related_name="componentes")
    ingrediente = models.ForeignKey(
        "NutritionIngredient", on_delete=models.PROTECT, related_name="usado_em_compostos")
    quantity_g = models.DecimalField(max_digits=10, decimal_places=3)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("sort_order", "created_at")
        constraints = [
            models.UniqueConstraint(fields=("composto", "ingrediente"), name="uniq_componente_do_composto"),
            models.CheckConstraint(condition=~Q(composto=models.F("ingrediente")),
                                   name="componente_nao_e_ele_mesmo"),
        ]

    def clean(self):
        if self.quantity_g is not None and self.quantity_g <= 0:
            raise ValidationError({"quantity_g": "A quantidade deve ser maior que zero."})
        if self.composto_id and self.ingrediente_id:
            if self.composto_id == self.ingrediente_id:
                raise ValidationError({"ingrediente": "Um preparo não pode ser componente de si mesmo."})
            # Ciclo: A feito de B feito de A calcularia para sempre.
            if _depende_de(self.ingrediente, self.composto_id):
                raise ValidationError({"ingrediente":
                                       "Isso criaria um ciclo: esse preparo já usa o que você está montando."})


def _depende_de(ingrediente, alvo_id, vistos=None):
    """O `ingrediente` usa `alvo_id` em algum nível da composição?"""
    vistos = vistos or set()
    if ingrediente.id in vistos:
        return False
    vistos.add(ingrediente.id)
    for componente in IngredientComponent.objects.filter(composto=ingrediente).select_related("ingrediente"):
        if componente.ingrediente_id == alvo_id or _depende_de(componente.ingrediente, alvo_id, vistos):
            return True
    return False


class ProductRecipe(BaseModel):
    class Mode(models.TextChoices):
        CALCULATED = "calculated", "Calculado"
        MANUAL = "manual", "Manual"
        HYBRID = "hybrid", "Híbrido"
    class Status(models.TextChoices):
        DRAFT = "draft", "Rascunho"
        ESTIMATED = "estimated", "Estimado"
        REVIEWED = "reviewed", "Revisado"
        APPROVED = "approved", "Aprovado"

    product = models.OneToOneField("stores.StoreProduct", on_delete=models.CASCADE, related_name="nutrition_recipe")
    serving_size_g = models.DecimalField(max_digits=10, decimal_places=3, default=100)
    household_measure = models.CharField(max_length=100, blank=True)
    servings_per_container = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    prepared_weight_g = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True)
    calculation_mode = models.CharField(max_length=20, choices=Mode.choices, default=Mode.CALCULATED)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    source_notes = models.TextField(blank=True)
    calculation_version = models.PositiveIntegerField(default=1)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="nutrition_recipes_reviewed")
    reviewed_at = models.DateTimeField(null=True, blank=True)

    def clean(self):
        if self.serving_size_g <= 0:
            raise ValidationError({"serving_size_g": "A porção deve ser maior que zero."})


class RecipeItem(BaseModel):
    recipe = models.ForeignKey(ProductRecipe, on_delete=models.CASCADE, related_name="items")
    ingredient = models.ForeignKey(NutritionIngredient, on_delete=models.PROTECT, related_name="recipe_items")
    quantity_g = models.DecimalField(max_digits=10, decimal_places=3)
    prepared_quantity_g = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True)
    yield_factor = models.DecimalField(max_digits=8, decimal_places=4, null=True, blank=True)
    notes = models.CharField(max_length=255, blank=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("sort_order", "created_at")
        constraints = [models.UniqueConstraint(fields=("recipe", "ingredient"), name="uniq_recipe_ingredient")]

    def clean(self):
        if self.quantity_g <= 0:
            raise ValidationError({"quantity_g": "A quantidade deve ser maior que zero."})
        if self.ingredient_id and self.recipe_id:
            ingredient_store = self.ingredient.store_id
            product_store = self.recipe.product.store_id
            if ingredient_store and ingredient_store != product_store:
                raise ValidationError({"ingredient": "O ingrediente pertence a outra loja."})


class ProductNutritionProfile(BaseModel):
    class ValueSource(models.TextChoices):
        CALCULATED = "calculated", "Calculado"
        MANUAL = "manual", "Manual"
        HYBRID = "hybrid", "Híbrido"

    class PhysicalForm(models.TextChoices):
        SOLIDO = "solido", "Sólido"
        LIQUIDO = "liquido", "Líquido"

    product = models.OneToOneField("stores.StoreProduct", on_delete=models.CASCADE, related_name="nutrition_profile")
    recipe = models.OneToOneField(ProductRecipe, null=True, blank=True, on_delete=models.SET_NULL, related_name="profile")
    value_source = models.CharField(max_length=20, choices=ValueSource.choices, default=ValueSource.CALCULATED)
    # Decide o limite da lupa frontal (RDC 429/2020): líquido tem metade do
    # valor de corte do sólido. Errar aqui é imprimir selo a menos.
    physical_form = models.CharField(max_length=10, choices=PhysicalForm.choices, default=PhysicalForm.SOLIDO)
    serving_size_g = models.DecimalField(max_digits=10, decimal_places=3, default=100)
    household_measure = models.CharField(max_length=100, blank=True)
    manual_override_reason = models.TextField(blank=True)
    is_print_approved = models.BooleanField(default=False, db_index=True)
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="nutrition_profiles_approved")
    approved_at = models.DateTimeField(null=True, blank=True)
    energy_kcal = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    carbohydrates_g = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    total_sugars_g = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    added_sugars_g = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    protein_g = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    total_fat_g = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    saturated_fat_g = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    trans_fat_g = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    fiber_g = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    sodium_mg = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)


class NutritionProfileRevision(BaseModel):
    profile = models.ForeignKey(ProductNutritionProfile, on_delete=models.CASCADE, related_name="revisions")
    version = models.PositiveIntegerField()
    snapshot = models.JSONField(default=dict)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("profile", "version"), name="uniq_nutrition_profile_revision")]
