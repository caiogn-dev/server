#!/usr/bin/env bash
# Mostra os últimos pedidos vindos pelo catálogo do WhatsApp e diz, item a
# item, se o produto foi reconhecido. Serve para confirmar que a associação
# do catálogo na Meta propagou.
#
#   ./scripts/checar-catalogo.sh            # últimos 5 pedidos
#   ./scripts/checar-catalogo.sh 10         # últimos 10
set -euo pipefail
LIMITE="${1:-5}"

docker exec pastita_web /opt/venv/bin/python manage.py shell -c "
from apps.whatsapp.models import Message
from apps.whatsapp.services.webhook_service import resolve_catalog_products
from django.utils import timezone

msgs = Message.objects.filter(message_type='order').order_by('-created_at')[:${LIMITE}]
if not msgs:
    print('nenhum pedido por catalogo ainda')
for m in msgs:
    pedido = (m.content or {}).get('order') or {}
    itens = pedido.get('product_items') or []
    conta = m.account
    loja = getattr(conta, 'store', None) or (
        conta.stores.first() if hasattr(conta, 'stores') else None)
    if loja is None:
        cp = getattr(conta, 'company_profile', None)
        loja = getattr(cp, 'store', None)
    quando = timezone.localtime(m.created_at).strftime('%d/%m %H:%M')
    print(f'--- {quando} | conta={conta.name} | loja={getattr(loja,\"slug\",\"?\")} | catalog_id={pedido.get(\"catalog_id\")}')
    if loja is None:
        print('    LOJA NAO IDENTIFICADA -> vai para atendimento humano')
        continue
    rids = [i.get('product_retailer_id') for i in itens if i.get('product_retailer_id')]
    achados = resolve_catalog_products(loja, rids)
    for i in itens:
        rid = i.get('product_retailer_id')
        p = achados.get(rid)
        marca = 'OK  ' if p else 'FALHA'
        nome = p.name if p else '(nao reconhecido -> atendimento humano)'
        print(f'    {marca} {rid} -> {nome}')
    print(f'    {len(achados)}/{len(rids)} reconhecidos')
"
