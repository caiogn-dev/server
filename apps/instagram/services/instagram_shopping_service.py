import logging
from typing import Optional, Dict, List, Any
from .instagram_api import InstagramAPI, InstagramAPIException
from ..models import InstagramCatalog, InstagramProduct, InstagramProductTag

logger = logging.getLogger(__name__)


class InstagramShoppingService:
    """Serviço para gerenciamento de Shopping e catálogos de produtos"""
    
    def __init__(self, api: InstagramAPI):
        self.api = api
    
    # ========== Catálogos ==========
    
    def list_catalogs(self) -> List[Dict]:
        """Lista catálogos de produtos"""
        # Não existe endpoint direto na Graph API para listar catálogos
        # Geralmente são gerenciados via Commerce Manager do Facebook
        # Retorna os catálogos salvos localmente
        catalogs = InstagramCatalog.objects.filter(account=self.api.account, is_active=True)
        return [
            {
                'id': str(c.id),
                'catalog_id': c.catalog_id,
                'name': c.name,
                'created_at': c.created_at.isoformat()
            }
            for c in catalogs
        ]
    
    def get_catalog(self, catalog_id: str) -> Optional[Dict]:
        """Obtém detalhes de um catálogo"""
        try:
            catalog = InstagramCatalog.objects.get(
                account=self.api.account,
                catalog_id=catalog_id
            )
            return {
                'id': str(catalog.id),
                'catalog_id': catalog.catalog_id,
                'name': catalog.name,
                'products_count': catalog.products.filter(is_active=True).count(),
                'created_at': catalog.created_at.isoformat()
            }
        except InstagramCatalog.DoesNotExist:
            return None
    
    def sync_catalog(self, catalog_id: str, name: str) -> InstagramCatalog:
        """Sincroniza um catálogo localmente"""
        catalog, created = InstagramCatalog.objects.get_or_create(
            account=self.api.account,
            catalog_id=catalog_id,
            defaults={'name': name}
        )
        
        if not created:
            catalog.name = name
            catalog.save()
        
        return catalog
    
    # ========== Produtos ==========
    
    def list_products(self, catalog_id: str = None, limit: int = 100) -> List[Dict]:
        """Lista produtos do catálogo"""
        queryset = InstagramProduct.objects.filter(
            catalog__account=self.api.account,
            is_active=True
        )
        
        if catalog_id:
            queryset = queryset.filter(catalog__catalog_id=catalog_id)
        
        products = queryset[:limit]
        
        return [
            {
                'id': str(p.id),
                'product_id': p.product_id,
                'name': p.name,
                'description': p.description,
                'price': str(p.price),
                'currency': p.currency,
                'availability': p.availability,
                'image_url': p.image_url,
                'url': p.url
            }
            for p in products
        ]
    
    def get_product(self, product_id: str) -> Optional[Dict]:
        """Obtém detalhes de um produto"""
        try:
            product = InstagramProduct.objects.get(
                catalog__account=self.api.account,
                product_id=product_id
            )
            return {
                'id': str(product.id),
                'product_id': product.product_id,
                'name': product.name,
                'description': product.description,
                'price': str(product.price),
                'currency': product.currency,
                'availability': product.availability,
                'condition': product.condition,
                'image_url': product.image_url,
                'additional_images': product.additional_image_urls,
                'url': product.url
            }
        except InstagramProduct.DoesNotExist:
            return None
    
    def create_product(self, catalog: InstagramCatalog, product_data: Dict) -> InstagramProduct:
        """Cria um novo produto no catálogo"""
        product = InstagramProduct.objects.create(
            catalog=catalog,
            product_id=product_data['product_id'],
            retailer_id=product_data.get('retailer_id'),
            name=product_data['name'],
            description=product_data.get('description', ''),
            price=product_data['price'],
            currency=product_data.get('currency', 'BRL'),
            availability=product_data.get('availability', 'in stock'),
            condition=product_data.get('condition', 'new'),
            image_url=product_data['image_url'],
            additional_image_urls=product_data.get('additional_images', []),
            url=product_data['url']
        )
        return product
    
    def update_product(self, product_id: str, product_data: Dict) -> bool:
        """Atualiza um produto existente"""
        try:
            product = InstagramProduct.objects.get(
                catalog__account=self.api.account,
                product_id=product_id
            )
            
            for field, value in product_data.items():
                if hasattr(product, field):
                    setattr(product, field, value)
            
            product.save()
            return True
        except InstagramProduct.DoesNotExist:
            return False
    
    def delete_product(self, product_id: str) -> bool:
        """Remove um produto (soft delete)"""
        try:
            product = InstagramProduct.objects.get(
                catalog__account=self.api.account,
                product_id=product_id
            )
            product.is_active = False
            product.save()
            return True
        except InstagramProduct.DoesNotExist:
            return False
    
    # ========== Product Tags ==========
    
    def add_tag_to_media(self, media_id: str, product_id: str, x: float, y: float) -> InstagramProductTag:
        """Adiciona tag de produto a uma mídia"""
        try:
            product = InstagramProduct.objects.get(
                catalog__account=self.api.account,
                product_id=product_id
            )
            
            from ..models import InstagramMedia
            media = InstagramMedia.objects.get(id=media_id)
            
            tag = InstagramProductTag.objects.create(
                media=media,
                product_id=product_id,
                product_name=product.name,
                position_x=x,
                position_y=y
            )
            
            media.has_product_tags = True
            media.save()
            
            return tag
        except (InstagramProduct.DoesNotExist, InstagramMedia.DoesNotExist) as e:
            logger.error(f"Error adding product tag: {e}")
            raise InstagramAPIException(str(e))
    
    def remove_tag_from_media(self, tag_id: str) -> bool:
        """Remove tag de produto de uma mídia"""
        try:
            from ..models import InstagramProductTag
            tag = InstagramProductTag.objects.get(
                media__account=self.api.account,
                id=tag_id
            )
            tag.delete()
            
            # Verifica se ainda há tags
            media = tag.media
            if not media.product_tags.exists():
                media.has_product_tags = False
                media.save()
            
            return True
        except InstagramProductTag.DoesNotExist:
            return False
    
    def get_media_tags(self, media_id: str) -> List[Dict]:
        """Obtém tags de produto de uma mídia"""
        from ..models import InstagramProductTag
        
        tags = InstagramProductTag.objects.filter(media__id=media_id)
        return [
            {
                'id': str(tag.id),
                'product_id': tag.product_id,
                'product_name': tag.product_name,
                'position': {'x': tag.position_x, 'y': tag.position_y}
            }
            for tag in tags
        ]
    
    # ========== Instagram Shop ==========
    
    def enable_shopping(self) -> bool:
        """Habilita shopping na conta (requer aprovação do Instagram)"""
        # Não existe endpoint direto - requer configuração no Commerce Manager
        # e aprovação do Instagram
        logger.info("Shopping habilitação requer configuração manual no Commerce Manager")
        return True
    
    def get_shopping_settings(self) -> Dict:
        """Obtém configurações de shopping da conta"""
        try:
            result = self.api.get(self.api.account.instagram_business_id, {
                'fields': 'shopping_product_tag_eligibility,shopping_review_status'
            })
            return {
                'eligible': result.get('shopping_product_tag_eligibility', False),
                'review_status': result.get('shopping_review_status', 'not_reviewed')
            }
        except InstagramAPIException as e:
            logger.error(f"Error getting shopping settings: {e}")
            return {'eligible': False, 'review_status': 'error'}