from django.db import transaction
from django.utils import timezone
from rest_framework import serializers
from django.urls import reverse

from apps.nutrition.models import NutritionIngredient, ProductRecipe, RecipeItem, ProductNutritionProfile, NUTRIENT_FIELDS
from apps.nutrition.services.calculator import calculate_recipe


class NutritionIngredientSerializer(serializers.ModelSerializer):
    class Meta:
        model = NutritionIngredient
        fields = "__all__"
        read_only_fields = ("id", "created_at", "updated_at")

    def validate_store(self, store):
        user = self.context["request"].user
        if store is None and not user.is_superuser:
            raise serializers.ValidationError("Somente administradores podem criar ingredientes globais.")
        if store and not (user.is_superuser or store.owner_id == user.id or store.staff.filter(id=user.id).exists()):
            raise serializers.ValidationError("Loja não autorizada.")
        return store

    def validate(self, attrs):
        if self.instance and self.instance.store_id is None and not self.context["request"].user.is_superuser:
            raise serializers.ValidationError("Ingredientes oficiais globais são somente leitura.")
        instance = NutritionIngredient(**{**({k: getattr(self.instance, k) for k in NUTRIENT_FIELDS} if self.instance else {}), **attrs})
        instance.clean()
        return attrs


class RecipeItemSerializer(serializers.ModelSerializer):
    ingredient_name = serializers.CharField(source="ingredient.display_name", read_only=True)
    class Meta:
        model = RecipeItem
        fields = ("id", "ingredient", "ingredient_name", "quantity_g", "prepared_quantity_g", "yield_factor", "notes", "sort_order")


class ProductRecipeSerializer(serializers.ModelSerializer):
    items = RecipeItemSerializer(many=True, required=False)
    calculation = serializers.SerializerMethodField()
    product_name = serializers.CharField(source="product.name", read_only=True)

    class Meta:
        model = ProductRecipe
        fields = "__all__"
        read_only_fields = ("id", "created_at", "updated_at", "reviewed_by", "reviewed_at")

    def get_calculation(self, obj):
        return calculate_recipe(obj)

    def validate_product(self, product):
        user = self.context["request"].user
        store = product.store
        if not (user.is_superuser or store.owner_id == user.id or store.staff.filter(id=user.id).exists()):
            raise serializers.ValidationError("Produto não autorizado.")
        return product

    def _save_items(self, recipe, items):
        recipe.items.all().delete()
        for item in items:
            ingredient = item["ingredient"]
            if ingredient.store_id and ingredient.store_id != recipe.product.store_id:
                raise serializers.ValidationError({"items": "Ingrediente pertence a outra loja."})
            RecipeItem.objects.create(recipe=recipe, **item)

    def _sync_profile(self, recipe):
        calculation = calculate_recipe(recipe)
        profile, _ = ProductNutritionProfile.objects.get_or_create(
            product=recipe.product,
            defaults={"recipe": recipe, "serving_size_g": recipe.serving_size_g, "household_measure": recipe.household_measure},
        )
        profile.recipe = recipe
        profile.serving_size_g = recipe.serving_size_g
        profile.household_measure = recipe.household_measure
        if profile.value_source == ProductNutritionProfile.ValueSource.CALCULATED:
            for field, value in calculation["per_100g"].items():
                setattr(profile, field, value)
        elif profile.value_source == ProductNutritionProfile.ValueSource.HYBRID:
            for field, value in calculation["per_100g"].items():
                if getattr(profile, field) is None:
                    setattr(profile, field, value)
        profile.is_print_approved = recipe.status == ProductRecipe.Status.APPROVED and not calculation["missing_nutrients"]
        profile.save()

    @transaction.atomic
    def create(self, validated_data):
        items = validated_data.pop("items", [])
        recipe = super().create(validated_data)
        self._save_items(recipe, items)
        self._sync_profile(recipe)
        return recipe

    @transaction.atomic
    def update(self, instance, validated_data):
        items = validated_data.pop("items", None)
        recipe = super().update(instance, validated_data)
        if items is not None:
            self._save_items(recipe, items)
        self._sync_profile(recipe)
        return recipe


class ProductNutritionProfileSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    calculation = serializers.SerializerMethodField()
    public_url = serializers.SerializerMethodField()
    class Meta:
        model = ProductNutritionProfile
        fields = "__all__"
        read_only_fields = ("id", "created_at", "updated_at", "approved_by", "approved_at")

    def validate_product(self, product):
        user = self.context["request"].user
        store = product.store
        if not (user.is_superuser or store.owner_id == user.id or store.staff.filter(id=user.id).exists()):
            raise serializers.ValidationError("Produto não autorizado.")
        return product

    def get_calculation(self, obj):
        return calculate_recipe(obj.recipe) if obj.recipe_id else None

    def update(self, instance, validated_data):
        """Carimba quem aprovou e quando.

        Aprovação sem autor e sem data não é aprovação — é um booleano. Quando
        a etiqueta impressa for questionada, é este par que responde quem
        assumiu a responsabilidade pelo que foi declarado.
        """
        aprovando = validated_data.get("is_print_approved")
        if aprovando is not None and aprovando != instance.is_print_approved:
            usuario = getattr(self.context.get("request"), "user", None)
            if aprovando:
                validated_data["approved_by"] = usuario if usuario and usuario.is_authenticated else None
                validated_data["approved_at"] = timezone.now()
            else:
                # Revogar limpa o carimbo: manter o nome antigo daria a
                # entender que aquela pessoa aprovou o estado atual.
                validated_data["approved_by"] = None
                validated_data["approved_at"] = None
        return super().update(instance, validated_data)

    def get_public_url(self, obj):
        path = reverse("public-nutrition-label", kwargs={"product_id": obj.product_id})
        request = self.context.get("request")
        return request.build_absolute_uri(path) if request else path
