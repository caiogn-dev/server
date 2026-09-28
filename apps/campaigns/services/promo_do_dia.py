"""Promoção do dia, todo dia, sem o dono ter que criar a campanha à mão.

Medido em 28/09: a Cê Saladas mandou a "oferta do dia" de 16 a 24/09 — cada
uma criada à mão pelo dono no painel (modelo aprovado + card no cabeçalho +
produtos da oferta) — e parou no dia 24 porque ele parou. Nada era automático.

Aqui a loja configura uma vez (`store.metadata['promo_do_dia']`) e o beat
cria a campanha do dia sozinho, com o card daquele dia da semana:

    {
      'ativo': True,
      'hora': '18:00',            # hora local da loja em que a campanha nasce
      'para': sempre 'amanha'     # às 18h de segunda sai a promoção de TERÇA (28/09: 'hoje' não faz sentido)
      'modo': 'janela' | 'modelo',# grátis para quem falou em 24h | modelo pago p/ todos
      'modelo': 'ce_saladas_oferta_do_dia',   # nome do template aprovado (modo modelo)
      'cards': {'0': url, ..., '6': url},      # imagem por dia da semana da PROMOÇÃO
      'texto': '...',             # modo janela; {nome} {dia} {loja} {ofertas} {cardapio}
    }

Dia sem promoção cadastrada = nada sai. Uma campanha por loja por dia-alvo
(marca em `Campaign.metadata['promo_do_dia']`).
"""
import logging
import re
from datetime import timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.utils import timezone

logger = logging.getLogger(__name__)

CHAVE = 'promo_do_dia'
DIAS_PT = ('segunda', 'terça', 'quarta', 'quinta', 'sexta', 'sábado', 'domingo')
TEXTO_PADRAO = (
    "Oi, {nome}! 🥗\n\n{dia} tem oferta na {loja}:\n\n{ofertas}\n\n"
    "Peça pelo cardápio: {cardapio}"
)
PADRAO = {'ativo': False, 'hora': '18:00', 'para': 'amanha', 'modo': 'janela', 'modelo': '', 'cards': {}, 'texto': TEXTO_PADRAO}


def config(store) -> dict:
    bruto = (getattr(store, 'metadata', None) or {}).get(CHAVE) or {}
    cfg = {**PADRAO, **{k: v for k, v in bruto.items() if k in PADRAO}}
    if not isinstance(cfg.get('cards'), dict):
        cfg['cards'] = {}
    # 28/09: a loja ficou em 'hoje' e às 17h saiu a promoção de segunda. Não
    # existe caso para isso — a véspera é a regra.
    cfg['para'] = 'amanha'
    if cfg['modo'] not in ('janela', 'modelo'):
        cfg['modo'] = 'janela'
    if not str(cfg.get('texto') or '').strip():
        cfg['texto'] = TEXTO_PADRAO
    return cfg


def _reais(valor) -> str:
    return f"R$ {Decimal(str(valor)):.2f}".replace('.', ',')


def ofertas(store, weekday: int) -> list:
    from apps.stores.models import StoreProduct

    return [
        {'nome': p.name, 'preco': _reais(p.promo_price), 'de': _reais(p.price)}
        for p in StoreProduct.disponiveis(store).exclude(tags__contains=['ingrediente'])
        .filter(promo_weekday=weekday).exclude(promo_price__isnull=True).order_by('sort_order', 'name')
        if p.promo_price < p.price
    ]


def fuso(store):
    try:
        return ZoneInfo(getattr(store, 'timezone', '') or 'America/Sao_Paulo')
    except Exception:
        return ZoneInfo('America/Sao_Paulo')


def montar(store, agora=None) -> dict | None:
    """O que sai hoje: dia-alvo, ofertas, card e texto. None se não há promoção."""
    from apps.agents.services.contexto_da_loja import link_do_cardapio

    cfg = config(store)
    agora = agora or timezone.now()
    local = agora.astimezone(fuso(store))
    alvo = local.date() + (timedelta(days=1) if cfg['para'] == 'amanha' else timedelta())
    weekday = alvo.weekday()
    itens = ofertas(store, weekday)
    if not itens:
        return None
    quando = ('Amanhã' if cfg['para'] == 'amanha' else 'Hoje') + f" ({DIAS_PT[weekday]})"
    # O motor de campanha personaliza com chaves DUPLAS ({{nome}}); com uma
    # chave o cliente recebia "Oi, {nome}!" literalmente (28/09).
    texto = cfg['texto'].format(
        nome='{{nome}}', dia=quando, loja=store.name,
        ofertas="\n".join(f"• {o['nome']} — *{o['preco']}* (de {o['de']})" for o in itens),
        cardapio=link_do_cardapio(store),
    )
    return {
        'dia': alvo.isoformat(), 'weekday': weekday, 'quando': quando, 'ofertas': itens,
        'card': (cfg['cards'].get(str(weekday)) or '').strip(), 'texto': texto, 'modo': cfg['modo'],
    }


def _variaveis_do_modelo(template) -> list:
    corpo = next((c.get('text') or '' for c in (template.components or []) if str(c.get('type', '')).upper() == 'BODY'), '')
    vistas = []
    for nome in re.findall(r'\{\{\s*([A-Za-z0-9_]+)\s*\}\}', corpo):
        if nome not in vistas:
            vistas.append(nome)
    return vistas


def _tem_cabecalho_de_imagem(template) -> bool:
    return any(
        str(c.get('type', '')).upper() == 'HEADER' and str(c.get('format', '')).upper() == 'IMAGE'
        for c in (template.components or [])
    )


