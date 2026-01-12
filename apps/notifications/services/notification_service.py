"""
Notification service for creating and managing notifications.
"""
import logging
from typing import Optional, List, Dict, Any
from django.contrib.auth import get_user_model
from django.db.models import QuerySet
from django.utils import timezone
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from ..models import Notification, NotificationPreference, PushSubscription

logger = logging.getLogger(__name__)
User = get_user_model()


class NotificationService:
    """Service for notification operations."""
    
    def create_notification(
        self,
        title: str,
        message: str,
        notification_type: str = Notification.NotificationType.SYSTEM,
        priority: str = Notification.Priority.NORMAL,
        user: Optional[User] = None,
        data: Optional[Dict[str, Any]] = None,
        related_object_type: str = '',
        related_object_id: str = '',
        send_push: bool = True,
        send_realtime: bool = True,
    ) -> Notification:
        """Create a new notification."""
        notification = Notification.objects.create(
            user=user,
            notification_type=notification_type,
            priority=priority,
            title=title,
            message=message,
            data=data or {},
            related_object_type=related_object_type,
            related_object_id=related_object_id,
        )
        
        if send_realtime and user:
            self._send_realtime_notification(notification)
        
        if send_push and user:
            self._send_push_notification(notification)
        
        return notification
    
    def create_broadcast_notification(
        self,
        title: str,
        message: str,
        notification_type: str = Notification.NotificationType.SYSTEM,
        priority: str = Notification.Priority.NORMAL,
        data: Optional[Dict[str, Any]] = None,
        user_ids: Optional[List[int]] = None,
    ) -> List[Notification]:
        """Create notifications for multiple users."""
        if user_ids:
            users = User.objects.filter(id__in=user_ids)
        else:
            users = User.objects.filter(is_active=True)
        
        notifications = []
        for user in users:
            notification = self.create_notification(
                title=title,
                message=message,
                notification_type=notification_type,
                priority=priority,
                user=user,
                data=data,
            )
            notifications.append(notification)
        
        return notifications
    
    def get_user_notifications(
        self,
        user: User,
        unread_only: bool = False,
        notification_type: Optional[str] = None,
        limit: int = 50,
    ) -> QuerySet:
        """Get notifications for a user."""
        queryset = Notification.objects.filter(user=user)
        
        if unread_only:
            queryset = queryset.filter(is_read=False)
        
        if notification_type:
            queryset = queryset.filter(notification_type=notification_type)
        
        return queryset[:limit]
    
    def get_unread_count(self, user: User) -> int:
        """Get count of unread notifications."""
        return Notification.objects.filter(user=user, is_read=False).count()
    
    def mark_as_read(self, notification_id: str, user: User) -> Optional[Notification]:
        """Mark a notification as read."""
        try:
            notification = Notification.objects.get(id=notification_id, user=user)
            notification.mark_as_read()
            return notification
        except Notification.DoesNotExist:
            return None
    
    def mark_all_as_read(self, user: User) -> int:
        """Mark all notifications as read for a user."""
        count = Notification.objects.filter(user=user, is_read=False).update(
            is_read=True,
            read_at=timezone.now()
        )
        return count
    
    def delete_notification(self, notification_id: str, user: User) -> bool:
        """Delete a notification."""
        try:
            notification = Notification.objects.get(id=notification_id, user=user)
            notification.delete()
            return True
        except Notification.DoesNotExist:
            return False
    
    def delete_old_notifications(self, days: int = 30) -> int:
        """Delete notifications older than specified days."""
        cutoff_date = timezone.now() - timezone.timedelta(days=days)
        count, _ = Notification.objects.filter(created_at__lt=cutoff_date).delete()
        return count
    
    def get_or_create_preferences(self, user: User) -> NotificationPreference:
        """Get or create notification preferences for a user."""
        preferences, _ = NotificationPreference.objects.get_or_create(user=user)
        return preferences
    
    def update_preferences(
        self,
        user: User,
        **kwargs
    ) -> NotificationPreference:
        """Update notification preferences."""
        preferences = self.get_or_create_preferences(user)
        
        for key, value in kwargs.items():
            if hasattr(preferences, key):
                setattr(preferences, key, value)
        
        preferences.save()
        return preferences
    
    def register_push_subscription(
        self,
        user: User,
        endpoint: str,
        p256dh_key: str,
        auth_key: str,
        user_agent: str = '',
    ) -> PushSubscription:
        """Register a push subscription."""
        subscription, created = PushSubscription.objects.update_or_create(
            user=user,
            endpoint=endpoint,
            defaults={
                'p256dh_key': p256dh_key,
                'auth_key': auth_key,
                'user_agent': user_agent,
                'is_active': True,
            }
        )
        return subscription
    
    def unregister_push_subscription(self, user: User, endpoint: str) -> bool:
        """Unregister a push subscription."""
        try:
            subscription = PushSubscription.objects.get(user=user, endpoint=endpoint)
            subscription.is_active = False
            subscription.save()
            return True
        except PushSubscription.DoesNotExist:
            return False
    
    def _send_realtime_notification(self, notification: Notification):
        """Send notification via WebSocket."""
        try:
            channel_layer = get_channel_layer()
            if channel_layer and notification.user:
                async_to_sync(channel_layer.group_send)(
                    f"user_{notification.user.id}",
                    {
                        "type": "notification.message",
                        "notification": {
                            "id": str(notification.id),
                            "type": notification.notification_type,
                            "notification_type": notification.notification_type,
                            "priority": notification.priority,
                            "title": notification.title,
                            "message": notification.message,
                            "data": notification.data,
                            "created_at": notification.created_at.isoformat(),
                        }
                    }
                )
                notification.is_sent = True
                notification.sent_at = timezone.now()
                notification.save(update_fields=['is_sent', 'sent_at'])
        except Exception as e:
            logger.error(f"Error sending realtime notification: {e}")
    
    def _send_push_notification(self, notification: Notification):
        """Send push notification to user's devices."""
        if not notification.user:
            return
        
        try:
            preferences = self.get_or_create_preferences(notification.user)
            
            if not preferences.push_enabled:
                return
            
            type_enabled = {
                Notification.NotificationType.MESSAGE: preferences.push_messages,
                Notification.NotificationType.ORDER: preferences.push_orders,
                Notification.NotificationType.PAYMENT: preferences.push_payments,
                Notification.NotificationType.SYSTEM: preferences.push_system,
            }
            
            if not type_enabled.get(notification.notification_type, True):
                return
            
            subscriptions = PushSubscription.objects.filter(
                user=notification.user,
                is_active=True
            )
            
            for subscription in subscriptions:
                self._send_web_push(subscription, notification)
            
            notification.push_sent = True
            notification.push_sent_at = timezone.now()
            notification.save(update_fields=['push_sent', 'push_sent_at'])
            
        except Exception as e:
            logger.error(f"Error sending push notification: {e}")
    
    def _send_web_push(self, subscription: PushSubscription, notification: Notification):
        """Send web push notification."""
        # Implementation would use pywebpush library
        # For now, just log the attempt
        logger.info(f"Would send push to {subscription.endpoint}: {notification.title}")
    
    # Convenience methods for specific notification types
    def notify_new_message(
        self,
        user: User,
        from_number: str,
        message_preview: str,
        conversation_id: str,
    ) -> Notification:
        """Create notification for new message."""
        return self.create_notification(
            title=f"Nova mensagem de {from_number}",
            message=message_preview[:100],
            notification_type=Notification.NotificationType.MESSAGE,
            priority=Notification.Priority.HIGH,
            user=user,
            data={
                'from_number': from_number,
                'conversation_id': conversation_id,
            },
            related_object_type='conversation',
            related_object_id=conversation_id,
        )
    
    def notify_order_update(
        self,
        user: User,
        order_number: str,
        old_status: str,
        new_status: str,
        order_id: str,
    ) -> Notification:
        """Create notification for order status update."""
        return self.create_notification(
            title=f"Pedido #{order_number} atualizado",
            message=f"Status alterado de {old_status} para {new_status}",
            notification_type=Notification.NotificationType.ORDER,
            priority=Notification.Priority.NORMAL,
            user=user,
            data={
                'order_number': order_number,
                'old_status': old_status,
                'new_status': new_status,
                'order_id': order_id,
            },
            related_object_type='order',
            related_object_id=order_id,
        )
    
    def notify_payment_received(
        self,
        user: User,
        order_number: str,
        amount: float,
        payment_id: str,
    ) -> Notification:
        """Create notification for payment received."""
        return self.create_notification(
            title=f"Pagamento recebido - Pedido #{order_number}",
            message=f"Pagamento de R$ {amount:.2f} confirmado",
            notification_type=Notification.NotificationType.PAYMENT,
            priority=Notification.Priority.HIGH,
            user=user,
            data={
                'order_number': order_number,
                'amount': amount,
                'payment_id': payment_id,
            },
            related_object_type='payment',
            related_object_id=payment_id,
        )
