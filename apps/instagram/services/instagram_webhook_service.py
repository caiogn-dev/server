"""
Instagram Webhook Service — processa eventos recebidos via webhook da Meta.
"""
import logging
from datetime import datetime
from typing import Dict, Any, List

from django.utils import timezone

logger = logging.getLogger(__name__)


class InstagramWebhookService:
    """
    Processa payloads de webhook do Instagram (Graph API).

    Tipos de evento suportados:
      - messages          → DM recebida
      - messaging_seen    → DM lida pelo usuário
      - comments          → Comentário em publicação
      - live_comments     → Comentário em live
      - story_insights    → Métricas de story
      - mentions          → Menção à conta
      - media             → Nova publicação
    """

    def process_webhook(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Entry-point principal: roteia cada entry/field do payload."""
        object_type = payload.get('object', '')
        entries = payload.get('entry', [])
        results: List[Dict] = []

        for entry in entries:
            page_id = entry.get('id')

            # ── Mensagens Diretas (messaging array) ──────────────────────────
            for messaging in entry.get('messaging', []):
                try:
                    result = self._process_messaging_event(page_id, messaging)
                    results.append(result)
                except Exception as e:
                    logger.error(f"Instagram messaging event error: {e}", exc_info=True)

            # ── Changes (comments, story_insights, mentions, media) ──────────
            for change in entry.get('changes', []):
                field = change.get('field')
                value = change.get('value', {})
                try:
                    result = self._process_change_event(page_id, field, value)
                    results.append(result)
                except Exception as e:
                    logger.error(f"Instagram change event [{field}] error: {e}", exc_info=True)

        return {'processed': len(results), 'results': results}

    # ──────────────────────────────────────────────────────────────────────────
    # Messaging events (DMs)
    # ──────────────────────────────────────────────────────────────────────────

    def _process_messaging_event(self, page_id: str, messaging: Dict) -> Dict:
        sender_id = messaging.get('sender', {}).get('id')
        recipient_id = messaging.get('recipient', {}).get('id')
        timestamp = messaging.get('timestamp')

        if 'message' in messaging:
            return self._handle_dm_received(page_id, sender_id, messaging['message'], timestamp)

        if 'read' in messaging:
            return self._handle_dm_read(page_id, sender_id, messaging['read'])

        if 'reaction' in messaging:
            return self._handle_dm_reaction(page_id, sender_id, messaging['reaction'])

        return {'type': 'messaging_unknown', 'sender': sender_id}

    def _handle_dm_received(self, page_id: str, sender_id: str,
                             message: Dict, timestamp: int) -> Dict:
        """Salva DM recebida e dispara notificação em tempo real."""
        from apps.instagram.models import InstagramAccount, InstagramConversation, InstagramMessage

        account = self._get_account_by_page_id(page_id)
        if not account:
            return {'type': 'dm', 'status': 'account_not_found', 'page_id': page_id}

        # Conversa
        conv, _ = InstagramConversation.objects.get_or_create(
            account=account,
            participant_id=sender_id,
            defaults={'participant_username': sender_id}
        )

        # Determina tipo e conteúdo
        message_type = 'TEXT'
        content = message.get('text', '')
        media_url = None

        attachments = message.get('attachments', [])
        if attachments:
            att = attachments[0]
            att_type = att.get('type', '').upper()
            if att_type in ('IMAGE', 'VIDEO', 'AUDIO', 'FILE'):
                message_type = att_type
                media_url = att.get('payload', {}).get('url', '')
            elif att_type == 'STICKER':
                message_type = 'STICKER'
                media_url = att.get('payload', {}).get('url', '')

        # Story reply
        if 'reply_to' in message:
            message_type = 'STORY_REPLY'
            content = message.get('text', '')

        sent_at = datetime.fromtimestamp(timestamp / 1000) if timestamp else timezone.now()

        msg = InstagramMessage.objects.create(
            conversation=conv,
            instagram_message_id=message.get('mid', ''),
            message_type=message_type,
            content=content,
            media_url=media_url,
            is_from_business=False,
            is_read=False,
            sent_at=sent_at,
        )

        conv.unread_count += 1
        conv.last_message_at = sent_at
        conv.save(update_fields=['unread_count', 'last_message_at'])

        # Real-time via channel layer
        self._push_ws_event(
            group=f'instagram_{account.id}',
            event_type='instagram_message_received',
            data={
                'message': {
                    'id': str(msg.id),
                    'type': message_type,
                    'content': content,
                    'media_url': media_url,
                    'sent_at': sent_at.isoformat(),
                },
                'conversation_id': str(conv.id),
                'account_id': str(account.id),
            }
        )

        return {'type': 'dm_received', 'message_id': str(msg.id)}

    def _handle_dm_read(self, page_id: str, sender_id: str, read_data: Dict) -> Dict:
        from apps.instagram.models import InstagramAccount, InstagramConversation, InstagramMessage

        account = self._get_account_by_page_id(page_id)
        if not account:
            return {'type': 'dm_read', 'status': 'account_not_found'}

        watermark = read_data.get('watermark', 0)
        InstagramMessage.objects.filter(
            conversation__account=account,
            conversation__participant_id=sender_id,
            is_from_business=True,
            is_read=False,
        ).update(is_read=True)

        return {'type': 'dm_read', 'sender': sender_id, 'watermark': watermark}

    def _handle_dm_reaction(self, page_id: str, sender_id: str, reaction: Dict) -> Dict:
        from apps.instagram.models import InstagramAccount, InstagramMessage

        account = self._get_account_by_page_id(page_id)
        if not account:
            return {'type': 'dm_reaction', 'status': 'account_not_found'}

        mid = reaction.get('mid')
        emoji = reaction.get('emoji') or reaction.get('reaction')
        action = reaction.get('action', 'react')  # 'react' | 'unreact'

        if mid:
            InstagramMessage.objects.filter(
                conversation__account=account,
                instagram_message_id=mid,
            ).update(reaction_type=emoji if action == 'react' else None)

        return {'type': 'dm_reaction', 'mid': mid, 'emoji': emoji, 'action': action}

    # ──────────────────────────────────────────────────────────────────────────
    # Change events (comments, insights, mentions, media, live)
    # ──────────────────────────────────────────────────────────────────────────

    def _process_change_event(self, page_id: str, field: str, value: Dict) -> Dict:
        if field == 'comments':
            return self._handle_comment(page_id, value)
        if field == 'live_comments':
            return self._handle_live_comment(page_id, value)
        if field == 'story_insights':
            return self._handle_story_insights(page_id, value)
        if field == 'mentions':
            return self._handle_mention(page_id, value)
        if field == 'media':
            return self._handle_media_change(page_id, value)

        logger.debug(f"Instagram webhook: unhandled field '{field}'")
        return {'type': f'change_{field}', 'status': 'ignored'}

    def _handle_comment(self, page_id: str, value: Dict) -> Dict:
        from apps.instagram.models import InstagramMedia

        media_id = value.get('media', {}).get('id') or value.get('media_id')
        comment_id = value.get('id')
        text = value.get('text', '')
        from_user = value.get('from', {})

        logger.info(
            f"Instagram comment on media {media_id} from {from_user.get('username')}: {text[:60]}"
        )

        account = self._get_account_by_page_id(page_id)
        if account:
            self._push_ws_event(
                group=f'instagram_{account.id}',
                event_type='instagram_comment_received',
                data={
                    'comment_id': comment_id,
                    'media_id': media_id,
                    'text': text,
                    'from': from_user,
                    'account_id': str(account.id),
                }
            )

        return {'type': 'comment', 'comment_id': comment_id, 'media_id': media_id}

    def _handle_live_comment(self, page_id: str, value: Dict) -> Dict:
        from apps.instagram.models import InstagramLive, InstagramLiveComment

        live_id = value.get('live_id') or value.get('id')
        comment_text = value.get('text', '')
        from_user = value.get('from', {})

        live = InstagramLive.objects.filter(live_id=live_id).first()
        if live:
            InstagramLiveComment.objects.create(
                live=live,
                comment_id=value.get('comment_id', ''),
                username=from_user.get('username', ''),
                text=comment_text,
            )
            live.comments_count += 1
            live.save(update_fields=['comments_count'])

        return {'type': 'live_comment', 'live_id': live_id}

    def _handle_story_insights(self, page_id: str, value: Dict) -> Dict:
        from apps.instagram.models import InstagramMedia

        media_id = value.get('media_id')
        if media_id:
            InstagramMedia.objects.filter(instagram_media_id=media_id).update(
                impressions=value.get('impressions', 0),
                reach=value.get('reach', 0),
                exits=value.get('exits', 0),
                replies=value.get('replies', 0),
            )

        return {'type': 'story_insights', 'media_id': media_id}

    def _handle_mention(self, page_id: str, value: Dict) -> Dict:
        account = self._get_account_by_page_id(page_id)
        media_id = value.get('media_id')
        comment_id = value.get('comment_id')

        logger.info(f"Instagram mention — media: {media_id}, comment: {comment_id}")

        if account:
            self._push_ws_event(
                group=f'instagram_{account.id}',
                event_type='instagram_mention_received',
                data={
                    'media_id': media_id,
                    'comment_id': comment_id,
                    'account_id': str(account.id),
                }
            )

        return {'type': 'mention', 'media_id': media_id}

    def _handle_media_change(self, page_id: str, value: Dict) -> Dict:
        """Novo post/reel publicado — atualiza status local se rastreado."""
        from apps.instagram.models import InstagramMedia

        media_id = value.get('media_id') or value.get('id')
        if media_id:
            InstagramMedia.objects.filter(instagram_media_id=media_id).update(
                status='published'
            )

        return {'type': 'media_change', 'media_id': media_id}

    # ──────────────────────────────────────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────────────────────────────────────

    def _get_account_by_page_id(self, page_id: str):
        """Busca InstagramAccount pelo facebook_page_id ou instagram_business_id."""
        from apps.instagram.models import InstagramAccount

        if not page_id:
            return None

        return (
            InstagramAccount.objects.filter(facebook_page_id=page_id, is_active=True).first()
            or InstagramAccount.objects.filter(instagram_business_id=page_id, is_active=True).first()
        )

    def _push_ws_event(self, group: str, event_type: str, data: Dict):
        """Envia evento real-time via Django Channels (fire-and-forget)."""
        try:
            from asgiref.sync import async_to_sync
            from channels.layers import get_channel_layer

            layer = get_channel_layer()
            if layer:
                async_to_sync(layer.group_send)(group, {'type': event_type, **data})
        except Exception as e:
            logger.debug(f"WebSocket push skipped ({event_type}): {e}")
