import logging
from typing import Any, Dict, Optional

from apps.stores.models import StoreProduct

from .base import HandlerResult, IntentHandler

logger = logging.getLogger(__name__)

_DRINK_KEYWORDS = ('bebida', 'drink', 'refresc', 'suco', 'refrigerante', 'beber')


def _is_drink_category(cat_name: str) -> bool:
    n = cat_name.lower()
    return any(kw in n for kw in _DRINK_KEYWORDS)


def _is_drink_product(product) -> bool:
    cat = getattr(product, 'category', None)
    if cat and _is_drink_category(cat.name):
        return True
    tags = list(product.tags or [])
    return any(kw in ' '.join(tags).lower() for kw in _DRINK_KEYWORDS)


def _build_price_list_text(store, intro: Optional[str] = None) -> str:
    """Retorna lista de preços categorizada como texto."""
    all_products = StoreProduct.objects.filter(
        store=store, is_active=True
    ).exclude(tags__contains=['ingrediente']).select_related('category').order_by(
        'category__sort_order', 'category__name', 'name'
    )
    if not all_products.exists():
        return "Cardápio em atualização. Tente novamente em breve! 🔄"
    by_cat: dict = {}
    for p in all_products:
        cat = p.category.name if p.category else 'Outros'
        if ' - ' in cat:
            cat = cat.split(' - ')[-1]
        by_cat.setdefault(cat, []).append(p)
    lines = [intro or "💰 *Tabela de preços:*", ""]
    for cat, products in by_cat.items():
        lines.append(f"*{cat}*")
        for p in products:
            lines.append(f"  • {p.name} — R$ {p.price}")
        lines.append("")
    lines.append("Para pedir, é só dizer o nome ou a quantidade. Ex: _2 rondelli de frango_ 😊")
    return "\n".join(lines)


class PriceCheckHandler(IntentHandler):
    """Handler para consulta de preços."""

    def handle(self, intent_data: Dict[str, Any]) -> HandlerResult:
        message = intent_data.get('original_message', '')
        normalized_message = self._normalize_lookup_text(message)
        if any(term in normalized_message for term in ('taxa', 'frete', 'entrega', 'delivery')):
            logger.info("[PriceCheckHandler] Respondendo taxa de entrega de forma determinística")
            return HandlerResult.text(self._build_delivery_info_text(message))
        logger.info("[PriceCheckHandler] Respondendo preço de produto de forma determinística")
        return self._legacy_handle(intent_data)

    def _legacy_handle(self, intent_data: Dict[str, Any]) -> HandlerResult:
        entities = intent_data.get('entities', {})
        product_name = entities.get('product_name')
        logger.info(f"Price check for: {product_name}")
        if not self.store:
            return HandlerResult.text("Desculpe, não encontrei informações da loja no momento. 😔")
        if product_name:
            products = StoreProduct.objects.filter(
                store=self.store, name__icontains=product_name, is_active=True
            ).exclude(tags__contains=['ingrediente'])[:5]
            if products:
                if len(products) == 1:
                    p = products[0]
                    response = f"💰 *{p.name}*\nPreço: *R$ {p.price}*\n\n"
                    if p.description:
                        response += f"{p.description}\n\n"
                    return HandlerResult.buttons(
                        body=response,
                        buttons=[
                            {'id': f'add_{p.id}_1', 'title': '🛒 Adicionar ao pedido'},
                            {'id': 'view_menu', 'title': '📋 Ver Cardápio'},
                        ],
                    )
                response = "💰 Encontrei esses produtos:\n\n"
                for p in products:
                    response += f"• *{p.name}*: R$ {p.price}\n"
                response += "\nQual você quer?"
                return HandlerResult.text(response)
            intro = f"😕 Não encontrei *{product_name}* no cardápio.\n\nMas temos:"
            return HandlerResult.text(_build_price_list_text(self.store, intro))
        return HandlerResult.text(_build_price_list_text(self.store))


