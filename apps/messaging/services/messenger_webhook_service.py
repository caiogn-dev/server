"""
Messenger Webhook Service — processa eventos recebidos via webhook da Meta.
"""
import logging
from datetime import datetime
from typing import Dict, Any, List

from django.utils import timezone

logger = logging.getLogger(__name__)


class MessengerWebhookService:
    """
    Processa payloads de webhook do Facebook Messenger.

    Tipos de evento suportados:
      - messages              → Mensagem recebida
      - message_deliveries    → Confirmação de entrega
      - message_reads         → Confirmação de leitura
      - messaging_postbacks   → Clique em botão/postback
      - messaging_optins      → Opt-in do usuário
      - messaging_referrals   → Referral (link patrocinado)
    """

    def process_webhook(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Entry-point: roteia cada entry do payload."""
        entries = payload.get('entry', [])
        results: List[Dict] = []

        for entry in entries:
            page_id = entry.get('id')

            for messaging in entry.get('messaging', []):
                try:
                    result = self._process_messaging_event(page_id, messaging)
                    results.append(result)
                except Exception as e:
                    logger.error(f"Messenger event error: {e}", exc_info=True)

        return {'processed': len(results), 'results': results}

    # ──────────────────────────────────────────────────────────────────────────
    # Router principal
    # ──────────────────────────────────────────────────────────────────────────

    def _process_messaging_event(self, page_id: str, messaging: Dict) -> Dict:
        sender_psid = messaging.get('sender', {}).get('id')
        timestamp = messaging.get('timestamp')

        if 'message' in messaging:
            return self._handle_message(page_id, sender_psid, messaging['message'], timestamp)

        if 'delivery' in messaging:
            return self._handle_delivery(page_id, sender_psid, messaging['delivery'])

        if 'read' in messaging:
            return self._handle_read(page_id, sender_psid, messaging['read'])

        if 'postback' in messaging:
            return self._handle_postback(page_id, sender_psid, messaging['postback'], timestamp)

        if 'optin' in messaging:
            return self._handle_optin(page_id, sender_psid, messaging['optin'])

        if 'referral' in messaging:
            return self._handle_referral(page_id, sender_psid, messaging['referral'])

        return {'type': 'unknown', 'sender': sender_psid}

    # ──────────────────────────────────────────────────────────────────────────
    # Handlers
    # ──────────────────────────────────────────────────────────────────────────

    def _handle_message(self, page_id: str, sender_psid: str,
                        message: Dict, timestamp: int) -> Dict:
        """Salva mensagem recebida e dispara evento WebSocket."""
        from apps.messaging.models import MessengerAccount, MessengerConversation, MessengerMessage

        account = self._get_account(page_id)
        if not account:
            return {'type': 'message', 'status': 'account_not_found', 'page_id': page_id}

        # Ignora eco (mensagens enviadas pela própria página)
        if message.get('is_echo'):
            return {'type': 'message_echo', 'status': 'ignored'}

        conv, _ = MessengerConversation.objects.get_or_create(
            account=account,
            psid=sender_psid,
        )

        # Determina tipo e conteúdo
        message_type = 'TEXT'
        content = message.get('text', '')
        attachment_url = None

        attachments = message.get('attachments', [])
        if attachments:
            att = attachments[0]
            att_type = att.get('type', '').upper()
            type_map = {'IMAGE': 'IMAGE', 'VIDEO': 'VIDEO', 'AUDIO': 'AUDIO',
                        'FILE': 'FILE', 'STICKER': 'STICKER', 'FALLBACK': 'TEXT'}
            message_type = type_map.get(att_type, 'TEXT')
            attachment_url = att.get('payload', {}).get('url', '')

        quick_reply = message.get('quick_reply', {})
        if quick_reply:
            message_type = 'QUICK_REPLY'
            content = quick_reply.get('payload', content)

        sent_at = datetime.fromtimestamp(timestamp / 1000) if timestamp else timezone.now()

        msg = MessengerMessage.objects.create(
            conversation=conv,
            messenger_message_id=message.get('mid', ''),
            message_type=message_type,
            content=content,
            attachment_url=attachment_url,
            is_from_page=False,
            is_read=False,
            sent_at=sent_at,
        )

        conv.unread_count += 1
        conv.last_message_at = sent_at
        conv.save(update_fields=['unread_count', 'last_message_at'])

        # Real-time
        self._push_ws_event(
            group=f'messenger_{account.id}',
            event_type='messenger_message_received',
            data={
                'message': {
                    'id': str(msg.id),
                    'type': message_type,
                    'content': content,
                    'attachment_url': attachment_url,
                    'sent_at': sent_at.isoformat(),
                },
                'conversation_id': str(conv.id),
                'account_id': str(account.id),
            }
        )

        return {'type': 'message_received', 'message_id': str(msg.id)}

    def _handle_delivery(self, page_id: str, sender_psid: str, delivery: Dict) -> Dict:
        """Marca mensagens como entregues."""
        from apps.messaging.models import MessengerMessage

        account = self._get_account(page_id)
        if not account:
            return {'type': 'delivery', 'status': 'account_not_found'}

        watermark = delivery.get('watermark', 0)
        mids = delivery.get('mids', [])

        if mids:
            MessengerMessage.objects.filter(
                conversation__account=account,
                messenger_message_id__in=mids,
                is_from_page=True,
            ).update(status='delivered')
        else:
            # Watermark: tudo enviado antes desse timestamp foi entregue
            cutoff = datetime.fromtimestamp(watermark / 1000) if watermark else None
            if cutoff:
                MessengerMessage.objects.filter(
                    conversation__account=account,
                    conversation__psid=sender_psid,
                    is_from_page=True,
                    sent_at__lte=cutoff,
                ).update(status='delivered')

        return {'type': 'delivery', 'watermark': watermark, 'mids': mids}

    def _handle_read(self, page_id: str, sender_psid: str, read: Dict) -> Dict:
        """Marca mensagens como lidas."""
        from apps.messaging.models import MessengerMessage

        account = self._get_account(page_id)
        if not account:
            return {'type': 'read', 'status': 'account_not_found'}

        watermark = read.get('watermark', 0)
        cutoff = datetime.fromtimestamp(watermark / 1000) if watermark else None
        if cutoff:
            MessengerMessage.objects.filter(
                conversation__account=account,
                conversation__psid=sender_psid,
                is_from_page=True,
                sent_at__lte=cutoff,
                is_read=False,
            ).update(is_read=True)

        return {'type': 'read', 'watermark': watermark}

    def _handle_postback(self, page_id: str, sender_psid: str,
                         postback: Dict, timestamp: int) -> Dict:
        """Clique em botão (postback) — salva como mensagem e notifica."""
        from apps.messaging.models import MessengerConversation, MessengerMessage

        account = self._get_account(page_id)
        if not account:
            return {'type': 'postback', 'status': 'account_not_found'}

        payload_str = postback.get('payload', '')
        title = postback.get('title', '')

        conv, _ = MessengerConversation.objects.get_or_create(
            account=account,
            psid=sender_psid,
        )

        sent_at = datetime.fromtimestamp(timestamp / 1000) if timestamp else timezone.now()

        msg = MessengerMessage.objects.create(
            conversation=conv,
            message_type='POSTBACK',
            content=payload_str,
            is_from_page=False,
            is_read=False,
            sent_at=sent_at,
        )

        conv.unread_count += 1
        conv.last_message_at = sent_at
        conv.save(update_fields=['unread_count', 'last_message_at'])

        self._push_ws_event(
            group=f'messenger_{account.id}',
            event_type='messenger_postback_received',
            data={
                'payload': payload_str,
                'title': title,
                'conversation_id': str(conv.id),
                'account_id': str(account.id),
            }
        )

        return {'type': 'postback', 'payload': payload_str, 'message_id': str(msg.id)}

    def _handle_optin(self, page_id: str, sender_psid: str, optin: Dict) -> Dict:
        """Usuário optou em receber mensagens."""
        account = self._get_account(page_id)
        if not account:
            return {'type': 'optin', 'status': 'account_not_found'}

        from apps.messaging.models import MessengerConversation
        conv, _ = MessengerConversation.objects.get_or_create(
            account=account,
            psid=sender_psid,
        )
        conv.is_active = True
        conv.save(update_fields=['is_active'])

        logger.info(f"Messenger opt-in: PSID={sender_psid}, ref={optin.get('ref')}")
        return {'type': 'optin', 'psid': sender_psid}

    def _handle_referral(self, page_id: str, sender_psid: str, referral: Dict) -> Dict:
        """Usuário chegou via link com referral (ex: anúncio)."""
        ref = referral.get('ref', '')
        source = referral.get('source', '')
        logger.info(f"Messenger referral: PSID={sender_psid}, ref={ref}, source={source}")
        return {'type': 'referral', 'ref': ref, 'source': source}

    # ──────────────────────────────────────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────────────────────────────────────

    def _get_account(self, page_id: str):
        from apps.messaging.models import MessengerAccount

        if not page_id:
            return None
        return MessengerAccount.objects.filter(page_id=page_id, is_active=True).first()

    def _push_ws_event(self, group: str, event_type: str, data: Dict):
        try:
            from asgiref.sync import async_to_sync
            from channels.layers import get_channel_layer

            layer = get_channel_layer()
            if layer:
                async_to_sync(layer.group_send)(group, {'type': event_type, **data})
        except Exception as e:
            logger.debug(f"WebSocket push skipped ({event_type}): {e}")
