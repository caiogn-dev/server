import logging
import hmac
from datetime import timedelta

from django.conf import settings
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from ..models import (
    InstagramAccount,
    InstagramCatalog,
    InstagramConversation,
    InstagramInsight,
    InstagramLive,
    InstagramMedia,
    InstagramProduct,
    InstagramScheduledPost,
)
from ..services import (
    InstagramAPI,
    InstagramDirectService,
    InstagramGraphService,
    InstagramLiveService,
    InstagramShoppingService,
)
from .serializers import (
    InstagramAccountSerializer,
    InstagramCatalogSerializer,
    InstagramConversationSerializer,
    InstagramInsightSerializer,
    InstagramLiveSerializer,
    InstagramMediaSerializer,
    InstagramMessageSerializer,
    InstagramProductSerializer,
    InstagramScheduledPostSerializer,
)

logger = logging.getLogger(__name__)


class InstagramAccountViewSet(viewsets.ModelViewSet):
    """Manage connected Instagram accounts."""

    queryset = InstagramAccount.objects.all()
    permission_classes = [IsAuthenticated]
    serializer_class = InstagramAccountSerializer

    def get_queryset(self):
        queryset = self.queryset
        if self.request.user.is_superuser or self.request.user.is_staff:
            return queryset
        return queryset.filter(user=self.request.user)

    @action(detail=True, methods=["post"])
    def sync(self, request, pk=None):
        account = self.get_object()
        api = InstagramAPI(account)

        if api.sync_account_info():
            return Response({"status": "success", "message": "Conta sincronizada"})

        return Response(
            {"status": "error", "message": "Falha na sincronizacao"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    @action(detail=True, methods=["get"])
    def insights(self, request, pk=None):
        account = self.get_object()
        days = int(request.query_params.get("days", 30))
        since = timezone.now() - timedelta(days=days)
        until = timezone.now()

        api = InstagramAPI(account)
        graph_service = InstagramGraphService(api)

        try:
            insights = graph_service.get_account_insights(since, until)
            return Response(insights)
        except Exception as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)


class InstagramMediaViewSet(viewsets.ModelViewSet):
    """Manage Instagram media."""

    queryset = InstagramMedia.objects.all()
    permission_classes = [IsAuthenticated]
    serializer_class = InstagramMediaSerializer

    def get_queryset(self):
        queryset = self.queryset
        if self.request.user.is_superuser or self.request.user.is_staff:
            return queryset
        return queryset.filter(account__user=self.request.user)

    @action(detail=False, methods=["get"])
    def feed(self, request):
        queryset = self.get_queryset().filter(
            media_type__in=["IMAGE", "VIDEO", "CAROUSEL_ALBUM"]
        )
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["get"])
    def stories(self, request):
        queryset = self.get_queryset().filter(media_type="STORY")
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["get"])
    def reels(self, request):
        queryset = self.get_queryset().filter(media_type="REELS")
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["post"])
    def publish(self, request, pk=None):
        media = self.get_object()
        api = InstagramAPI(media.account)
        graph_service = InstagramGraphService(api)

        try:
            result = graph_service.publish_media(
                media.media_type,
                media.media_url,
                media.caption,
            )
            media.instagram_media_id = result.get("id")
            media.status = "PUBLISHED"
            media.published_at = timezone.now()
            media.save(update_fields=["instagram_media_id", "status", "published_at", "updated_at"])
            return Response({"status": "success", "id": result.get("id")})
        except Exception as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["post"])
    def schedule(self, request, pk=None):
        media = self.get_object()
        schedule_time = request.data.get("schedule_time")

        if not schedule_time:
            return Response(
                {"error": "schedule_time e obrigatorio"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        media.status = "SCHEDULED"
        media.scheduled_at = schedule_time
        media.save(update_fields=["status", "scheduled_at", "updated_at"])
        return Response({"status": "scheduled"})

    @action(detail=True, methods=["get"])
    def insights(self, request, pk=None):
        media = self.get_object()
        api = InstagramAPI(media.account)
        graph_service = InstagramGraphService(api)

        try:
            insights = graph_service.get_media_insights(media.instagram_media_id)
            return Response(insights)
        except Exception as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["get"])
    def comments(self, request, pk=None):
        media = self.get_object()
        api = InstagramAPI(media.account)
        graph_service = InstagramGraphService(api)

        try:
            comments = graph_service.get_comments(media.instagram_media_id)
            return Response(comments)
        except Exception as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)


class InstagramShoppingViewSet(viewsets.ViewSet):
    """Instagram shopping helpers."""

    permission_classes = [IsAuthenticated]

    def get_account(self):
        account_id = self.request.query_params.get("account_id")
        queryset = InstagramAccount.objects.all()
        if not (self.request.user.is_superuser or self.request.user.is_staff):
            queryset = queryset.filter(user=self.request.user)
        return get_object_or_404(queryset, id=account_id)

    @action(detail=False, methods=["get"])
    def catalogs(self, request):
        account = self.get_account()
        api = InstagramAPI(account)
        service = InstagramShoppingService(api)
        return Response(service.list_catalogs())

    @action(detail=False, methods=["get"])
    def products(self, request):
        account = self.get_account()
        catalog_id = request.query_params.get("catalog_id")
        api = InstagramAPI(account)
        service = InstagramShoppingService(api)
        return Response(service.list_products(catalog_id))

    @action(detail=False, methods=["post"])
    def tag_product(self, request):
        account_id = request.data.get("account_id") or request.query_params.get("account_id")
        queryset = InstagramAccount.objects.all()
        if not (request.user.is_superuser or request.user.is_staff):
            queryset = queryset.filter(user=request.user)
        account = get_object_or_404(queryset, id=account_id)

        media_id = request.data.get("media_id")
        product_id = request.data.get("product_id")
        x = request.data.get("x", 0.5)
        y = request.data.get("y", 0.5)

        api = InstagramAPI(account)
        service = InstagramShoppingService(api)

        try:
            tag = service.add_tag_to_media(media_id, product_id, x, y)
            return Response({"status": "success", "tag_id": str(tag.id)})
        except Exception as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=["get"])
    def settings(self, request):
        account = self.get_account()
        api = InstagramAPI(account)
        service = InstagramShoppingService(api)
        return Response(service.get_shopping_settings())


