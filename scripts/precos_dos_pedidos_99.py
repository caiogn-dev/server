"""Só leitura: bloco `price` de cada pedido da 99 num dia, ao lado do que o painel gravou.

Uso (dia padrão 2026-11-06):
    docker exec -i pastita_web python manage.py shell < scripts/precos_dos_pedidos_99.py
Outro dia:
    docker exec -i -e DIA=2026-11-07 pastita_web python manage.py shell < scripts/precos_dos_pedidos_99.py

Não grava nada. Não mostra nome, telefone nem endereço.
"""
import json
import os
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from apps.stores.models import StoreOrder
from apps.webhooks.models import WebhookEvent

TZ = ZoneInfo('America/Sao_Paulo')
DIA = date.fromisoformat(os.environ.get('DIA', '2026-11-06'))
inicio = datetime.combine(DIA, time.min, TZ)
fim = datetime.combine(DIA, time.max, TZ)


def achar(obj, chave):
    """Primeiro valor de `chave` em qualquer nível do JSON."""
    if isinstance(obj, dict):
        if chave in obj:
            return obj[chave]
        for v in obj.values():
            r = achar(v, chave)
            if r is not None:
                return r
    elif isinstance(obj, list):
        for v in obj:
            r = achar(v, chave)
            if r is not None:
                return r
    return None


# order_id da 99 -> bloco price do orderNew
precos = {}
for e in WebhookEvent.objects.filter(provider='99food', created_at__range=(inicio, fim)).order_by('created_at'):
    payload = getattr(e, 'payload', None) or {}
    oid = achar(payload, 'order_id')
    price = achar(payload, 'price')
    if oid and isinstance(price, dict) and str(oid) not in precos:
        precos[str(oid)] = price

pedidos = StoreOrder.objects.filter(source='99food', created_at__range=(inicio, fim)).order_by('created_at')
print(f'{DIA:%d/%m/%Y}: {pedidos.count()} pedidos da 99 no painel, {len(precos)} blocos price nos webhooks\n')

for p in pedidos:
    meta = (p.metadata or {}).get('99food') or {}
    oid = str(meta.get('order_id') or '')
    print('=' * 70)
    print(f"99 #{meta.get('numero')}  {p.created_at.astimezone(TZ):%H:%M}  painel {p.order_number}  status {p.status}")
    print(f'  painel gravou: subtotal {p.subtotal}  desconto {p.discount}  frete {p.delivery_fee}  total {p.total}')
    price = precos.pop(oid, None)
    if price is None:
        print('  (sem bloco price no webhook desse pedido)')
    else:
        # A 99 manda centavos; mostro o valor cru e em reais.
        for k in sorted(price):
            v = price[k]
            extra = ''
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                extra = f'   (= R$ {v / 100:.2f} se for centavos)'
            print(f'  price.{k}: {json.dumps(v, ensure_ascii=False, default=str)[:80]}{extra}')

if precos:
    print('\nBlocos price sem pedido no painel:', ', '.join(precos))
