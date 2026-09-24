"""Modelo de utilidade `aviso_de_pedido`: o aviso de status fora da janela.

De 21 a 24/09/2026, 40% dos "pedido confirmado" falharam com 131047 — o
cliente pediu pelo SITE e nunca conversou com a loja, então não existe
janela de 24 h para texto livre. A Meta aceita, fora da janela, um modelo
de UTILIDADE aprovado. Este é o único modelo de status: nome, número do
pedido, loja e a frase do status entram como variáveis.

O texto livre da loja (personalizável no painel) continua sendo o caminho
normal; o modelo é a saída quando o texto não passaria.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

NOME_DO_MODELO = 'aviso_de_pedido'
IDIOMA = 'pt_BR'

# Corpo enviado à Meta. Variável não pode ter quebra de linha (erro 132018).
CORPO = (
    'Olá {{1}}! Sobre o seu pedido {{2}} na {{3}}: {{4}}\n\n'
    'Se precisar de algo, é só responder esta mensagem.'
)
EXEMPLO = ['Maria', 'CE-2609240001', 'Cê Saladas', 'está sendo preparado 👨‍🍳']

# evento (como o canal recebe) → frase que completa "Sobre o seu pedido X na Loja: …"
FRASES = {
    'order_processing': 'está sendo processado ⏳',
    'order_confirmed': 'foi confirmado e logo começaremos a preparar ✅',
    'order_paid': 'teve o pagamento confirmado 💰',
    'order_preparing': 'está sendo preparado 👨‍🍳',
    'order_ready': 'está pronto 📦',
    'order_shipped': 'foi enviado 🚚',
    'order_out_for_delivery': 'saiu para entrega — fique de olho 🛵',
    'order_delivered': 'foi entregue. Obrigado pela preferência! 🌟',
    'order_completed': 'foi finalizado. Obrigado pela compra! ✨',
    'order_cancelled': 'foi cancelado ❌',
    'order_refunded': 'foi reembolsado 💳',
}


def modelo_aprovado(conta):
    from apps.whatsapp.models import MessageTemplate

    return MessageTemplate.objects.filter(
        account=conta, name=NOME_DO_MODELO, language=IDIOMA, is_active=True,
        status=MessageTemplate.TemplateStatus.APPROVED,
    ).first()


def _texto(valor: str) -> str:
    return ' '.join(str(valor or '').split())  # sem \n nem \t, que a Meta recusa


def componentes(nome_cliente: str, numero_pedido: str, loja: str, frase: str) -> list[dict]:
    return [{'type': 'body', 'parameters': [
        {'type': 'text', 'text': _texto(nome_cliente) or 'Cliente'},
        {'type': 'text', 'text': _texto(numero_pedido)},
        {'type': 'text', 'text': _texto(loja)},
        {'type': 'text', 'text': _texto(frase)},
    ]}]


def _nome_da_loja(conta, extra: dict) -> str:
    from apps.stores.models import Store

    loja = Store.objects.filter(whatsapp_account=conta).only('name').first()
    return loja.name if loja else (conta.name or '')


def enviar_aviso_de_pedido(conta, telefone: str, evento: str, extra: dict | None, metadata: dict):
    """Manda o aviso pelo modelo. Devolve a mensagem, ou `None` quando não há
    modelo aprovado nesta conta (aí o canal segue com o texto, como antes)."""
    from apps.whatsapp.services.message_service import MessageService

    if evento not in FRASES or not modelo_aprovado(conta):
        return None
    extra = extra or {}
    return MessageService().send_template_message(
        account_id=str(conta.id), to=telefone, template_name=NOME_DO_MODELO, language_code=IDIOMA,
        components=componentes(
            extra.get('customer_name', ''), extra.get('order_number', ''),
            _nome_da_loja(conta, extra), FRASES[evento],
        ),
        metadata={**metadata, 'por_modelo': True},
    )


def criar_na_meta(conta):
    """Registra o modelo na WABA da conta e grava a linha local. Idempotente:
    se já existe (em qualquer status), devolve a linha sem chamar a Meta. O
    status final chega pelo webhook/sync de templates, como os outros."""
    from apps.whatsapp.models import MessageTemplate
    from apps.whatsapp.services.whatsapp_api_service import WhatsAppAPIService

    existente = MessageTemplate.objects.filter(account=conta, name=NOME_DO_MODELO, language=IDIOMA).first()
    if existente:
        return existente

    resposta = WhatsAppAPIService(conta)._make_request(  # noqa: SLF001 — não há wrapper de criação
        'POST', f'{conta.waba_id}/message_templates', data={
            'name': NOME_DO_MODELO,
            'language': IDIOMA,
            'category': 'UTILITY',
            'components': [{'type': 'BODY', 'text': CORPO, 'example': {'body_text': [EXEMPLO]}}],
        },
    )
    linha = MessageTemplate.objects.create(
        account=conta, template_id=str(resposta.get('id', '')), name=NOME_DO_MODELO, language=IDIOMA,
        category=MessageTemplate.TemplateCategory.UTILITY,
        status=str(resposta.get('status', 'pending')).lower(),
        components=[{'type': 'BODY', 'text': CORPO}],
    )
    logger.info('Modelo %s criado na conta %s: %s', NOME_DO_MODELO, conta.id, linha.status)
    return linha
