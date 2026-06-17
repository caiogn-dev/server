"""
Combo selection validators - ComboSelectionValidator for validating customer selections.
"""
from typing import List, Dict, Any, Optional
from django.core.exceptions import ValidationError
from django.db.models import QuerySet
from apps.stores.models.combo import StoreCombo
from apps.stores.models.combo_group import ComboProductGroup, ComboProductGroupVariantLimit
from apps.stores.models.product import StoreProductVariant


class ComboSelectionValidator:
    """
    Validates customer's variant selections for a combo against group rules,
    stock limits, and variant constraints.

    Handles:
    - Required groups must have selections
    - Min/max selection counts per group
    - Duplicate variant prevention (when not allowed)
    - Per-variant selection limits within groups
    - Stock availability checks
    """

    def __init__(self, combo: StoreCombo):
        """
        Initialize validator for a specific combo.

        Args:
            combo: StoreCombo instance to validate against
        """
        self.combo = combo
        self.errors = []

    def validate(self, selections: Dict[str, List[str]]) -> bool:
        """
        Validate customer's variant selections against all combo rules.

        Args:
            selections: Dict mapping group_id (str UUID) → list of selected variant_ids.
                       Example: {
                           "group-id-1": ["variant-id-1", "variant-id-2"],
                           "group-id-2": ["variant-id-3"]
                       }

        Returns:
            bool: True if all validations pass, False otherwise.
                 Access self.errors list for validation error messages.

        Raises:
            No exceptions; errors are collected in self.errors list.
        """
        self.errors = []

        # Validate required groups have selections
        self._validate_required_groups(selections)

        # Validate min/max selections per group
        self._validate_selection_counts(selections)

        # Validate no duplicate variants (when not allowed)
        self._validate_duplicates(selections)

        # Validate per-variant limits and stock
        self._validate_variant_limits(selections)

        return len(self.errors) == 0

    @staticmethod
    def _group_label(group) -> str:
        """Rótulo do grupo: produto-âncora, senão title (grupo de produtos)."""
        if getattr(group, 'product_id', None):
            return group.product.name
        return group.title or 'grupo'

    def _validate_required_groups(self, selections: Dict[str, List[str]]) -> None:
        """
        Check that all required groups have at least one selection.

        Args:
            selections: Dict mapping group_id → list of variant_ids
        """
        required_groups = self.combo.groups.filter(is_required=True)

        for group in required_groups:
            group_id = str(group.id)
            if group_id not in selections or not selections[group_id]:
                self.errors.append(
                    f"Grupo '{self._group_label(group)}' é obrigatório. "
                    f"Selecione pelo menos 1 item."
                )

    def _validate_selection_counts(self, selections: Dict[str, List[str]]) -> None:
        """
        Validate that selections per group respect min_selections and max_selections.

        Args:
            selections: Dict mapping group_id → list of variant_ids
        """
        groups_map = {str(g.id): g for g in self.combo.groups.all()}

        for group_id, variant_ids in selections.items():
            if group_id not in groups_map:
                self.errors.append(f"Grupo desconhecido: {group_id}")
                continue

            group = groups_map[group_id]
            count = len(variant_ids)

            # Check minimum selections
            if count < group.min_selections:
                self.errors.append(
                    f"Grupo '{self._group_label(group)}': selecione no mínimo "
                    f"{group.min_selections} item(ns). Você selecionou {count}."
                )

            # Check maximum selections
            if count > group.max_selections:
                self.errors.append(
                    f"Grupo '{self._group_label(group)}': selecione no máximo "
                    f"{group.max_selections} item(ns). Você selecionou {count}."
                )

    def _validate_duplicates(self, selections: Dict[str, List[str]]) -> None:
        """
        Check for duplicate variants when allow_duplicate_variants is False.

        Args:
            selections: Dict mapping group_id → list of variant_ids
        """
        groups_map = {str(g.id): g for g in self.combo.groups.all()}

        for group_id, variant_ids in selections.items():
            if group_id not in groups_map:
                continue

            group = groups_map[group_id]

            # If duplicates not allowed, check for repeats
            if not group.allow_duplicate_variants:
                unique_ids = set(variant_ids)
                if len(unique_ids) != len(variant_ids):
                    duplicates = [vid for vid in variant_ids if variant_ids.count(vid) > 1]
                    duplicate_names = self._get_variant_names(list(set(duplicates)))
                    self.errors.append(
                        f"Grupo '{self._group_label(group)}': não é permitido selecionar "
                        f"variantes duplicadas. Você selecionou múltiplas vezes: "
                        f"{', '.join(duplicate_names)}."
                    )

    def _validate_variant_limits(self, selections: Dict[str, List[str]]) -> None:
        """
        Validate per-variant limits and stock availability.

        Checks:
        - Variant exists in database
        - Variant belongs to group's product
        - Variant selection count doesn't exceed variant limit
        - Variant has sufficient stock (if tracked)

        Args:
            selections: Dict mapping group_id → list of variant_ids
        """
        groups_map = {str(g.id): g for g in self.combo.groups.all()}

        for group_id, sel_ids in selections.items():
            if group_id not in groups_map:
                continue

            group = groups_map[group_id]
            label = self._group_label(group)

            variant_limits_map = {
                str(vl.variant_id): vl for vl in group.variant_limits.all()
            }
            # NOVO: opções de PRODUTO do grupo (escolha entre vários produtos)
            product_options_map = {
                str(po.product_id): po for po in group.product_options.all()
            }

            counts = {}
            for sid in sel_ids:
                counts[sid] = counts.get(sid, 0) + 1

            for sid, count in counts.items():
                # 1) É uma opção de PRODUTO do grupo?
                if sid in product_options_map:
                    po = product_options_map[sid]
                    if count > po.max_selections:
                        self.errors.append(
                            f"'{po.product.name}' em '{label}': no máximo "
                            f"{po.max_selections} seleção(ões). Você selecionou {count}."
                        )
                    continue

                # 2) Senão, valida como VARIANTE
                try:
                    variant = StoreProductVariant.objects.get(id=sid)
                    if group.product_id and variant.product_id != group.product_id:
                        self.errors.append(
                            f"Variante '{variant.name}' não pertence ao grupo '{label}'."
                        )
                        continue
                except StoreProductVariant.DoesNotExist:
                    self.errors.append(f"Opção desconhecida: {sid}")
                    continue

                if sid in variant_limits_map:
                    limit = variant_limits_map[sid]
                    if count > limit.max_selections:
                        self.errors.append(
                            f"Variante '{variant.name}' em '{label}': no máximo "
                            f"{limit.max_selections} seleção(ões) permitida(s). "
                            f"Você selecionou {count}."
                        )
                elif count > group.max_selections:
                    self.errors.append(
                        f"Variante '{variant.name}' em '{label}': no máximo "
                        f"{group.max_selections} seleção(ões) permitida(s). "
                        f"Você selecionou {count}."
                    )

                # Check stock availability
                if variant.product.track_stock and variant.stock_quantity < count:
                    self.errors.append(
                        f"Variante '{variant.name}' não possui estoque suficiente. "
                        f"Disponível: {variant.stock_quantity}, solicitado: {count}."
                    )

    def _get_variant_names(self, variant_ids: List[str]) -> List[str]:
        """
        Helper to fetch variant names from IDs.

        Args:
            variant_ids: List of variant UUIDs

        Returns:
            List of variant names
        """
        variants = StoreProductVariant.objects.filter(
            id__in=variant_ids
        ).values_list('name', flat=True)
        return list(variants)
