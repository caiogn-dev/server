"""Cria o WebhookEndpoint do Pagar.me em producao.

POR QUE ESTE SCRIPT EXISTE

Medido em 22/09: `WebhookEndpoint.objects.count()` era ZERO, e `pagarme` esta
em `_PROVIDERS_REQUIRE_SIGNATURE` (fail-closed). Sem o registro,
`_verify_signature` devolve None e o dispatcher responde 403 a todo webhook.

Do lado do Pagar.me, os 7 hooks entregues desde 12/set estao TODOS com
`status=failed` e `attempts: 1/1` — ele nao repete. Cada 403 perdeu o evento
para sempre, e o caminho `processing -> paid` nunca teve como fechar.

Roda dentro do container:

    docker cp scripts/registrar_webhook_pagarme.py pastita_web:/tmp/reg.py
    docker exec -e PAGARME_WEBHOOK_USER=... -e PAGARME_WEBHOOK_PASS=... \
        pastita_web python /tmp/reg.py

O usuario e a senha sao os MESMOS configurados em Webhooks no painel do
Pagar.me (Basic Auth). Se divergirem, o dispatcher passa a devolver 403 por
assinatura invalida em vez de por falta de registro — mesmo sintoma, outra
causa.
"""
import os
import sys

sys.path.insert(0, '/app')

import django  # noqa: E402

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.production')
django.setup()

from apps.webhooks.models import WebhookEndpoint  # noqa: E402

usuario = os.environ.get('PAGARME_WEBHOOK_USER', '').strip()
senha = os.environ.get('PAGARME_WEBHOOK_PASS', '').strip()
if not usuario or not senha:
    raise SystemExit(
        'Faltam PAGARME_WEBHOOK_USER e PAGARME_WEBHOOK_PASS no ambiente.\n'
        'Use os mesmos valores do Basic Auth configurado no painel do Pagar.me.'
    )

endpoint, criado = WebhookEndpoint.objects.update_or_create(
    provider='pagarme',
    defaults=dict(
        name='Pagar.me (vale)',
        path='pagarme',
        secret=f'{usuario}:{senha}',
        # O default do modelo e 'X-Hub-Signature-256' (formato da Meta). O
        # Pagar.me manda Basic Auth no header padrao; sem esta linha o
        # dispatcher procura um header que nunca chega e devolve 403.
        signature_header='Authorization',
        handler_class='apps.webhooks.handlers.pagarme_handler.PagarmeHandler',
        is_active=True,
    ),
)
print(f'{"CRIADO" if criado else "ATUALIZADO"}: provider=pagarme '
      f'header={endpoint.signature_header} ativo={endpoint.is_active} '
      f'secret={len(endpoint.secret)} chars')
print('\nAgora confira que a porta abre (deve dar 200, nao 403):')
print("  curl -s -o /dev/null -w '%{http_code}\\n' -X POST \\")
print('    -H "Content-Type: application/json" \\')
print('    -u "$PAGARME_WEBHOOK_USER:$PAGARME_WEBHOOK_PASS" \\')
print("""    -d '{"type":"charge.paid","data":{"id":"or_inexistente"}}' \\""")
print('    https://backend.pastita.com.br/webhooks/v1/pagarme/')
