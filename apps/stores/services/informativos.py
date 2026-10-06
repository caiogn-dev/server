"""Informativos — avisos da loja no cardápio ("fechado no feriado", "novo horário").

Guardados em `store.metadata['informativos']`, mas gravados SÓ por aqui: o
painel mandava o metadata inteiro da cópia do navegador e duas telas abertas
apagavam uma à outra. A vitrine recebe apenas o que está no ar agora.
"""
import uuid
from datetime import datetime

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

CHAVE = 'informativos'
MAX_INFORMATIVOS = 20
MAX_TITULO = 60
MAX_TEXTO = 280


class InformativoInvalido(ValueError):
    pass


def _data(valor, campo: str):
    if valor in (None, ''):
        return None
    quando = parse_datetime(str(valor)) if not isinstance(valor, datetime) else valor
    if quando is None:
        raise InformativoInvalido(f'Data inválida em "{campo}".')
    if timezone.is_naive(quando):
        quando = timezone.make_aware(quando)
    return quando


def estado(item: dict, agora=None) -> str:
    agora = agora or timezone.now()
    if not item.get('ativo', True):
        return 'pausado'
    inicio, fim = _data(item.get('inicio'), 'inicio'), _data(item.get('fim'), 'fim')
    if fim and fim <= agora:
        return 'encerrado'
    if inicio and inicio > agora:
        return 'agendado'
    return 'no_ar'


def _validar(dados: dict, atual: dict | None = None) -> dict:
    item = dict(atual or {})
    for campo in ('titulo', 'texto', 'inicio', 'fim', 'ativo'):
        if campo in dados:
            item[campo] = dados[campo]
    item['titulo'] = str(item.get('titulo') or '').strip()
    item['texto'] = str(item.get('texto') or '').strip()
    if not item['titulo'] and not item['texto']:
        raise InformativoInvalido('Escreva o título ou o texto do aviso.')
    if len(item['titulo']) > MAX_TITULO:
        raise InformativoInvalido(f'Título com no máximo {MAX_TITULO} caracteres.')
    if len(item['texto']) > MAX_TEXTO:
        raise InformativoInvalido(f'Texto com no máximo {MAX_TEXTO} caracteres.')
    inicio, fim = _data(item.get('inicio'), 'inicio'), _data(item.get('fim'), 'fim')
    if inicio and fim and fim <= inicio:
        raise InformativoInvalido('O fim precisa ser depois do começo.')
    item['inicio'] = inicio.isoformat() if inicio else None
    item['fim'] = fim.isoformat() if fim else None
    item['ativo'] = bool(item.get('ativo', True))
    return item


def _com_estado(item: dict) -> dict:
    return {**item, 'estado': estado(item)}


def listar(loja) -> list:
    return [_com_estado(i) for i in (loja.metadata or {}).get(CHAVE) or []]


def _gravar(loja, alterar):
    """Relê a loja travada, aplica a alteração só na chave `informativos` e salva."""
    with transaction.atomic():
        fresca = type(loja).objects.select_for_update().get(pk=loja.pk)
        meta = dict(fresca.metadata or {})
        itens = list(meta.get(CHAVE) or [])
        resultado = alterar(itens)
        meta[CHAVE] = itens
        fresca.metadata = meta
        fresca.save(update_fields=['metadata', 'updated_at'])
        return resultado


def criar(loja, dados: dict) -> dict:
    novo = _validar(dados)
    novo['id'] = uuid.uuid4().hex[:12]
    novo['criado_em'] = timezone.now().isoformat()

    def alterar(itens):
        if len(itens) >= MAX_INFORMATIVOS:
            raise InformativoInvalido(f'No máximo {MAX_INFORMATIVOS} informativos — apague os encerrados.')
        itens.insert(0, novo)
        return _com_estado(novo)
    return _gravar(loja, alterar)


def editar(loja, informativo_id: str, dados: dict) -> dict | None:
    def alterar(itens):
        for i, atual in enumerate(itens):
            if atual.get('id') == informativo_id:
                itens[i] = _validar(dados, atual)
                return _com_estado(itens[i])
        return None
    return _gravar(loja, alterar)


def apagar(loja, informativo_id: str) -> bool:
    def alterar(itens):
        antes = len(itens)
        itens[:] = [i for i in itens if i.get('id') != informativo_id]
        return len(itens) < antes
    return _gravar(loja, alterar)


def no_ar_para_a_vitrine(loja) -> list:
    """Só o que o cliente deve ver agora, e só os campos do aviso."""
    agora = timezone.now()
    return [
        {'id': i.get('id'), 'titulo': i.get('titulo', ''), 'texto': i.get('texto', '')}
        for i in (loja.metadata or {}).get(CHAVE) or []
        if estado(i, agora) == 'no_ar'
    ][:5]