class ProductMentionHandler(IntentHandler):
    """Handler quando usuário menciona produto — usa somente o catálogo real da loja."""

    def handle(self, intent_data: Dict[str, Any]) -> HandlerResult:
        logger.info("[ProductMentionHandler] Respondendo via busca determinística")
        return self._legacy_handle(intent_data)

    def _legacy_handle(self, intent_data: Dict[str, Any]) -> HandlerResult:
        message = intent_data.get('original_message', '').strip()
        logger.info(f"[ProductMentionHandler] Mensagem: {message}")
        if not self.store:
            return HandlerResult.text("Cardápio não disponível. 😔")
        all_products = StoreProduct.objects.filter(store=self.store, is_active=True).exclude(tags__contains=['ingrediente'])
        search_term = message.lower().strip()
        normalized_search = self._normalize_lookup_text(search_term)
        search_term = search_term.replace('de ', '').replace('com ', '').replace('e ', '')
        matched_products = []
        for product in all_products:
            product_name_lower = product.name.lower()
            normalized_name = self._normalize_lookup_text(product.name)
            if (
                search_term in product_name_lower
                or normalized_search == normalized_name
                or (len(normalized_search) >= 5 and normalized_search in normalized_name)
                or (len(normalized_name) >= 5 and normalized_name in normalized_search)
            ):
                matched_products.append(product)
        if matched_products:
            if len(matched_products) == 1:
                p = matched_products[0]
                try:
                    session_manager = self._get_session_manager()
                    session = session_manager.get_or_create_session()
                    session.update_context('pending_product_id', str(p.id))
                    session.update_context('pending_product_name', p.name)
                    session.update_context('pending_product_price', float(p.price))
                except Exception as exc:
                    logger.warning('[ProductMentionHandler] session context save failed: %s', exc)
                body = f"🥗 *{p.name}*\n💰 R$ {p.price}"
                if getattr(p, 'description', ''):
                    body += f"\n\n_{p.description[:120]}_"
                return HandlerResult.buttons(
                    body=body,
                    buttons=[
                        {'id': f'add_{p.id}_1', 'title': '🛒 Adicionar ao pedido'},
                        {'id': 'view_menu', 'title': '📋 Ver Cardápio'},
                    ],
                )
            product_list = "\n".join([f"{i+1}. {p.name} - R$ {p.price}" for i, p in enumerate(matched_products[:10])])
            return HandlerResult.text(
                f"🍝 *{search_term.title()}* - Temos esses:\n\n{product_list}\n\n"
                f"Qual você quer? Digite o número ou o nome! 👇"
            )
        keyword_products = []
        for product in all_products:
            product_words = product.name.lower().split()
            if product_words:
                first_word = product_words[0]
                if search_term == first_word or first_word in search_term:
                    keyword_products.append(product)
        if keyword_products:
            product_list = "\n".join([f"{i+1}. {p.name} - R$ {p.price}" for i, p in enumerate(keyword_products[:10])])
            return HandlerResult.text(
                f"🍝 *{search_term.title()}* - Temos esses:\n\n{product_list}\n\n"
                f"Qual você quer? Digite o número ou o nome! 👇"
            )
        intro = f"😕 Não encontrei *{search_term.title()}* no cardápio.\n\nMas temos:"
        return HandlerResult.text(_build_price_list_text(self.store, intro))


