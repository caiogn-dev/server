from django.conf import settings
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from ..models import (
    MessengerAccount,
    MessengerBroadcast,
    MessengerConversation,
    MessengerMessage,
    MessengerSponsoredMessage,
)
from ..services import MessengerBroadcastService, MessengerPlatformService, MessengerService
from .serializers import (
    MessengerAccountSerializer,
    MessengerBroadcastSerializer,
    MessengerConversationSerializer,
    MessengerMessageSerializer,
    MessengerProfileSerializer,
    MessengerSponsoredMessageSerializer,
)


class MessengerAccountViewSet(viewsets.ModelViewSet):
    """Manage connected Messenger pages."""

    queryset = MessengerAccount.objects.all()
    permission_classes = [IsAuthenticated]
    serializer_class = MessengerAccountSerializer

    def get_queryset(self):
        queryset = self.queryset
        if self.request.user.is_superuser or self.request.user.is_staff:
            return queryset
        return queryset.filter(user=self.request.user)

    @action(detail=True, methods=["post"])
    def sync(self, request, pk=None):
        account = self.get_object()
        messenger = MessengerService(account)

        try:
            page_info = messenger.get(account.page_id)
            account.page_name = page_info.get("name", account.page_name)
            account.category = page_info.get("category", "")
            account.followers_count = page_info.get("followers_count", 0)
            account.last_sync_at = timezone.now()
            account.save(
                update_fields=[
                    "page_name",
                    "category",
                    "followers_count",
                    "last_sync_at",
                    "updated_at",
                ]
            )
            return Response({"status": "success"})
        except Exception as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)


class MessengerProfileViewSet(viewsets.ViewSet):
    """Page-level Messenger profile settings."""

    permission_classes = [IsAuthenticated]

    def get_account(self):
        account_id = self.request.query_params.get("account_id")
        queryset = MessengerAccount.objects.all()
        if not (self.request.user.is_superuser or self.request.user.is_staff):
            queryset = queryset.filter(user=self.request.user)
        return get_object_or_404(queryset, id=account_id)

    @action(detail=False, methods=["get"])
    def get(self, request):
        account = self.get_account()
        from ..models import MessengerProfile

        profile, _ = MessengerProfile.objects.get_or_create(account=account)
        serializer = MessengerProfileSerializer(profile)
        return Response(serializer.data)

    @action(detail=False, methods=["post"])
    def greeting(self, request):
        account = self.get_account()
        text = request.data.get("text")
        locale = request.data.get("locale", "default")

        if not text:
            return Response({"error": "text e obrigatorio"}, status=status.HTTP_400_BAD_REQUEST)

        messenger = MessengerService(account)
        platform = MessengerPlatformService(messenger)

        if platform.set_greeting(text, locale):
            return Response({"status": "success"})
        return Response({"error": "Falha ao definir saudacao"}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=["post"])
    def get_started(self, request):
        account = self.get_account()
        payload = request.data.get("payload", "GET_STARTED")

        messenger = MessengerService(account)
        platform = MessengerPlatformService(messenger)

        if platform.set_get_started_button(payload):
            return Response({"status": "success"})
        return Response({"error": "Falha ao definir botao"}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=["post"])
    def persistent_menu(self, request):
        account = self.get_account()
        menu_items = request.data.get("menu_items", [])

        messenger = MessengerService(account)
        platform = MessengerPlatformService(messenger)

        if platform.set_persistent_menu(menu_items):
            return Response({"status": "success"})
        return Response({"error": "Falha ao definir menu"}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=["post"])
    def ice_breakers(self, request):
        account = self.get_account()
        ice_breakers = request.data.get("ice_breakers", [])

        messenger = MessengerService(account)
        platform = MessengerPlatformService(messenger)

        if platform.set_ice_breakers(ice_breakers):
            return Response({"status": "success"})
        return Response({"error": "Falha ao definir ice breakers"}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=["post"])
    def whitelist_domains(self, request):
        account = self.get_account()
        domains = request.data.get("domains", [])

        messenger = MessengerService(account)
        platform = MessengerPlatformService(messenger)

        if platform.whitelist_domains(domains):
            return Response({"status": "success"})
        return Response({"error": "Falha ao definir dominios"}, status=status.HTTP_400_BAD_REQUEST)


