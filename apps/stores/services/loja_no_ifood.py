"""Módulo Merchant do iFood: status, pausas e horário da loja no iFood.

Usa o app de pedidos quando ele tem credencial; senão o de entregas (os dois
são centralizados e enxergam a mesma loja depois da aprovação no portal).

    status         GET    /merchant/v1.0/merchants/{m}/status
    pausas         GET    /merchant/v1.0/merchants/{m}/interruptions
    pausar         POST   /merchant/v1.0/merchants/{m}/interruptions
    retomar        DELETE /merchant/v1.0/merchants/{m}/interruptions/{id}
    horários       GET    /merchant/v1.0/merchants/{m}/opening-hours
    salvar         PUT    /merchant/v1.0/merchants/{m}/opening-hours

Horário: o iFood guarda turno como início + duração em minutos; o painel
trabalha com início/fim. Turno que passa da meia-noite não é aceito aqui
(fim tem que ser depois do início no mesmo dia).
"""
from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timedelta
from datetime import timezone as dt_timezone
from zoneinfo import ZoneInfo

from django.utils import timezone

from . import ifood_oauth

DIAS = ('MONDAY', 'TUESDAY', 'WEDNESDAY', 'THURSDAY', 'FRIDAY', 'SATURDAY', 'SUNDAY')
PAUSA_MAX_MIN = 60 * 24 * 7
_HORA = re.compile(r'^([01]\d|2[0-3]):([0-5]\d)(?::[0-5]\d)?$')


class LojaNoIfoodErro(Exception):
    pass


def _app() -> str:
    for app in ('pedidos', 'entregas'):
        if ifood_oauth.esta_configurado(app):
            return app
    raise LojaNoIfoodErro('iFood não configurado na plataforma.')


def _merchant(store) -> str:
    from apps.stores.models import StoreIfoodIntegration
    integracao = StoreIfoodIntegration.objects.filter(store=store).first()
    if integracao is None or not integracao.merchant_id:
        raise LojaNoIfoodErro('Informe o ID da loja no iFood.')
    return integracao.merchant_id


def _chamar(store, metodo, sufixo='', corpo=None):
    caminho = f'/merchant/v1.0/merchants/{_merchant(store)}{sufixo}'
    try:
        return ifood_oauth.api(_app(), metodo, caminho, corpo=corpo)
    except ifood_oauth.IfoodNaoConfigurado as exc:
        raise LojaNoIfoodErro('iFood não configurado na plataforma.') from exc
    except ifood_oauth.IfoodRecusou as exc:
        mensagem = ''
        try:
            dados = json.loads(exc.corpo or '{}')
            if isinstance(dados, dict):
                dados = dados.get('error') if isinstance(dados.get('error'), dict) else dados
                mensagem = str(dados.get('message') or '')
        except ValueError:
            pass
        if exc.status in (401, 403):
            mensagem = 'Aprove o app Cardapidex no Portal do Parceiro do iFood.'
        raise LojaNoIfoodErro((mensagem or str(exc))[:300]) from exc


# ── leitura ──────────────────────────────────────────────────────────────

def _status(dados) -> dict:
    itens = dados if isinstance(dados, list) else ([dados] if isinstance(dados, dict) else [])
    if not itens:
        return {'estado': '', 'aberta': False, 'titulo': '', 'detalhe': ''}
    # Delivery manda; sem ele, o primeiro canal.
    item = next((i for i in itens if str(i.get('operation') or '').lower() == 'delivery'), itens[0])
    mensagem = item.get('message') or {}
    return {
        'estado': str(item.get('state') or '').upper(),
        'aberta': bool(item.get('available')) or str(item.get('state') or '').upper() == 'OK',
        'titulo': str(mensagem.get('title') or ''),
        'detalhe': str(mensagem.get('subtitle') or mensagem.get('description') or ''),
    }


_COM_FUSO = re.compile(r'(Z|[+-]\d{2}:?\d{2})$')


#: Medido ao vivo 20/11: o iFood LÊ e DEVOLVE a hora da pausa no horário de
#: Brasília, SEM fuso. Pausa mandada em UTC só começava 3 h depois.
FUSO_DO_IFOOD = ZoneInfo('America/Sao_Paulo')
_FMT_UTC = '%Y-%m-%dT%H:%M:%SZ'


def _para_ifood(momento) -> str:
    return momento.astimezone(FUSO_DO_IFOOD).replace(tzinfo=None).isoformat()


def _utc(valor) -> str:
    """Hora sem fuso do iFood (Brasília) → UTC com Z, que o painel converte certo."""
    texto = str(valor or '')
    if not texto:
        return texto
    if _COM_FUSO.search(texto):
        return texto
    try:
        local = datetime.fromisoformat(texto).replace(tzinfo=FUSO_DO_IFOOD)
    except ValueError:
        return texto
    return local.astimezone(dt_timezone.utc).strftime(_FMT_UTC)


def _pausas(dados) -> list:
    return [
        {'id': str(p.get('id') or ''), 'motivo': str(p.get('description') or ''),
         'inicio': _utc(p.get('start')), 'fim': _utc(p.get('end'))}
        for p in (dados or []) if isinstance(p, dict)
    ]


#: Pausa recém-criada some do GET /interruptions por alguns segundos (medido
#: ao vivo). Guardamos por 2 min para o painel mostrar na hora.
_RECENTES_S = 120


def _chave_recentes(store) -> str:
    return f'ifood:pausas-recentes:{_merchant(store)}'


def _hhmm(minutos: int) -> str:
    minutos = max(0, min(int(minutos), 24 * 60 - 1))
    return f'{minutos // 60:02d}:{minutos % 60:02d}'


