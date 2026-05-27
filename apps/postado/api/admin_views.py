from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from apps.postado.api.admin_auth import IsPostadoAdmin
from apps.postado.api.admin_serializers import (
    PostadoClientListSerializer, PostadoClientAdminSerializer,
    PostadoPackAdminSerializer, PostadoPackListSerializer,
    PostadoPostAdminSerializer,
)
from apps.postado.models import PostadoClient, PostadoPack, PostadoPost


class AdminDashboardView(APIView):
    permission_classes = [IsPostadoAdmin]

    def get(self, request):
        review_queue = PostadoPack.objects.filter(status='review').select_related('client')
        return Response({
            'total_clients': PostadoClient.objects.count(),
            'active_clients': PostadoClient.objects.filter(status='active').count(),
            'packs_in_review': PostadoPack.objects.filter(status='review').count(),
            'packs_generating': PostadoPack.objects.filter(status='generating').count(),
            'review_queue': PostadoPackListSerializer(review_queue, many=True).data,
        })


class AdminClientListView(APIView):
    permission_classes = [IsPostadoAdmin]

    def get(self, request):
        clients = PostadoClient.objects.all()
        return Response(PostadoClientListSerializer(clients, many=True).data)


class AdminClientDetailView(APIView):
    permission_classes = [IsPostadoAdmin]
    EDITABLE_FIELDS = {
        'business_name', 'niche', 'tone', 'brand_colors', 'logo_url',
        'description', 'products', 'target_audience', 'instagram_handle',
        'contact_info', 'reference_images', 'brand_guidelines', 'status',
    }

    def get(self, request, client_id):
        try:
            client = PostadoClient.objects.prefetch_related('packs').get(id=client_id)
        except PostadoClient.DoesNotExist:
            return Response({'error': 'not found'}, status=404)
        return Response(PostadoClientAdminSerializer(client).data)

    def patch(self, request, client_id):
        try:
            client = PostadoClient.objects.get(id=client_id)
        except PostadoClient.DoesNotExist:
            return Response({'error': 'not found'}, status=404)
        data = {k: v for k, v in request.data.items() if k in self.EDITABLE_FIELDS}
        for field, value in data.items():
            setattr(client, field, value)
        client.save(update_fields=list(data.keys()))
        return Response(PostadoClientAdminSerializer(client).data)


class AdminPackDetailView(APIView):
    permission_classes = [IsPostadoAdmin]

    def get(self, request, pack_id):
        try:
            pack = PostadoPack.objects.prefetch_related('posts').get(id=pack_id)
        except PostadoPack.DoesNotExist:
            return Response({'error': 'not found'}, status=404)
        return Response(PostadoPackAdminSerializer(pack).data)


class AdminPostUpdateView(APIView):
    permission_classes = [IsPostadoAdmin]
    EDITABLE_FIELDS = {'caption', 'hashtags', 'cta', 'status', 'revision_notes'}

    def patch(self, request, post_id):
        try:
            post = PostadoPost.objects.get(id=post_id)
        except PostadoPost.DoesNotExist:
            return Response({'error': 'not found'}, status=404)
        data = {k: v for k, v in request.data.items() if k in self.EDITABLE_FIELDS}
        for field, value in data.items():
            setattr(post, field, value)
        post.save(update_fields=list(data.keys()))
        return Response(PostadoPostAdminSerializer(post).data)


class AdminPackApproveView(APIView):
    permission_classes = [IsPostadoAdmin]

    def post(self, request, pack_id):
        try:
            pack = PostadoPack.objects.get(id=pack_id)
        except PostadoPack.DoesNotExist:
            return Response({'error': 'not found'}, status=404)
        pack.status = 'approved'
        pack.approved_at = timezone.now()
        pack.save(update_fields=['status', 'approved_at'])
        return Response({'status': 'approved'})


class AdminGeneratePackView(APIView):
    permission_classes = [IsPostadoAdmin]

    def post(self, request):
        client_id = request.data.get('client_id')
        month = request.data.get('month')
        if not client_id or not month:
            return Response({'error': 'client_id and month required'}, status=400)
        try:
            client = PostadoClient.objects.get(id=client_id)
        except PostadoClient.DoesNotExist:
            return Response({'error': 'client not found'}, status=404)
        if PostadoPack.objects.filter(client=client, month=month).exists():
            return Response({'error': f'Pack {month} já existe para este cliente'}, status=409)
        pack = PostadoPack.objects.create(client=client, month=month)
        from apps.postado.tasks import generate_pack
        generate_pack.delay(str(pack.id))
        return Response({
            'status': 'generating',
            'pack_id': str(pack.id),
        }, status=201)


class AdminPostRegenerateView(APIView):
    permission_classes = [IsPostadoAdmin]

    def post(self, request, post_id):
        from apps.postado.tasks import regenerate_single_post
        try:
            post = PostadoPost.objects.get(id=post_id)
        except PostadoPost.DoesNotExist:
            return Response({'error': 'not found'}, status=404)
        regenerate_single_post.delay(str(post.id))
        return Response({'status': 'queued'}, status=202)
