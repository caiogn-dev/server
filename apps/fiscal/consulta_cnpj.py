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
        raise ConsultaIndisponivel() from exc

    if resp.status_code == 404:
        return None
    if resp.status_code != 200:
        logger.warning('consulta de CNPJ respondeu %s', resp.status_code)
        raise ConsultaIndisponivel()

    dados = resp.json()
    logradouro = ' '.join(
        p for p in [_titulo(dados.get('descricao_tipo_de_logradouro')), _titulo(dados.get('logradouro'))] if p
    )
    resultado = {
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
    cache.set(chave, resultado, UM_DIA)
    return resultado