class MenuRequestHandler(IntentHandler):
    """Handler para solicitação de cardápio."""

    def handle(self, intent_data: Dict[str, Any]) -> HandlerResult:
        logger.info(f"[MenuRequestHandler] Store: {self.store}")
        if not self.store:
            logger.error("[MenuRequestHandler] Sem store!")
            # Multi-tenant: NUNCA hardcode de loja. Usa o menu_url do profile.
            menu_url = self.company_profile.get_menu_url() if self.company_profile else ''
            if menu_url:
                return HandlerResult.text(
                    f"🌿 Veja nosso cardápio completo aqui:\n{menu_url}"
                )
            return HandlerResult.text(
                "Desculpe, não consegui carregar o cardápio agora. "
                "Um atendente já vai te ajudar. 🙏"
            )
        all_products = StoreProduct.objects.filter(
            store=self.store, is_active=True
        ).exclude(tags__contains=['ingrediente']).select_related('category').order_by(
            'category__sort_order', 'category__name', 'name'
        )
        total_products = all_products.count()
        logger.info(f"[MenuRequestHandler] Total produtos ativos (excluindo ingredientes): {total_products}")
        if total_products == 0:
            logger.error("[MenuRequestHandler] Nenhum produto ativo encontrado!")
            return HandlerResult.text("Nenhum produto disponível no momento. 😔")
        # Separa saladas de bebidas — bebidas entram no upsell, não no menu principal
        products_by_category = {}
        has_drinks = False
        for product in all_products:
            cat_name = product.category.name if product.category else 'Outros'
            if ' - ' in cat_name:
                cat_name = cat_name.split(' - ')[-1]
            if _is_drink_category(cat_name):
                has_drinks = True
                continue  # bebidas ficam fora do menu principal
            if cat_name not in products_by_category:
                products_by_category[cat_name] = []
            products_by_category[cat_name].append(product)

        logger.info("[MenuRequestHandler] Categorias (sem bebidas): %s | has_drinks=%s",
                    list(products_by_category.keys()), has_drinks)

        drink_footer = "🥤 Bebidas disponíveis ao finalizar o pedido!" if has_drinks else None

        if not products_by_category:
            logger.error("[MenuRequestHandler] Nenhum produto (não-bebida) encontrado!")
            return HandlerResult.text("Nenhum produto disponível no momento. 😔")

        sections = []
        total_rows = 0
        max_rows = 10
        for cat_name, products in list(products_by_category.items())[:5]:
            if total_rows >= max_rows:
                break
            remaining_rows = max_rows - total_rows
            rows = [
                {'id': f'product_{p.id}', 'title': p.name[:24], 'description': f'R$ {p.price}'}
                for p in products[:remaining_rows]
            ]
            if total_rows + len(rows) > max_rows:
                rows = rows[:max_rows - total_rows]
            if rows:
                sections.append({'title': cat_name[:24], 'rows': rows})
                total_rows += len(rows)

        if not sections:
            logger.warning("[MenuRequestHandler] Sem seções, usando fallback de texto")
            fallback = list(products_by_category.values())[0] if products_by_category else []
            if fallback:
                product_list = "\n".join([f"• {p.name} - R$ {p.price}" for p in fallback[:10]])
                body = f"📋 *Cardápio - {self.store.name}*\n\n{product_list}\n\nPara pedir, é só dizer o nome e a quantidade!"
                if drink_footer:
                    body += f"\n\n{drink_footer}"
                return HandlerResult.text(body)
            return HandlerResult.text("Nenhum produto disponível no momento. 😔")

        # Encaminha pro catálogo OFICIAL do WhatsApp (carrinho nativo, cliente
        # adiciona/remove vários itens). product_list com retailer_id do nosso
        # banco não bate com os IDs do catálogo e vira mensagem não-selecionável.
        logger.info("[MenuRequestHandler] Enviando catalog_message oficial (fallback: %s seções)",
                    len(sections))
        return HandlerResult.catalog_message(
            body=f"📋 *Cardápio - {self.store.name}*\n\n"
                 "Toque em *Ver catálogo* para escolher seus produtos e montar o carrinho. 🛒",
            footer=drink_footer or "Adicione quantos itens quiser!",
            fallback_sections=sections,
        )


class ProductNotFoundHandler(IntentHandler):
    """Handler quando produto não é encontrado — evita alucinações da IA."""

    def handle(self, intent_data: Dict[str, Any]) -> HandlerResult:
        if not self.store:
            return HandlerResult.text(
                "❌ Não encontrei esse produto.\n\n"
                "Digite *cardápio* para ver o que temos disponível! 📋"
            )
        products = StoreProduct.objects.filter(
            store=self.store, is_active=True
        ).exclude(tags__contains=['ingrediente'])[:5]
        product_list = "\n".join([f"• {p.name} - R$ {p.price}" for p in products])
        return HandlerResult.text(
            f"❌ Não encontrei esse produto.\n\n"
            f"Temos disponíveis:\n{product_list}\n\n"
            f"Qual desses você quer? 😊"
        )
