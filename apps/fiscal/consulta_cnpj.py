"""Cadastro público do CNPJ (Receita, via BrasilAPI) para preencher o destinatário.

É atalho de digitação, não fonte de verdade: o operador confere e corrige —
o sindicato que motivou isto tinha no pedido um endereço diferente do da Receita.
"""
import logging

import requests
from django.core.cache import cache

from .documents import limpar

logger = logging.getLogger(__name__)

URL = 'https://brasilapi.com.br/api/cnpj/v1/{cnpj}'
# Reserva: a BrasilAPI deu 429 em 28/10 e o painel ficou sem consulta.
URL_RESERVA = 'https://publica.cnpj.ws/cnpj/{cnpj}'
UM_DIA = 60 * 60 * 24


class ConsultaIndisponivel(Exception):
    pass


def _titulo(valor) -> str:
    return ' '.join(str(valor or '').split())


def consultar_cnpj(cnpj: str) -> dict | None:
    """Destinatário no formato do formulário, ou None se o CNPJ não existe."""
    cnpj = limpar(cnpj)
    chave = f'fiscal:cnpj:{cnpj}'
    guardado = cache.get(chave)
    if guardado is not None:
        return guardado

    try:
        resp = requests.get(URL.format(cnpj=cnpj), timeout=8)
    except requests.RequestException as exc:
        logger.warning('consulta de CNPJ falhou: %s', type(exc).__name__)
        resp = None

    if resp is not None and resp.status_code == 404:
        return None
    if resp is not None and resp.status_code == 200:
        resultado = _da_brasilapi(cnpj, resp.json())
    else:
        if resp is not None:
            logger.warning('consulta de CNPJ respondeu %s', resp.status_code)
        resultado = _da_reserva(cnpj)
        if resultado is None:
            return None
    cache.set(chave, resultado, UM_DIA)
    return resultado


def _da_brasilapi(cnpj: str, dados: dict) -> dict:
    logradouro = ' '.join(
        p for p in [_titulo(dados.get('descricao_tipo_de_logradouro')), _titulo(dados.get('logradouro'))] if p
    )
    return {
        'documento': cnpj,
        'nome': _titulo(dados.get('razao_social')),
        'nome_fantasia': _titulo(dados.get('nome_fantasia')),
        'situacao': _titulo(dados.get('descricao_situacao_cadastral')),
        'email': _titulo(dados.get('email')).lower(),
        'telefone': limpar(str(dados.get('ddd_telefone_1') or '')),
        'endereco': {
            'street': logradouro,
            'number': _titulo(dados.get('numero')),
            'complement': _titulo(dados.get('complemento')),
            'neighborhood': _titulo(dados.get('bairro')),
            'city': _titulo(dados.get('municipio')),
            'state': _titulo(dados.get('uf')).upper(),
            'zip_code': limpar(str(dados.get('cep') or '')),
        },
    }


def _da_reserva(cnpj: str) -> dict | None:
    """CNPJ.ws (publica.cnpj.ws): mesmo cadastro da Receita, outro formato."""
    try:
        resp = requests.get(URL_RESERVA.format(cnpj=cnpj), timeout=8)
    except requests.RequestException as exc:
        logger.warning('consulta de CNPJ (reserva) falhou: %s', type(exc).__name__)
        raise ConsultaIndisponivel() from exc
    if resp.status_code == 404:
        return None
    if resp.status_code != 200:
        logger.warning('consulta de CNPJ (reserva) respondeu %s', resp.status_code)
        raise ConsultaIndisponivel()

    dados = resp.json()
    est = dados.get('estabelecimento') or {}
    logradouro = ' '.join(p for p in [_titulo(est.get('tipo_logradouro')), _titulo(est.get('logradouro'))] if p)
    return {
        'documento': cnpj,
        'nome': _titulo(dados.get('razao_social')),
        'nome_fantasia': _titulo(est.get('nome_fantasia')),
        'situacao': _titulo(est.get('situacao_cadastral')),
        'email': _titulo(est.get('email')).lower(),
        'telefone': limpar(f"{est.get('ddd1') or ''}{est.get('telefone1') or ''}"),
        'endereco': {
            'street': logradouro,
            'number': _titulo(est.get('numero')),
            'complement': _titulo(est.get('complemento')),
            'neighborhood': _titulo(est.get('bairro')),
            'city': _titulo((est.get('cidade') or {}).get('nome')),
            'state': _titulo((est.get('estado') or {}).get('sigla')).upper(),
            'zip_code': limpar(str(est.get('cep') or '')),
        },
    }
