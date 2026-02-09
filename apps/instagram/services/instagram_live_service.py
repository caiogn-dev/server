import logging
from typing import Optional, Dict, List, Any
from datetime import datetime
from .instagram_api import InstagramAPI, InstagramAPIException
from ..models import InstagramLive, InstagramLiveComment

logger = logging.getLogger(__name__)


class InstagramLiveService:
    """Serviço para gerenciamento de Lives do Instagram"""
    
    def __init__(self, api: InstagramAPI):
        self.api = api
    
    # ========== Lives ==========
    
    def create_live(self, title: str = "", description: str = "", scheduled_at: datetime = None) -> InstagramLive:
        """Cria uma nova live (ou agenda)"""
        live = InstagramLive.objects.create(
            account=self.api.account,
            title=title or f"Live - {datetime.now().strftime('%d/%m/%Y %H:%M')}",
            description=description,
            scheduled_at=scheduled_at,
            status='SCHEDULED' if scheduled_at else 'LIVE'
        )
        return live
    
    def start_live(self, live_id: str) -> Dict:
        """Inicia uma transmissão ao vivo"""
        try:
            live = InstagramLive.objects.get(
                account=self.api.account,
                id=live_id
            )
            
            # Obter stream key e URL (simulado - Graph API não fornece diretamente)
            # Na prática, isso requer integração com obs/encoder ou API de lives do Instagram
            stream_info = self._get_stream_info()
            
            live.stream_url = stream_info.get('stream_url')
            live.stream_key = stream_info.get('stream_key')
            live.status = 'LIVE'
            live.started_at = datetime.now()
            live.save()
            
            return {
                'success': True,
                'stream_url': live.stream_url,
                'stream_key': live.stream_key
            }
            
        except InstagramLive.DoesNotExist:
            raise InstagramAPIException("Live não encontrada")
        except Exception as e:
            logger.error(f"Error starting live: {e}")
            raise InstagramAPIException(str(e))
    
    def end_live(self, live_id: str) -> bool:
        """Finaliza uma live"""
        try:
            live = InstagramLive.objects.get(
                account=self.api.account,
                id=live_id
            )
            
            live.status = 'ENDED'
            live.ended_at = datetime.now()
            live.save()
            
            return True
            
        except InstagramLive.DoesNotExist:
            return False
    
    def cancel_live(self, live_id: str) -> bool:
        """Cancela uma live agendada"""
        try:
            live = InstagramLive.objects.get(
                account=self.api.account,
                id=live_id,
                status='SCHEDULED'
            )
            
            live.status = 'CANCELLED'
            live.save()
            
            return True
            
        except InstagramLive.DoesNotExist:
            return False
    
    def get_live(self, live_id: str) -> Optional[Dict]:
        """Obtém detalhes de uma live"""
        try:
            live = InstagramLive.objects.get(
                account=self.api.account,
                id=live_id
            )
            
            return {
                'id': str(live.id),
                'title': live.title,
                'description': live.description,
                'status': live.status,
                'viewers_count': live.viewers_count,
                'max_viewers': live.max_viewers,
                'comments_count': live.comments_count,
                'stream_url': live.stream_url,
                'scheduled_at': live.scheduled_at.isoformat() if live.scheduled_at else None,
                'started_at': live.started_at.isoformat() if live.started_at else None,
                'ended_at': live.ended_at.isoformat() if live.ended_at else None
            }
            
        except InstagramLive.DoesNotExist:
            return None
    
    def list_lives(self, status: str = None, limit: int = 50) -> List[Dict]:
        """Lista lives da conta"""
        queryset = InstagramLive.objects.filter(account=self.api.account)
        
        if status:
            queryset = queryset.filter(status=status)
        
        lives = queryset.order_by('-created_at')[:limit]
        
        return [
            {
                'id': str(live.id),
                'title': live.title,
                'status': live.status,
                'viewers_count': live.viewers_count,
                'comments_count': live.comments_count,
                'created_at': live.created_at.isoformat()
            }
            for live in lives
        ]
    
    # ========== Comentários de Live ==========
    
    def get_comments(self, live_id: str, limit: int = 100) -> List[Dict]:
        """Obtém comentários de uma live"""
        comments = InstagramLiveComment.objects.filter(
            live__account=self.api.account,
            live__id=live_id
        ).order_by('-created_at')[:limit]
        
        return [
            {
                'id': str(comment.id),
                'username': comment.username,
                'text': comment.text,
                'created_at': comment.created_at.isoformat()
            }
            for comment in comments
        ]
    
    def add_comment(self, live_id: str, username: str, text: str, created_at: datetime = None) -> InstagramLiveComment:
        """Adiciona um comentário (via webhook)"""
        live = InstagramLive.objects.get(
            account=self.api.account,
            id=live_id
        )
        
        comment = InstagramLiveComment.objects.create(
            live=live,
            comment_id=f"live_{live_id}_{datetime.now().timestamp()}",
            username=username,
            text=text,
            created_at=created_at or datetime.now()
        )
        
        # Atualiza contador
        live.comments_count = live.comments.count()
        live.save()
        
        return comment
    
    def delete_comment(self, comment_id: str) -> bool:
        """Remove um comentário da live"""
        try:
            comment = InstagramLiveComment.objects.get(
                live__account=self.api.account,
                id=comment_id
            )
            comment.delete()
            return True
        except InstagramLiveComment.DoesNotExist:
            return False
    
    # ========== Métricas ==========
    
    def update_viewers_count(self, live_id: str, count: int) -> bool:
        """Atualiza contador de espectadores"""
        try:
            live = InstagramLive.objects.get(
                account=self.api.account,
                id=live_id
            )
            
            live.viewers_count = count
            if count > live.max_viewers:
                live.max_viewers = count
            live.save()
            
            return True
        except InstagramLive.DoesNotExist:
            return False
    
    def _get_stream_info(self) -> Dict:
        """Obtém informações de stream (simulado)"""
        # Na implementação real, isso integraria com encoder/API de lives
        # Por enquanto, retorna estrutura esperada
        return {
            'stream_url': f"rtmps://live-upload.instagram.com:443/rtmp/",
            'stream_key': f"{self.api.account.instagram_business_id}_{datetime.now().timestamp()}"
        }