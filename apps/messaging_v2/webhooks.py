"""
Webhook handlers para messaging_v2 - Recebimento de eventos externos.
"""
import hmac
import hashlib
import json
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.conf import settings

from .tasks import process_webhook_event


@csrf_exempt
@require_http_methods(['GET', 'POST'])
def whatsapp_webhook(request):
    """
    Webhook para eventos do WhatsApp Business API.
    
    GET: Verificação do webhook (Meta)
    POST: Recebimento de eventos
    """
    if request.method == 'GET':
        # Verificação do webhook
        mode = request.GET.get('hub.mode')
        token = request.GET.get('hub.verify_token')
        challenge = request.GET.get('hub.challenge')
        
        verify_token = getattr(settings, 'WHATSAPP_VERIFY_TOKEN', 'pastita-webhook-token')
        
        if mode == 'subscribe' and token == verify_token:
            return JsonResponse(int(challenge), safe=False, status=200)
        
        return JsonResponse({'error': 'Verification failed'}, status=403)
    
    elif request.method == 'POST':
        # Verificar assinatura
        signature = request.headers.get('X-Hub-Signature-256', '')
        app_secret = getattr(settings, 'WHATSAPP_APP_SECRET', '')
        
        if app_secret and signature:
            expected = 'sha256=' + hmac.new(
                app_secret.encode(),
                request.body,
                hashlib.sha256
            ).hexdigest()
            
            if not hmac.compare_digest(expected, signature):
                return JsonResponse({'error': 'Invalid signature'}, status=401)
        
        # Processar evento de forma assíncrona
        try:
            event_data = json.loads(request.body)
            process_webhook_event.delay('whatsapp', event_data)
            
            return JsonResponse({'status': 'accepted'}, status=200)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)


@csrf_exempt
@require_http_methods(['GET', 'POST'])
def instagram_webhook(request):
    """
    Webhook para eventos do Instagram API.
    """
    if request.method == 'GET':
        mode = request.GET.get('hub.mode')
        token = request.GET.get('hub.verify_token')
        challenge = request.GET.get('hub.challenge')
        
        verify_token = getattr(settings, 'INSTAGRAM_VERIFY_TOKEN', 'pastita-instagram-token')
        
        if mode == 'subscribe' and token == verify_token:
            return JsonResponse(int(challenge), safe=False, status=200)
        
        return JsonResponse({'error': 'Verification failed'}, status=403)
    
    elif request.method == 'POST':
        try:
            event_data = json.loads(request.body)
            process_webhook_event.delay('instagram', event_data)
            
            return JsonResponse({'status': 'accepted'}, status=200)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)


@csrf_exempt
@require_http_methods(['POST'])
def generic_webhook(request, platform):
    """
    Webhook genérico para outras plataformas.
    """
    try:
        event_data = json.loads(request.body)
        process_webhook_event.delay(platform, event_data)
        
        return JsonResponse({'status': 'accepted'}, status=200)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