def _minutos(hora: str) -> int:
    casou = _HORA.match(str(hora or '').strip())
    if not casou:
        raise LojaNoIfoodErro(f'Horário inválido: {hora}.')
    return int(casou.group(1)) * 60 + int(casou.group(2))


def _horarios(dados) -> list:
    turnos = (dados or {}).get('shifts') if isinstance(dados, dict) else None
    saida = []
    for t in turnos or []:
        try:
            inicio = _minutos(t.get('start'))
        except LojaNoIfoodErro:
            continue
        saida.append({'dia': str(t.get('dayOfWeek') or '').upper(), 'inicio': _hhmm(inicio),
                      'fim': _hhmm(inicio + int(t.get('duration') or 0))})
    ordem = {d: i for i, d in enumerate(DIAS)}
    return sorted(saida, key=lambda t: (ordem.get(t['dia'], 9), t['inicio']))


def _com_recentes(store, pausas: list) -> list:
    from django.core.cache import cache
    ids = {p['id'] for p in pausas}
    agora = timezone.now().isoformat()
    recentes = [p for p in (cache.get(_chave_recentes(store)) or [])
                if p['id'] not in ids and p['fim'] > agora[:19]]
    return pausas + recentes


def resumo(store) -> dict:
    return {
        'status': _status(_chamar(store, 'GET', '/status')),
        'pausas': _com_recentes(store, _pausas(_chamar(store, 'GET', '/interruptions'))),
        'horarios': _horarios_recentes(store) or _horarios(_chamar(store, 'GET', '/opening-hours')),
    }


def _chave_horarios(store) -> str:
    return f'ifood:horarios-recentes:{_merchant(store)}'


def _horarios_recentes(store):
    """Grade recém-salva. Medido ao vivo 20/11: o PUT responde 201 já com a
    grade nova, mas o GET /opening-hours só reflete 3–15 s depois — o painel
    relia logo após salvar e "desfazia" a mudança na tela."""
    from django.core.cache import cache
    return cache.get(_chave_horarios(store))


# ── operações ────────────────────────────────────────────────────────────

def pausar(store, minutos: int, motivo: str = ''):
    try:
        minutos = int(minutos)
    except (TypeError, ValueError):
        raise LojaNoIfoodErro('Tempo de pausa inválido.')
    if not 1 <= minutos <= PAUSA_MAX_MIN:
        raise LojaNoIfoodErro('Pausa entre 1 minuto e 7 dias.')
    from django.core.cache import cache
    inicio = timezone.now().replace(microsecond=0)
    fim = inicio + timedelta(minutes=minutos)
    corpo = {
        'id': str(uuid.uuid4()),
        'description': (motivo or 'Pausa pelo Cardapidex')[:100],
        'start': _para_ifood(inicio),
        'end': _para_ifood(fim),
    }
    criada = _chamar(store, 'POST', '/interruptions', corpo)
    # O iFood ignora o id mandado e cria outro; remover pelo nosso dá 404.
    pausa_id = str(criada.get('id') or '') if isinstance(criada, dict) else ''
    pausa = {'id': pausa_id or corpo['id'], 'motivo': corpo['description'],
             'inicio': inicio.astimezone(dt_timezone.utc).strftime(_FMT_UTC),
             'fim': fim.astimezone(dt_timezone.utc).strftime(_FMT_UTC)}
    chave = _chave_recentes(store)
    cache.set(chave, (cache.get(chave) or []) + [pausa], timeout=_RECENTES_S)
    return pausa


def retomar(store, pausa_id: str):
    pausa_id = str(pausa_id or '').strip()
    if not pausa_id or '/' in pausa_id:
        raise LojaNoIfoodErro('Pausa inválida.')
    _chamar(store, 'DELETE', f'/interruptions/{pausa_id}')
    from django.core.cache import cache
    chave = _chave_recentes(store)
    cache.set(chave, [p for p in (cache.get(chave) or []) if p['id'] != pausa_id], timeout=_RECENTES_S)


def salvar_horarios(store, horarios: list):
    turnos = []
    for item in horarios or []:
        dia = str((item or {}).get('dia') or '').upper()
        if dia not in DIAS:
            raise LojaNoIfoodErro(f'Dia inválido: {item.get("dia")}.')
        inicio, fim = _minutos(item.get('inicio')), _minutos(item.get('fim'))
        if fim <= inicio:
            raise LojaNoIfoodErro('O fim do turno tem que ser depois do início.')
        turnos.append({'dayOfWeek': dia, 'start': f'{_hhmm(inicio)}:00', 'duration': fim - inicio})
    salvo = _chamar(store, 'PUT', '/opening-hours', {'storeId': _merchant(store), 'shifts': turnos})
    confirmado = _horarios(salvo if isinstance(salvo, dict) and salvo.get('shifts') else {'shifts': turnos})
    from django.core.cache import cache
    cache.set(_chave_horarios(store), confirmado, timeout=_RECENTES_S)


def lojas_do_app() -> list:
    """GET /merchants: as lojas que aprovaram o app (o painel oferece para escolher)."""
    try:
        dados = ifood_oauth.api(_app(), 'GET', '/merchant/v1.0/merchants', params={'page': 1, 'size': 100}) or []
    except ifood_oauth.IfoodRecusou as exc:
        raise LojaNoIfoodErro(str(exc)[:300]) from exc
    return [{'id': str(m.get('id') or ''), 'nome': str(m.get('name') or ''),
             'razao_social': str(m.get('corporateName') or '')}
            for m in dados if isinstance(m, dict) and m.get('id')]
