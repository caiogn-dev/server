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
MAX_BOTAO = 30
FORMATOS = ('modal', 'faixa')
FREQUENCIAS = ('uma_vez', 'toda_visita')
MAX_IMAGEM_BYTES = 3 * 1024 * 1024


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
    for campo in ('titulo', 'texto', 'inicio', 'fim', 'ativo', 'formato', 'frequencia',
                  'botao_texto', 'botao_link'):
        if campo in dados:
            item[campo] = dados[campo]
    if dados.get('imagem_url') == '':  # tirar a imagem; trocar só pelo upload
        item['imagem'] = ''
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
    item['formato'] = item.get('formato') or 'modal'
    if item['formato'] not in FORMATOS:
        raise InformativoInvalido('Formato inválido.')
    item['frequencia'] = item.get('frequencia') or 'uma_vez'
    if item['frequencia'] not in FREQUENCIAS:
        raise InformativoInvalido('Frequência inválida.')
    item['botao_texto'] = str(item.get('botao_texto') or '').strip()
    item['botao_link'] = str(item.get('botao_link') or '').strip()
    if bool(item['botao_texto']) != bool(item['botao_link']):
        raise InformativoInvalido('O botão precisa de texto e de link.')
    if len(item['botao_texto']) > MAX_BOTAO:
        raise InformativoInvalido(f'Texto do botão com no máximo {MAX_BOTAO} caracteres.')
    if item['botao_link'] and not link_seguro(item['botao_link']):
        raise InformativoInvalido('Link do botão precisa começar com https:// ou /.')
    item['atualizado_em'] = timezone.now().isoformat()
    return item


def link_seguro(link: str) -> bool:
    """https?:// ou caminho do próprio site. Barra `//host` (vira outro domínio) e esquemas."""
    if link.startswith('/'):
        return not link.startswith('//') and '\\' not in link
    return link.startswith(('https://', 'http://'))


def _com_estado(item: dict) -> dict:
    return {**item, 'estado': estado(item)}


def listar(loja) -> list:
    return [para_o_painel(i) for i in (loja.metadata or {}).get(CHAVE) or []]


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
        return para_o_painel(novo)
    return _gravar(loja, alterar)


def editar(loja, informativo_id: str, dados: dict) -> dict | None:
    def alterar(itens):
        for i, atual in enumerate(itens):
            if atual.get('id') == informativo_id:
                itens[i] = _validar(dados, atual)
                return para_o_painel(itens[i])
        return None
    return _gravar(loja, alterar)


def apagar(loja, informativo_id: str) -> bool:
    def alterar(itens):
        antes = len(itens)
        itens[:] = [i for i in itens if i.get('id') != informativo_id]
        return len(itens) < antes
    return _gravar(loja, alterar)


def _url_da_imagem(caminho: str) -> str:
    if not caminho:
        return ''
    from django.core.files.storage import default_storage
    from apps.core.utils import build_absolute_media_url
    return build_absolute_media_url(default_storage.url(caminho))


def para_o_painel(item: dict) -> dict:
    return {**_com_estado(item), 'imagem_url': _url_da_imagem(item.get('imagem', '')),
            'versao': _versao(item)}


def _versao(item: dict) -> str:
    return item.get('atualizado_em') or item.get('criado_em') or item.get('id') or ''


def no_ar_para_a_vitrine(loja) -> list:
    """Só o que o cliente deve ver agora, e só os campos do aviso.

    Sem `formato` = cadastrado antes do modal: continua faixa, como estava.
    `versao` muda a cada edição — o navegador usa para mostrar de novo o que mudou.
    """
    agora = timezone.now()
    return [
        {
            'id': i.get('id'),
            'titulo': i.get('titulo', ''),
            'texto': i.get('texto', ''),
            'formato': i.get('formato') or 'faixa',
            'frequencia': i.get('frequencia') or 'uma_vez',
            'imagem_url': _url_da_imagem(i.get('imagem', '')),
            'botao_texto': i.get('botao_texto', ''),
            'botao_link': i.get('botao_link', ''),
            'versao': _versao(i),
        }
        for i in (loja.metadata or {}).get(CHAVE) or []
        if estado(i, agora) == 'no_ar'
    ][:5]


def salvar_imagem(loja, informativo_id: str, arquivo) -> dict | None:
    """Valida (é imagem de verdade, ≤ 3 MB) e grava; troca a anterior."""
    from io import BytesIO
    from django.core.files.base import ContentFile
    from django.core.files.storage import default_storage
    from PIL import Image, UnidentifiedImageError

    if arquivo.size > MAX_IMAGEM_BYTES:
        raise InformativoInvalido('Imagem com no máximo 3 MB.')
    conteudo = arquivo.read()
    try:
        with Image.open(BytesIO(conteudo)) as img:
            img.verify()
            formato = (img.format or '').upper()
    except (UnidentifiedImageError, OSError, SyntaxError):
        raise InformativoInvalido('Arquivo não é uma imagem válida.')
    extensao = {'JPEG': 'jpg', 'PNG': 'png', 'WEBP': 'webp'}.get(formato)
    if not extensao:
        raise InformativoInvalido('Use JPG, PNG ou WEBP.')
    caminho = default_storage.save(
        f'informativos/{loja.pk}/{uuid.uuid4().hex}.{extensao}', ContentFile(conteudo))

    antiga = {}

    def alterar(itens):
        for atual in itens:
            if atual.get('id') == informativo_id:
                antiga['caminho'] = atual.get('imagem', '')
                atual['imagem'] = caminho
                atual['atualizado_em'] = timezone.now().isoformat()
                return para_o_painel(atual)
        return None
    resultado = _gravar(loja, alterar)
    apagar_arquivo = caminho if resultado is None else antiga.get('caminho')
    if apagar_arquivo:
        default_storage.delete(apagar_arquivo)
    return resultado