class InstagramLiveViewSet(viewsets.ModelViewSet):
    """Manage Instagram live records."""

    queryset = InstagramLive.objects.all()
    permission_classes = [IsAuthenticated]
    serializer_class = InstagramLiveSerializer

    def get_queryset(self):
        queryset = self.queryset
        if self.request.user.is_superuser or self.request.user.is_staff:
            return queryset
        return queryset.filter(account__user=self.request.user)

    @action(detail=True, methods=["post"])
    def start(self, request, pk=None):
        live = self.get_object()
        api = InstagramAPI(live.account)
        service = InstagramLiveService(api)

        try:
            result = service.start_live(str(live.id))
            return Response(result)
        except Exception as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["post"])
    def end(self, request, pk=None):
        live = self.get_object()
        api = InstagramAPI(live.account)
        service = InstagramLiveService(api)

        if service.end_live(str(live.id)):
            return Response({"status": "ended"})

        return Response({"error": "Falha ao finalizar"}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["get"])
    def comments(self, request, pk=None):
        live = self.get_object()
        api = InstagramAPI(live.account)
        service = InstagramLiveService(api)
        return Response(service.get_comments(str(live.id)))


class InstagramConversationViewSet(viewsets.ModelViewSet):
    """Manage Instagram DM conversations."""

    queryset = InstagramConversation.objects.all()
    permission_classes = [IsAuthenticated]
    serializer_class = InstagramConversationSerializer

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
        queryset = conversation.messages.filter(is_unsent=False).order_by("created_at")
        serializer = InstagramMessageSerializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["post"], url_path="send_message")
    def send_message(self, request, pk=None):
        conversation = self.get_object()
        message_type = (
            request.data.get("message_type")
            or request.data.get("type")
            or "TEXT"
        )
        content = request.data.get("content", "")
        media_url = request.data.get("media_url")
        reply_to_id = request.data.get("reply_to")

        api = InstagramAPI(conversation.account)
        service = InstagramDirectService(api)

        try:
            logger.info(
                "Instagram send request received: account=%s conversation=%s participant=%s message_type=%s user=%s",
                conversation.account_id,
                conversation.id,
                conversation.participant_id,
                str(message_type).upper(),
                request.user.id,
            )
            message = service.send_message(
                str(conversation.id),
                str(message_type).upper(),
                content=content,
                media_url=media_url,
                reply_to_id=reply_to_id,
            )
            serializer = InstagramMessageSerializer(message)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        except Exception as exc:
            logger.warning(
                "Instagram send request failed: account=%s conversation=%s participant=%s error=%s",
                conversation.account_id,
                conversation.id,
                conversation.participant_id,
                exc,
            )
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["post"], url_path="mark_as_read")
    def mark_as_read(self, request, pk=None):
        conversation = self.get_object()
        api = InstagramAPI(conversation.account)
        service = InstagramDirectService(api)

        if service.mark_as_read(str(conversation.id)):
            conversation.refresh_from_db()
            serializer = self.get_serializer(conversation)
            return Response(serializer.data)

        return Response({"error": "Falha ao marcar"}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["post"])
    def archive(self, request, pk=None):
        conversation = self.get_object()
        api = InstagramAPI(conversation.account)
        service = InstagramDirectService(api)

        if service.archive_conversation(str(conversation.id)):
            return Response({"status": "archived"})

        return Response({"error": "Falha ao arquivar"}, status=status.HTTP_400_BAD_REQUEST)


class InstagramMessageViewSet(viewsets.ViewSet):
    """Operate on individual Instagram messages."""

    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=["post"])
    def react(self, request):
        return Response({"status": "success"})

    @action(detail=False, methods=["post"])
    def unsend(self, request):
        return Response({"status": "success"})


class InstagramWebhookViewSet(viewsets.ViewSet):
    """Webhook endpoints used by Meta verification and delivery."""

    permission_classes = []

    def create(self, request):
        return Response({"status": "received"})

    @action(detail=False, methods=["get"])
    def verify(self, request):
        mode = request.query_params.get("hub.mode")
        token = request.query_params.get("hub.verify_token")
        challenge = request.query_params.get("hub.challenge")

        verify_token = getattr(settings, "INSTAGRAM_WEBHOOK_VERIFY_TOKEN", "") or ""
        tokens_match = bool(verify_token) and hmac.compare_digest(
            (token or "").encode(),
            verify_token.encode(),
        )
        if mode == "subscribe" and tokens_match:
            return Response(int(challenge))
        return Response("Verification failed", status=403)
