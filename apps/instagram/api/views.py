import logging
import hmac
import requests
from datetime import timedelta

from django.conf import settings
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
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

    @action(detail=False, methods=["post"], url_path="connect", permission_classes=[IsAuthenticated])
    def connect(self, request):
        """Recebe o authorization code do Instagram Business Login e cria/atualiza a conta.

        Payload: { code: str }
        O frontend abre o popup OAuth do Instagram, que redireciona para /ig/callback,
        que por sua vez redireciona para o frontend com o code na URL.
        O frontend autenticado então chama este endpoint com o code.
        """
        code = request.data.get("code")

        if not code:
            return Response(
                {"error": "code é obrigatório"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        app_id = getattr(settings, "INSTAGRAM_APP_ID", "")
        app_secret = getattr(settings, "INSTAGRAM_APP_SECRET", "")
        if not app_id or not app_secret:
            return Response(
                {"error": "INSTAGRAM_APP_ID/INSTAGRAM_APP_SECRET não configurados no servidor"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # O redirect_uri deve ser exatamente o registrado no app Meta
        redirect_uri = getattr(
            settings,
            "INSTAGRAM_OAUTH_REDIRECT_URI",
            "https://backend.pastita.com.br/ig/callback",
        )

        # 1. Troca o code por short-lived token via Instagram Business Login
        try:
            token_resp = requests.post(
                "https://api.instagram.com/oauth/access_token",
                data={
                    "client_id": app_id,
                    "client_secret": app_secret,
                    "grant_type": "authorization_code",
                    "redirect_uri": redirect_uri,
                    "code": code,
                },
                timeout=30,
            )
            token_resp.raise_for_status()
            short_token = token_resp.json().get("access_token")
        except Exception as exc:
            logger.error("Instagram code exchange failed: %s", exc)
            raw = getattr(exc, "response", None)
            detail = raw.text if raw is not None else str(exc)
            return Response(
                {"error": f"Falha ao trocar code por token: {detail}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 2. Troca por long-lived token (~60 dias)
        try:
            ll_resp = requests.get(
                "https://graph.instagram.com/access_token",
                params={
                    "grant_type": "ig_exchange_token",
                    "client_id": app_id,
                    "client_secret": app_secret,
                    "access_token": short_token,
                },
                timeout=30,
            )
            ll_resp.raise_for_status()
            long_token = ll_resp.json().get("access_token", short_token)
        except Exception as exc:
            logger.warning("Instagram long-lived token exchange failed, using short token: %s", exc)
            long_token = short_token

        # 3. Busca informações da conta Instagram
        try:
            me_resp = requests.get(
                "https://graph.instagram.com/v22.0/me",
                params={
                    "fields": "id,username,name,biography,followers_count,follows_count,media_count,profile_picture_url,website",
                    "access_token": long_token,
                },
                timeout=30,
            )
            me_resp.raise_for_status()
            info = me_resp.json()
        except Exception as exc:
            logger.error("Instagram /me fetch failed: %s", exc)
            info = {}

        ig_id = info.get("id")
        if not ig_id:
            return Response(
                {"error": "Não foi possível obter ID da conta Instagram. Verifique as permissões do app."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 4. Cria ou atualiza a InstagramAccount
        account, created = InstagramAccount.objects.update_or_create(
            user=request.user,
            instagram_business_id=ig_id,
            defaults={
                "username": info.get("username", ig_id),
                "platform": "instagram",
                "access_token": long_token,
                "biography": info.get("biography", ""),
                "website": info.get("website", ""),
                "followers_count": info.get("followers_count", 0),
                "follows_count": info.get("follows_count", 0),
                "media_count": info.get("media_count", 0),
                "profile_picture_url": info.get("profile_picture_url", ""),
                "is_active": True,
            },
        )

        serializer = self.get_serializer(account)
        return Response(serializer.data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

    @action(detail=True, methods=["post"])
    def sync(self, request, pk=None):
        account = self.get_object()
        api = InstagramAPI(account)
        try:
            info = api.get_account_info()
            account.username = info.get("username", account.username)
            account.biography = info.get("biography", "")
            account.website = info.get("website", "")
            account.followers_count = info.get("followers_count", 0)
            account.follows_count = info.get("follows_count", 0)
            account.media_count = info.get("media_count", 0)
            account.profile_picture_url = info.get("profile_picture_url", "")
            account.is_verified = info.get("verified", False)
            from django.utils import timezone
            account.last_sync_at = timezone.now()
            account.save()
            return Response({"status": "success", "message": "Conta sincronizada"})
        except Exception as exc:
            return Response(
                {"status": "error", "message": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

    @action(detail=True, methods=["post"], url_path="refresh-page-token")
    def refresh_page_token(self, request, pk=None):
        """Renova o Page Access Token a partir do User Access Token já salvo.

        Chame este endpoint sempre que receber o erro
        'Page Access Token inválido ou expirado'.
        """
        account = self.get_object()
        api = InstagramAPI(account)
        try:
            api.refresh_page_token()
            return Response({"status": "success", "message": "Page Access Token renovado com sucesso."})
        except Exception as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

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


@csrf_exempt
def ig_oauth_callback(request):
    """Instagram Business Login OAuth callback.

    Instagram redirects here after the user authorizes the app.
    We relay the code (or error) to the frontend so the authenticated
    SPA can call POST /instagram/accounts/connect/ with the code.
    """
    frontend_url = getattr(settings, "FRONTEND_URL", "http://localhost:3000")
    code = request.GET.get("code")
    error = request.GET.get("error_description") or request.GET.get("error")

    if code:
        return HttpResponseRedirect(f"{frontend_url}/instagram/callback?code={code}")
    return HttpResponseRedirect(
        f"{frontend_url}/instagram/callback?error={error or 'authorization_failed'}"
    )
