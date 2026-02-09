import logging
from typing import Dict, List, Any
from datetime import datetime
from .messenger_service import MessengerService, MessengerAPIException
from ..models import MessengerBroadcast, MessengerSponsoredMessage

logger = logging.getLogger(__name__)


class MessengerBroadcastService:
    """Serviço para Broadcasts e Mensagens Patrocinadas"""
    
    def __init__(self, messenger: MessengerService):
        self.messenger = messenger
    
    # ========== Broadcasts ==========
    
    def create_broadcast(self, name: str, message_type: str, 
                         content: str, template_payload: Dict = None,
                         target_audience: Dict = None) -> MessengerBroadcast:
        """Cria broadcast"""
        broadcast = MessengerBroadcast.objects.create(
            account=self.messenger.account,
            name=name,
            message_type=message_type,
            content=content,
            template_payload=template_payload or {},
            target_audience=target_audience or {}
        )
        return broadcast
    
    def send_broadcast(self, broadcast_id: str) -> bool:
        """Envia broadcast"""
        try:
            broadcast = MessengerBroadcast.objects.get(
                account=self.messenger.account,
                id=broadcast_id
            )
            
            broadcast.status = 'PROCESSING'
            broadcast.started_at = datetime.now()
            broadcast.save()
            
            # Monta a mensagem
            if broadcast.message_type == 'TEXT':
                message = {'text': broadcast.content}
            else:
                message = {
                    'attachment': {
                        'type': 'template',
                        'payload': broadcast.template_payload
                    }
                }
            
            # Envia broadcast
            # Nota: Broadcast requer permissão especial e configuração de target audience
            payload = {
                'message': message
            }
            
            if broadcast.target_audience:
                payload['messaging_type'] = 'MESSAGE_TAG'
                payload['tag'] = broadcast.target_audience.get('tag', 'NON_PROMOTIONAL_SUBSCRIPTION')
            
            # Aqui seria feito o envio real para todos os usuários
            # Na prática, isso requer uma lista de PSIDs e rate limiting
            result = self.messenger.post('me/broadcast_messages', payload)
            
            broadcast.status = 'COMPLETED'
            broadcast.completed_at = datetime.now()
            broadcast.save()
            
            return True
            
        except MessengerBroadcast.DoesNotExist:
            logger.error(f"Broadcast {broadcast_id} not found")
            return False
        except MessengerAPIException as e:
            broadcast.status = 'FAILED'
            broadcast.save()
            logger.error(f"Error sending broadcast: {e}")
            return False
    
    def get_broadcast_insights(self, broadcast_id: str) -> Dict:
        """Obtém métricas do broadcast"""
        try:
            broadcast = MessengerBroadcast.objects.get(
                account=self.messenger.account,
                id=broadcast_id
            )
            
            return {
                'id': str(broadcast.id),
                'name': broadcast.name,
                'status': broadcast.status,
                'total_recipients': broadcast.total_recipients,
                'sent_count': broadcast.sent_count,
                'delivered_count': broadcast.delivered_count,
                'read_count': broadcast.read_count,
                'started_at': broadcast.started_at.isoformat() if broadcast.started_at else None,
                'completed_at': broadcast.completed_at.isoformat() if broadcast.completed_at else None
            }
        except MessengerBroadcast.DoesNotExist:
            return {}
    
    def list_broadcasts(self, limit: int = 50) -> List[Dict]:
        """Lista broadcasts"""
        broadcasts = MessengerBroadcast.objects.filter(
            account=self.messenger.account
        ).order_by('-created_at')[:limit]
        
        return [
            {
                'id': str(b.id),
                'name': b.name,
                'status': b.status,
                'total_recipients': b.total_recipients,
                'created_at': b.created_at.isoformat()
            }
            for b in broadcasts
        ]
    
    # ========== Sponsored Messages ==========
    
    def create_sponsored_message(self, name: str, ad_account_id: str,
                                 content: str, targeting: Dict,
                                 budget: Dict, schedule: Dict = None) -> MessengerSponsoredMessage:
        """Cria mensagem patrocinada"""
        sponsored = MessengerSponsoredMessage.objects.create(
            account=self.messenger.account,
            name=name,
            ad_account_id=ad_account_id,
            content=content,
            targeting=targeting,
            daily_budget=budget.get('daily'),
            total_budget=budget.get('total'),
            start_time=schedule.get('start') if schedule else None,
            end_time=schedule.get('end') if schedule else None
        )
        return sponsored
    
    def submit_sponsored_message(self, sponsored_id: str) -> bool:
        """Submete mensagem patrocinada para aprovação"""
        try:
            sponsored = MessengerSponsoredMessage.objects.get(
                account=self.messenger.account,
                id=sponsored_id
            )
            
            # Cria campanha no Facebook Ads
            # Isso requer integração com Facebook Marketing API
            
            sponsored.status = 'PENDING_REVIEW'
            sponsored.save()
            
            return True
            
        except MessengerSponsoredMessage.DoesNotExist:
            return False
    
    def pause_sponsored_message(self, sponsored_id: str) -> bool:
        """Pausa mensagem patrocinada"""
        try:
            sponsored = MessengerSponsoredMessage.objects.get(
                account=self.messenger.account,
                id=sponsored_id,
                status='ACTIVE'
            )
            sponsored.status = 'PAUSED'
            sponsored.save()
            return True
        except MessengerSponsoredMessage.DoesNotExist:
            return False
    
    def resume_sponsored_message(self, sponsored_id: str) -> bool:
        """Retoma mensagem patrocinada"""
        try:
            sponsored = MessengerSponsoredMessage.objects.get(
                account=self.messenger.account,
                id=sponsored_id,
                status='PAUSED'
            )
            sponsored.status = 'ACTIVE'
            sponsored.save()
            return True
        except MessengerSponsoredMessage.DoesNotExist:
            return False
    
    def get_sponsored_message_insights(self, sponsored_id: str) -> Dict:
        """Obtém métricas da mensagem patrocinada"""
        try:
            sponsored = MessengerSponsoredMessage.objects.get(
                account=self.messenger.account,
                id=sponsored_id
            )
            
            return {
                'id': str(sponsored.id),
                'name': sponsored.name,
                'status': sponsored.status,
                'impressions': sponsored.impressions,
                'clicks': sponsored.clicks,
                'spent': str(sponsored.spent),
                'start_time': sponsored.start_time.isoformat() if sponsored.start_time else None,
                'end_time': sponsored.end_time.isoformat() if sponsored.end_time else None
            }
        except MessengerSponsoredMessage.DoesNotExist:
            return {}
    
    def list_sponsored_messages(self, limit: int = 50) -> List[Dict]:
        """Lista mensagens patrocinadas"""
        sponsored = MessengerSponsoredMessage.objects.filter(
            account=self.messenger.account
        ).order_by('-created_at')[:limit]
        
        return [
            {
                'id': str(s.id),
                'name': s.name,
                'status': s.status,
                'impressions': s.impressions,
                'spent': str(s.spent),
                'created_at': s.created_at.isoformat()
            }
            for s in sponsored
        ]
    
    # ========== Message Tags ==========
    
    def get_message_tags(self) -> List[Dict]:
        """Retorna tags de mensagem disponíveis"""
        # Tags válidas para envio proativo
        return [
            {'tag': 'CONFIRMED_EVENT_UPDATE', 'description': 'Atualização de evento confirmado'},
            {'tag': 'POST_PURCHASE_UPDATE', 'description': 'Atualização pós-compra'},
            {'tag': 'ACCOUNT_UPDATE', 'description': 'Atualização de conta'},
            {'tag': 'HUMAN_AGENT', 'description': 'Atendimento humano'},
            {'tag': 'NON_PROMOTIONAL_SUBSCRIPTION', 'description': 'Inscrição não promocional'},
        ]
    
    def send_tagged_message(self, psid: str, message: Dict, 
                            tag: str) -> Dict:
        """Envia mensagem com tag específica"""
        valid_tags = [t['tag'] for t in self.get_message_tags()]
        
        if tag not in valid_tags:
            raise MessengerAPIException(f"Invalid message tag: {tag}")
        
        payload = {
            'recipient': {'id': psid},
            'message': message,
            'messaging_type': 'MESSAGE_TAG',
            'tag': tag
        }
        
        return self.messenger.post('me/messages', payload)