class MessengerConversationViewSet(viewsets.ModelViewSet):
    """Manage Messenger conversations."""

    queryset = MessengerConversation.objects.all()
    permission_classes = [IsAuthenticated]
    serializer_class = MessengerConversationSerializer

    def get_queryset(self):
        queryset = self.queryset.filter(is_active=True)
        account_id = self.request.query_params.get("account")
        if account_id:
            queryset = queryset.filter(account_id=account_id)
        if self.request.user.is_superuser or self.request.user.is_staff:
            return queryset
        return queryset.filter(account__user=self.request.user)

    @action(detail=True, methods=["get"])
    def messages(self, request, pk=None):
        conversation = self.get_object()
        queryset = conversation.messages.order_by("created_at")
        serializer = MessengerMessageSerializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["post"], url_path="send-message")
    def send_message(self, request, pk=None):
        conversation = self.get_object()
        message_type = (
            request.data.get("message_type")
            or request.data.get("type")
            or "text"
        )
        content = request.data.get("content", "")
        attachment_url = request.data.get("attachment_url")

        messenger = MessengerService(conversation.account)

        try:
            normalized = str(message_type).lower()
            if normalized == "text":
                result = messenger.send_text_message(conversation.psid, content)
            elif normalized == "image":
                result = messenger.send_image(conversation.psid, attachment_url)
            elif normalized == "video":
                result = messenger.send_video(conversation.psid, attachment_url)
            elif normalized == "audio":
                result = messenger.send_audio(conversation.psid, attachment_url)
            elif normalized == "template":
                template = request.data.get("template", {})
                result = messenger.send_template(conversation.psid, template)
            else:
                return Response(
                    {"error": "Tipo de mensagem invalido"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            message = MessengerMessage.objects.create(
                conversation=conversation,
                message_type=normalized.upper(),
                content=content,
                attachment_url=attachment_url,
                is_from_page=True,
                messenger_message_id=result.get("message_id"),
                sent_at=timezone.now(),
            )
            conversation.last_message_at = message.sent_at or timezone.now()
            conversation.save(update_fields=["last_message_at", "updated_at"])
            serializer = MessengerMessageSerializer(message)
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        except Exception as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["post"], url_path="mark-read")
    def mark_read(self, request, pk=None):
        conversation = self.get_object()
        messenger = MessengerService(conversation.account)

        try:
            messenger.mark_seen(conversation.psid)
        except Exception:
            pass

        MessengerMessage.objects.filter(
            conversation=conversation,
            is_from_page=False,
            is_read=False,
        ).update(is_read=True, read_at=timezone.now())
        conversation.unread_count = 0
        conversation.save(update_fields=["unread_count", "updated_at"])
        conversation.refresh_from_db()
        serializer = self.get_serializer(conversation)
        return Response(serializer.data)

    @action(detail=True, methods=["post"], url_path="typing-on")
    def typing_on(self, request, pk=None):
        conversation = self.get_object()
        messenger = MessengerService(conversation.account)
        messenger.typing_on(conversation.psid)
        return Response({"status": "typing_on"})

    @action(detail=True, methods=["post"], url_path="typing-off")
    def typing_off(self, request, pk=None):
        conversation = self.get_object()
        messenger = MessengerService(conversation.account)
        messenger.typing_off(conversation.psid)
        return Response({"status": "typing_off"})


class MessengerBroadcastViewSet(viewsets.ModelViewSet):
    """Manage Messenger broadcasts."""

    queryset = MessengerBroadcast.objects.all()
    permission_classes = [IsAuthenticated]
    serializer_class = MessengerBroadcastSerializer

    def get_queryset(self):
        queryset = self.queryset
        if self.request.user.is_superuser or self.request.user.is_staff:
            return queryset
        return queryset.filter(account__user=self.request.user)

    @action(detail=True, methods=["post"])
    def send(self, request, pk=None):
        broadcast = self.get_object()
        messenger = MessengerService(broadcast.account)
        broadcast_service = MessengerBroadcastService(messenger)

        if broadcast_service.send_broadcast(str(broadcast.id)):
            return Response({"status": "sending"})
        return Response({"error": "Falha ao enviar broadcast"}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["get"])
    def insights(self, request, pk=None):
        broadcast = self.get_object()
        messenger = MessengerService(broadcast.account)
        broadcast_service = MessengerBroadcastService(messenger)
        insights = broadcast_service.get_broadcast_insights(str(broadcast.id))
        return Response(insights)

    @action(detail=False, methods=["get"])
    def tags(self, request):
        account_id = request.query_params.get("account_id")
        queryset = MessengerAccount.objects.all()
        if not (request.user.is_superuser or request.user.is_staff):
            queryset = queryset.filter(user=request.user)
        account = get_object_or_404(queryset, id=account_id)

        messenger = MessengerService(account)
        broadcast_service = MessengerBroadcastService(messenger)
        tags = broadcast_service.get_message_tags()
        return Response(tags)


class MessengerSponsoredViewSet(viewsets.ModelViewSet):
    """Manage sponsored Messenger messages."""

    queryset = MessengerSponsoredMessage.objects.all()
    permission_classes = [IsAuthenticated]
    serializer_class = MessengerSponsoredMessageSerializer

    def get_queryset(self):
        queryset = self.queryset
        if self.request.user.is_superuser or self.request.user.is_staff:
            return queryset
        return queryset.filter(account__user=self.request.user)

    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        sponsored = self.get_object()
        messenger = MessengerService(sponsored.account)
        broadcast_service = MessengerBroadcastService(messenger)

        if broadcast_service.submit_sponsored_message(str(sponsored.id)):
            return Response({"status": "submitted"})
        return Response({"error": "Falha ao submeter"}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["post"])
    def pause(self, request, pk=None):
        sponsored = self.get_object()
        messenger = MessengerService(sponsored.account)
        broadcast_service = MessengerBroadcastService(messenger)

        if broadcast_service.pause_sponsored_message(str(sponsored.id)):
            return Response({"status": "paused"})
        return Response({"error": "Falha ao pausar"}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["post"])
    def resume(self, request, pk=None):
        sponsored = self.get_object()
        messenger = MessengerService(sponsored.account)
        broadcast_service = MessengerBroadcastService(messenger)

        if broadcast_service.resume_sponsored_message(str(sponsored.id)):
            return Response({"status": "resumed"})
        return Response({"error": "Falha ao retomar"}, status=status.HTTP_400_BAD_REQUEST)


class MessengerWebhookViewSet(viewsets.ViewSet):
    """Messenger webhook endpoints."""

    permission_classes = []

    def create(self, request):
        from ..tasks import process_messenger_webhook

        payload = request.data
        process_messenger_webhook.delay(payload)
        return Response({"status": "received"})

    @action(detail=False, methods=["get"])
    def verify(self, request):
        mode = request.query_params.get("hub.mode")
        token = request.query_params.get("hub.verify_token")
        challenge = request.query_params.get("hub.challenge")
        verify_token = (
            getattr(settings, "MESSENGER_WEBHOOK_VERIFY_TOKEN", None)
            or getattr(settings, "MESSENGER_VERIFY_TOKEN", "")
        )

        if mode == "subscribe" and token == verify_token:
            return Response(int(challenge))
        return Response("Verification failed", status=403)
