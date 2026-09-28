"""Recuperador de vendas no WhatsApp: quem perguntou e sumiu, e quem deixou o carrinho.

Medido em 28/09 (Cê Saladas, 30 dias): 186 conversas, 10 pedidos. Das que não
viraram pedido, a maior parte "só perguntou" — e ninguém voltava a falar com
elas. O lembrete de carrinho já existia; faltava o de quem perguntou e a
promoção do dia nos dois.

Configuração em `store.metadata['recuperador']`:

    {
      'carrinho':  {'incluir_oferta': True},          # o lembrete de 2 h cita a promoção de hoje
      'perguntou': {'ativo': False, 'apos_horas': 3,   # quem falou e sumiu recebe um texto
                    'texto': '...'},                   # {nome} {oferta}
    }

Só sai texto livre dentro da janela de 24 h, nunca em modo humano, nunca para
quem pediu para parar (a política do canal cuida), e uma vez por conversa
(marca em `Conversation.context['recuperador_perguntou_em']`).
"""
import logging
from datetime import timedelta

from django.utils import timezone

logger = logging.getLogger(__name__)

CHAVE = 'recuperador'
TEXTO_PADRAO_PERGUNTOU = (
    "Oi, {nome}! Ficou alguma dúvida? Se quiser, eu já monto seu pedido por aqui. 😊{oferta}"
)
PADRAO = {
    'carrinho': {'incluir_oferta': True},
    'perguntou': {'ativo': False, 'apos_horas': 3, 'texto': TEXTO_PADRAO_PERGUNTOU},
}
#: Quem falou há mais tempo que isto além de `apos_horas` não recebe: virou
#: cobrança, e provavelmente a janela já fechou.
TOLERANCIA_HORAS = 6


def config(store) -> dict:
    bruto = (getattr(store, 'metadata', None) or {}).get(CHAVE) or {}
    carrinho = {**PADRAO['carrinho'], **(bruto.get('carrinho') or {})}
    perguntou = {**PADRAO['perguntou'], **(bruto.get('perguntou') or {})}
    try:
        perguntou['apos_horas'] = max(1, min(int(perguntou.get('apos_horas') or 3), 20))
    except (TypeError, ValueError):
        perguntou['apos_horas'] = 3
    if not str(perguntou.get('texto') or '').strip():
        perguntou['texto'] = TEXTO_PADRAO_PERGUNTOU
    return {'carrinho': carrinho, 'perguntou': perguntou}


def linha_da_oferta(store, agora=None) -> str:
    """"Hoje tem X por R$ Y (de R$ Z)." — ou vazio quando hoje não tem promoção."""
    from apps.campaigns.services.promo_do_dia import fuso, ofertas

    agora = agora or timezone.now()
    itens = ofertas(store, agora.astimezone(fuso(store)).weekday())
    if not itens:
        return ''
    partes = ", ".join(f"{o['nome']} por {o['preco']} (de {o['de']})" for o in itens[:3])
    return f"\n\nHoje tem: {partes}."


def seguir_quem_so_perguntou(store, agora=None) -> int:
    """Manda um texto para quem falou com o bot, não pediu, e sumiu. Devolve quantos."""
    from apps.automation.models import CustomerSession
    from apps.automation.mensageiro import canal, janela
    from apps.campaigns.services.contatos import chave_do_telefone
    from apps.conversations.models import Conversation
    from apps.core.utils import primeiro_nome
    from apps.stores.models import StoreOrder

    cfg = config(store)['perguntou']
    conta = getattr(store, 'whatsapp_account', None)
    if not cfg['ativo'] or conta is None:
        return 0
    agora = agora or timezone.now()
    ate = agora - timedelta(hours=cfg['apos_horas'])
    desde = ate - timedelta(hours=TOLERANCIA_HORAS)

    candidatas = Conversation.objects.filter(
        account=conta, mode='auto', last_customer_message_at__gte=desde, last_customer_message_at__lte=ate,
    )
    pedidos = {
        chave_do_telefone(t) for t in StoreOrder.objects.filter(store=store, created_at__gte=desde)
        .values_list('customer_phone', flat=True)
    }
    com_carrinho = {
        chave_do_telefone(t) for t in CustomerSession.objects.filter(
            company__store=store, updated_at__gte=desde, cart_items_count__gt=0, order__isnull=True,
        ).values_list('phone_number', flat=True)
    }
    oferta = linha_da_oferta(store, agora)
    enviados = 0
    for conversa in candidatas:
        chave = chave_do_telefone(conversa.phone_number)
        marca = (conversa.context or {}).get('recuperador_perguntou_em')
        if marca and marca >= conversa.last_customer_message_at.isoformat():
            continue
        if chave in pedidos or chave in com_carrinho:
            continue
        if not janela.aberta(conta, conversa.phone_number, agora):
            continue
        texto = cfg['texto'].format(nome=primeiro_nome(conversa.contact_name, 'tudo bem'), oferta=oferta)
        mensagem = canal.enviar_texto(conta, conversa.phone_number, texto, evento='recuperador_perguntou')
        conversa.context = {**(conversa.context or {}), 'recuperador_perguntou_em': agora.isoformat()}
        conversa.save(update_fields=['context', 'updated_at'])
        if mensagem is not None:
            enviados += 1
    return enviados


def rodar_para_todas(agora=None) -> dict:
    from apps.stores.models import Store

    agora = agora or timezone.now()
    saida = {}
    for loja in Store.objects.filter(is_active=True, status='active').exclude(whatsapp_account=None):
        if not config(loja)['perguntou']['ativo']:
            continue
        try:
            saida[loja.slug] = seguir_quem_so_perguntou(loja, agora)
        except Exception:
            logger.exception('recuperador falhou na loja %s', loja.slug)
    return saida
