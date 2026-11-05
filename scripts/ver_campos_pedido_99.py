"""Só leitura: mostra os campos do último orderNew da 99 (sem dados pessoais).

docker exec -i pastita_web python manage.py shell < scripts/ver_campos_pedido_99.py
"""
import json

from apps.webhooks.models import WebhookEvent

SENSIVEIS = ('name', 'phone', 'address', 'street', 'lat', 'lng', 'email', 'cpf', 'doc', 'remark', 'poi', 'house')


def mostrar(obj, prefixo=''):
    if isinstance(obj, dict):
        for chave, valor in obj.items():
            mostrar(valor, f'{prefixo}.{chave}' if prefixo else chave)
    elif isinstance(obj, list):
        print(f'{prefixo}: lista[{len(obj)}]')
        if obj:
            mostrar(obj[0], f'{prefixo}[0]')
    else:
        if any(s in prefixo.lower() for s in SENSIVEIS):
            print(f'{prefixo}: <oculto>')
        else:
            print(f'{prefixo}: {str(obj)[:40]}')


eventos = [e for e in WebhookEvent.objects.filter(provider='99food').order_by('-created_at')[:200]
           if 'orderNew' in json.dumps(getattr(e, 'payload', None) or {}, default=str)]
print(f'{len(eventos)} orderNew recentes')
if eventos:
    mostrar(eventos[0].payload)
