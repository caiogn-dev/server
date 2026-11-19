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
from datetime import timedelta

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


def _pausas(dados) -> list:
    return [
        {'id': str(p.get('id') or ''), 'motivo': str(p.get('description') or ''),
         'inicio': str(p.get('start') or ''), 'fim': str(p.get('end') or '')}
        for p in (dados or []) if isinstance(p, dict)
    ]


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


def resumo(store) -> dict:
    return {
        'status': _status(_chamar(store, 'GET', '/status')),
        'pausas': _pausas(_chamar(store, 'GET', '/interruptions')),
        'horarios': _horarios(_chamar(store, 'GET', '/opening-hours')),
    }


# ── operações ────────────────────────────────────────────────────────────

def pausar(store, minutos: int, motivo: str = ''):
    try:
        minutos = int(minutos)
    except (TypeError, ValueError):
        raise LojaNoIfoodErro('Tempo de pausa inválido.')
    if not 1 <= minutos <= PAUSA_MAX_MIN:
        raise LojaNoIfoodErro('Pausa entre 1 minuto e 7 dias.')
    inicio = timezone.now().replace(microsecond=0)
    _chamar(store, 'POST', '/interruptions', {
        'id': str(uuid.uuid4()),
        'description': (motivo or 'Pausa pelo Cardapidex')[:100],
        'start': inicio.isoformat(),
        'end': (inicio + timedelta(minutes=minutos)).isoformat(),
    })


def retomar(store, pausa_id: str):
    pausa_id = str(pausa_id or '').strip()
    if not pausa_id or '/' in pausa_id:
        raise LojaNoIfoodErro('Pausa inválida.')
    _chamar(store, 'DELETE', f'/interruptions/{pausa_id}')


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
    _chamar(store, 'PUT', '/opening-hours', {'storeId': _merchant(store), 'shifts': turnos})