def _contatos(store) -> list:
    from .contatos import coletar_por_loja, contatos_para_resposta

    return contatos_para_resposta(coletar_por_loja([store.id]), 100000)


def ja_saiu(store, dia_iso: str) -> bool:
    from apps.campaigns.models import Campaign

    return Campaign.objects.filter(
        account_id=store.whatsapp_account_id, metadata__promo_do_dia=dia_iso,
    ).exclude(status=Campaign.CampaignStatus.CANCELLED).exists()


def disparar(store, agora=None, forcar=False, criado_por=None):
    """Cria (e inicia) a campanha do dia. Devolve (campanha | None, motivo)."""
    from apps.campaigns.models import Campaign
    from apps.campaigns.services.campaign_service import CampaignService
    from apps.whatsapp.models import MessageTemplate

    agora = agora or timezone.now()
    cfg = config(store)
    if not cfg['ativo'] and not forcar:
        return None, 'desligado'
    if not store.whatsapp_account_id:
        return None, 'sem_whatsapp'
    plano = montar(store, agora)
    if plano is None:
        return None, 'sem_promocao'
    if ja_saiu(store, plano['dia']):
        return None, 'ja_saiu'
    contatos = _contatos(store)
    if not contatos:
        return None, 'sem_contatos'

    nome = f"Promoção do dia — {plano['quando']} {plano['dia']}"
    servico = CampaignService()
    modo = cfg['modo']
    template = None
    if modo == 'modelo':
        template = MessageTemplate.objects.filter(
            account_id=store.whatsapp_account_id, name=cfg['modelo'], is_active=True,
            status=MessageTemplate.TemplateStatus.APPROVED,
        ).first()
        if template is None or (_tem_cabecalho_de_imagem(template) and not plano['card']):
            logger.warning('promo_do_dia %s: modelo %r indisponível ou sem card — caindo para texto na janela', store.slug, cfg['modelo'])
            modo = 'janela'

    if modo == 'modelo':
        variaveis = _variaveis_do_modelo(template)
        componentes = []
        if _tem_cabecalho_de_imagem(template):
            componentes.append({'type': 'header', 'parameters': [{'type': 'image', 'image': {'link': plano['card']}}]})
        if variaveis:
            componentes.append({'type': 'body', 'parameters': [
                {'type': 'text', 'text': '', 'variable': v, 'parameter_name': v} for v in variaveis
            ]})
        base = {}
        for i, o in enumerate(plano['ofertas'][:5], start=1):
            base[f'produto_{i}'] = o['nome']
            base[f'preco_{i}'] = o['preco']
        for v in variaveis:
            base.setdefault(v, '')
        lista = [{
            'phone': c['phone'], 'name': c['name'],
            'variables': {**base, 'nome_cliente': (c['name'] or '').strip() or 'Cliente', 'nome': (c['name'] or '').strip() or 'Cliente'},
        } for c in contatos]
        campanha = servico.create_campaign(
            account_id=str(store.whatsapp_account_id), name=nome, template_id=str(template.id),
            message_content={'components': componentes, 'image_url': plano['card'], 'media_url': plano['card'], 'language': template.language},
            contact_list=lista, created_by=criado_por,
        )
        campanha.metadata = {**(campanha.metadata or {}), 'promo_do_dia': plano['dia'], 'modo': 'modelo', 'store_id': str(store.id)}
        campanha.save(update_fields=['metadata'])
        servico.start_campaign(str(campanha.id))
        campanha.refresh_from_db()
        return campanha, 'modelo'

    lista = [{'phone': c['phone'], 'name': c['name'], 'variables': {'nome': (c['name'] or '').strip() or 'você'}} for c in contatos]
    conteudo = {'text': plano['texto']}
    if plano['card']:
        conteudo.update({'media_url': plano['card'], 'image_url': plano['card'], 'media_type': 'image'})
    campanha = servico.create_campaign(
        account_id=str(store.whatsapp_account_id), name=nome, message_content=conteudo,
        contact_list=lista, scheduled_at=agora, created_by=criado_por,
    )
    campanha.metadata = {**(campanha.metadata or {}), 'promo_do_dia': plano['dia'], 'modo': 'janela', 'store_id': str(store.id)}
    campanha.status = Campaign.CampaignStatus.SCHEDULED
    campanha.save(update_fields=['metadata', 'status', 'updated_at'])
    return campanha, 'janela'


def esta_na_hora(store, agora=None) -> bool:
    """Passou da hora configurada hoje (hora local), dentro de 3 h de tolerância."""
    cfg = config(store)
    agora = agora or timezone.now()
    local = agora.astimezone(fuso(store))
    try:
        h, m = (int(x) for x in str(cfg['hora']).split(':')[:2])
    except (TypeError, ValueError):
        h, m = 18, 0
    inicio = local.replace(hour=h, minute=m, second=0, microsecond=0)
    return inicio <= local < inicio + timedelta(hours=3)


def rodar_para_todas(agora=None) -> list:
    """Uma passada do beat: dispara nas lojas ligadas cuja hora chegou."""
    from apps.stores.models import Store

    agora = agora or timezone.now()
    saida = []
    for loja in Store.objects.filter(is_active=True, status='active').exclude(whatsapp_account=None):
        try:
            if not config(loja)['ativo'] or not esta_na_hora(loja, agora):
                continue
            campanha, motivo = disparar(loja, agora)
            saida.append((loja.slug, motivo, str(campanha.id) if campanha else None))
        except Exception:
            logger.exception('promo_do_dia falhou na loja %s', loja.slug)
            saida.append((loja.slug, 'erro', None))
    return saida
