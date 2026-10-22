"""As `{variáveis}` das mensagens prontas: um lugar só para preencher.

Até 22/10/2026 cada envio (bot, lembrete de PIX, carrinho, avaliação, teste
do painel) trocava o seu próprio punhado de chaves, e o painel oferecia todas
para qualquer mensagem. A Cê escreveu {website_url} na mensagem fora de
horário e o cliente recebeu as chaves cruas.

Regra: o que é da loja (nome, link, horário de hoje) entra em qualquer envio;
o que é do momento (pedido, PIX, carrinho) vem do contexto de quem envia; e
variável que o painel oferece mas não tem dado neste envio vira vazio — nunca
sai crua. Chave que o painel não conhece fica como está, para o dono ver o erro
de digitação na prévia. Lista espelhada em
`pastita-dash/src/utils/variaveisDeMensagem.ts`.
"""
import logging
import re

from django.utils import timezone

logger = logging.getLogger(__name__)

VARIAVEIS_CONHECIDAS = frozenset({
    # loja
    'customer_name', 'company_name', 'store_name', 'website_url', 'menu_url',
    'business_hours_today',
    # conversa
    'phone_number', 'phone', 'order_id',
    # carrinho
    'cart_items', 'cart_total', 'cart_item_count',
    # pagamento
    'order_number', 'amount', 'pix_code', 'time_remaining',
    # pedido (textos_de_aviso.variaveis_do_pedido)
    'primeiro_nome', 'total', 'order_total', 'tempo', 'endereco',
    'entregue_ou_retirado', 'proximo_passo', 'order_status',
    # oferecidas pelo painel antigo
    'tracking_code', 'delivery_estimate', 'delivery_address',
    'discount_code', 'discount_percentage',
})

_DIAS = ('monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday')
_CHAVE = re.compile(r'\{(\w+)\}')


def variaveis_da_loja(perfil) -> dict:
    """Nome, link do cardápio e horário de hoje — valem para qualquer mensagem."""
    if perfil is None:
        return {}
    try:
        loja = perfil.get_effective_store()
    except Exception:
        loja = None
    try:
        link = perfil.link_do_cardapio() or ''
    except Exception:
        logger.warning('[variaveis] link do cardápio indisponível', exc_info=True)
        link = ''
    horario_hoje = ''
    if loja is not None:
        from apps.stores.services.horario_de_funcionamento import faixa_do_dia
        horarios = getattr(loja, 'operating_hours', None) or {}
        if isinstance(horarios, dict):
            horario_hoje = faixa_do_dia(horarios.get(_DIAS[timezone.localtime().weekday()]) or {})
    nome_loja = getattr(loja, 'name', '') if loja is not None else ''
    return {
        'company_name': getattr(perfil, 'company_name', '') or nome_loja,
        'store_name': nome_loja or getattr(perfil, 'company_name', ''),
        'website_url': link,
        'menu_url': link,
        'business_hours_today': horario_hoje,
    }


def preencher(texto: str, contexto: dict, perfil=None) -> str:
    """Troca as chaves: contexto do envio > dados da loja > vazio."""
    valores = {k: v for k, v in variaveis_da_loja(perfil).items() if v not in (None, '')}
    valores.update({k: v for k, v in (contexto or {}).items() if v not in (None, '')})

    def _troca(m):
        chave = m.group(1)
        if chave in valores:
            return str(valores[chave])
        if chave in VARIAVEIS_CONHECIDAS:
            return ''
        return m.group(0)

    return _CHAVE.sub(_troca, texto or '')
