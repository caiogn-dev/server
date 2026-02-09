import logging
from typing import Optional, Dict, List, Any
from datetime import datetime
from .instagram_api import InstagramAPI, InstagramAPIException
from ..models import (
    InstagramMedia, InstagramMediaItem, InstagramScheduledPost,
    InstagramProductTag, InstagramInsight
)

logger = logging.getLogger(__name__)


class InstagramGraphService:
    """Serviço para gerenciamento de conteúdo via Graph API"""
    
    def __init__(self, api: InstagramAPI):
        self.api = api
    
    # ========== Posts / Media ==========
    
    def get_media_list(self, limit: int = 25, after: str = None) -> Dict:
        """Lista mídias da conta"""
        params = {
            'fields': 'id,caption,media_type,media_url,thumbnail_url,permalink,timestamp,like_count,comments_count',
            'limit': limit
        }
        if after:
            params['after'] = after
            
        return self.api.get(f"{self.api.account.instagram_business_id}/media", params)
    
    def get_media_details(self, media_id: str) -> Dict:
        """Obtém detalhes de uma mídia"""
        fields = [
            'id', 'caption', 'media_type', 'media_url', 'thumbnail_url',
            'permalink', 'timestamp', 'like_count', 'comments_count',
            'is_comment_enabled', 'comments'
        ]
        return self.api.get(media_id, {'fields': ','.join(fields)})
    
    def publish_media(self, media_type: str, media_url: str, caption: str = "", 
                      tags: List[Dict] = None) -> Dict:
        """Publica uma mídia"""
        
        # Cria o container
        container_params = {
            'media_type': media_type.upper(),
            'caption': caption,
        }
        
        if media_type.upper() == 'CAROUSEL':
            # Para carrossel, primeiro cria os itens
            children_ids = []
            for item in media_url if isinstance(media_url, list) else [media_url]:
                child_container = self.api.post(f"{self.api.account.instagram_business_id}/media", {
                    'is_carousel_item': True,
                    'image_url': item if isinstance(item, str) else item.get('url')
                })
                children_ids.append(child_container['id'])
            
            container_params['children'] = ','.join(children_ids)
        elif media_type.upper() == 'REELS':
            container_params['video_url'] = media_url
            container_params['share_to_feed'] = True
        elif media_type.upper() == 'STORY':
            container_params['image_url'] = media_url if media_type == 'IMAGE' else None
            container_params['video_url'] = media_url if media_type == 'VIDEO' else None
        else:
            if media_url.startswith('http'):
                container_params['image_url'] = media_url
            else:
                # Upload de arquivo local seria feito aqui
                raise InstagramAPIException("Upload de arquivo local não implementado")
        
        # Cria o container
        container = self.api.post(f"{self.api.account.instagram_business_id}/media", container_params)
        container_id = container['id']
        
        # Publica o container
        publish_result = self.api.post(
            f"{self.api.account.instagram_business_id}/media_publish",
            {'creation_id': container_id}
        )
        
        # Adiciona tags de produto se fornecidas
        if tags and publish_result.get('id'):
            for tag in tags:
                self.add_product_tag(publish_result['id'], tag)
        
        return publish_result
    
    def schedule_media(self, scheduled_post: InstagramScheduledPost) -> bool:
        """Agenda uma publicação"""
        # A publicação real será feita pela task celery
        scheduled_post.status = 'PENDING'
        scheduled_post.save()
        return True
    
    def delete_media(self, media_id: str) -> bool:
        """Deleta uma mídia"""
        try:
            self.api.delete(media_id)
            return True
        except InstagramAPIException:
            return False
    
    def add_product_tag(self, media_id: str, tag: Dict) -> Dict:
        """Adiciona tag de produto a uma mídia"""
        return self.api.post(f"{media_id}/product_tags", {
            'product_id': tag['product_id'],
            'position': [tag.get('x', 0.5), tag.get('y', 0.5)]
        })
    
    def get_comments(self, media_id: str) -> List[Dict]:
        """Obtém comentários de uma mídia"""
        result = self.api.get(f"{media_id}/comments", {
            'fields': 'id,text,username,timestamp,like_count,replies'
        })
        return result.get('data', [])
    
    def reply_to_comment(self, comment_id: str, message: str) -> Dict:
        """Responde a um comentário"""
        return self.api.post(f"{comment_id}/replies", {'message': message})
    
    def hide_comment(self, comment_id: str, hide: bool = True) -> bool:
        """Oculta/mostra um comentário"""
        try:
            self.api.post(comment_id, {'hide': hide})
            return True
        except InstagramAPIException:
            return False
    
    def delete_comment(self, comment_id: str) -> bool:
        """Deleta um comentário"""
        try:
            self.api.delete(comment_id)
            return True
        except InstagramAPIException:
            return False
    
    # ========== Stories ==========
    
    def publish_story(self, media_url: str, sticker: Dict = None) -> Dict:
        """Publica um story"""
        params = {
            'media_type': 'STORIES',
        }
        
        if media_url.endswith(('.mp4', '.mov')):
            params['video_url'] = media_url
        else:
            params['image_url'] = media_url
        
        # Cria container
        container = self.api.post(f"{self.api.account.instagram_business_id}/media", params)
        
        # Publica
        return self.api.post(
            f"{self.api.account.instagram_business_id}/media_publish",
            {'creation_id': container['id']}
        )
    
    def get_stories(self) -> List[Dict]:
        """Obtém stories ativos da conta"""
        result = self.api.get(f"{self.api.account.instagram_business_id}/stories", {
            'fields': 'id,caption,media_type,media_url,thumbnail_url,timestamp,expiring_at'
        })
        return result.get('data', [])
    
    # ========== Reels ==========
    
    def publish_reel(self, video_url: str, caption: str = "", share_to_feed: bool = True) -> Dict:
        """Publica um Reel"""
        # Cria container
        container = self.api.post(f"{self.api.account.instagram_business_id}/media", {
            'media_type': 'REELS',
            'video_url': video_url,
            'caption': caption,
            'share_to_feed': share_to_feed
        })
        
        # Publica
        return self.api.post(
            f"{self.api.account.instagram_business_id}/media_publish",
            {'creation_id': container['id']}
        )
    
    def get_reels(self, limit: int = 25) -> List[Dict]:
        """Obtém Reels da conta"""
        media_list = self.get_media_list(limit=limit)
        return [m for m in media_list.get('data', []) if m.get('media_type') == 'REELS']
    
    # ========== Insights / Analytics ==========
    
    def get_account_insights(self, since: datetime, until: datetime, metrics: List[str] = None) -> Dict:
        """Obtém insights da conta"""
        if not metrics:
            metrics = ['impressions', 'reach', 'profile_views', 'follower_count', 'website_clicks']
        
        params = {
            'metric': ','.join(metrics),
            'period': 'day',
            'since': since.strftime('%Y-%m-%d'),
            'until': until.strftime('%Y-%m-%d')
        }
        
        return self.api.get(f"{self.api.account.instagram_business_id}/insights", params)
    
    def get_media_insights(self, media_id: str, metrics: List[str] = None) -> Dict:
        """Obtém insights de uma mídia específica"""
        if not metrics:
            metrics = ['impressions', 'reach', 'engagement', 'saved', 'video_views']
        
        return self.api.get(f"{media_id}/insights", {
            'metric': ','.join(metrics)
        })
    
    def sync_insights(self, since: datetime, until: datetime) -> bool:
        """Sincroniza insights com o banco de dados"""
        try:
            insights_data = self.get_account_insights(since, until)
            
            for data in insights_data.get('data', []):
                metric_name = data.get('name')
                values = data.get('values', [])
                
                for value in values:
                    date = datetime.strptime(value['end_time'], '%Y-%m-%dT%H:%M:%S%z').date()
                    
                    insight, created = InstagramInsight.objects.get_or_create(
                        account=self.api.account,
                        media=None,
                        date=date,
                        defaults={metric_name: value['value']}
                    )
                    
                    if not created:
                        setattr(insight, metric_name, value['value'])
                        insight.save()
            
            return True
        except Exception as e:
            logger.error(f"Error syncing insights: {e}")
            return False
    
    # ========== Hashtag Search ==========
    
    def search_hashtag(self, hashtag: str) -> Optional[str]:
        """Busca ID de uma hashtag"""
        result = self.api.get(f"{self.api.account.instagram_business_id}/tags", {
            'q': hashtag.replace('#', '')
        })
        
        data = result.get('data', [])
        return data[0]['id'] if data else None
    
    def get_hashtag_media(self, hashtag_id: str, media_type: str = 'top', limit: int = 25) -> List[Dict]:
        """Obtém mídias de uma hashtag"""
        valid_types = ['top', 'recent']
        if media_type not in valid_types:
            media_type = 'top'
        
        result = self.api.get(f"{hashtag_id}/{media_type}", {
            'fields': 'id,caption,media_type,media_url,permalink,timestamp',
            'limit': limit
        })
        return result.get('data', [])