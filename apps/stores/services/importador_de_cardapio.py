"""Ler o cardápio de uma planilha e transformá-lo em produtos.

POR QUE ESTE MÓDULO EXISTE

A implantação de um cliente custa **7,9 h medidas**, e a maior fatia é digitar
produto por produto no formulário. Com 92 min/mês de suporte por loja, o teto
de um dev solo fica em ~35 clientes. O teto é o que impede vender volume — não
o preço. Este módulo é o corte desse teto, não uma conveniência.

FOTO E PDF (24/09)

A primeira versão foi só planilha porque a chave da NVIDIA devolvia 403
(22/09). Com a chave nova, foto e PDF entram por `cardapio_por_ia`, que só
TRANSCREVE e devolve as mesmas linhas que `ler_planilha()` — daqui em diante
é o mesmo funil: `conferir()` decide o que é preço, o que é repetido e o que
entra. Uma regra só para as três portas.

O DESENHO EM UMA FRASE

Conferir é separado de gravar. `conferir()` não toca no banco: devolve o que
entra e o que falhou, com número de linha. A tela mostra isso ANTES de
qualquer escrita, porque importar 80 produtos errados é pior que não importar.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation


class LinhaInvalida(ValueError):
    """A linha não vira produto. A mensagem é para o dono da loja ler."""


#: Coluna canônica -> como o dono pode ter escrito o cabeçalho.
#:
#: Exigir um cabeçalho exato devolveria ao dono o trabalho que o importador
#: veio tirar: ele monta a planilha do jeito dele, com acento e maiúscula.
SINONIMOS = {
    'nome': ('nome', 'produto', 'nome do produto', 'item', 'descricao do item'),
    'preco': ('preco', 'valor', 'preco r', 'preco unitario', 'valor unitario'),
    'categoria': ('categoria', 'secao', 'grupo', 'tipo'),
    'descricao': ('descricao', 'detalhes', 'observacao', 'ingredientes'),
}


def _chave(texto) -> str:
    """Minúsculo, sem acento e sem pontuação — para comparar cabeçalho."""
    t = unicodedata.normalize('NFKD', str(texto or ''))
    t = t.encode('ascii', 'ignore').decode('ascii').lower()
    return re.sub(r'\s+', ' ', re.sub(r'[^a-z0-9 ]', ' ', t)).strip()


def coluna_canonica(cabecalho) -> str | None:
    """Qual coluna é esta, ou None se não for uma que a gente entende.

    Coluna desconhecida é IGNORADA, não é erro: a planilha do dono costuma ter
    colunas dele ("observações do chef") que não têm nada a ver com o cadastro.
    """
    k = _chave(cabecalho)
    for canonica, variantes in SINONIMOS.items():
        if k in variantes or k == canonica:
            return canonica
    return None


def ler_preco(valor) -> Decimal:
    """'12,90' e 'R$ 1.234,50' viram Decimal. Lixo levanta.

    Nunca devolve 0 para entrada ruim: um produto que entra de graça no
    cardápio é pior que uma linha recusada, porque ninguém percebe até vender.
    """
    if valor is None:
        raise LinhaInvalida('Informe o preço.')
    if isinstance(valor, (int, float, Decimal)):
        bruto = str(valor)
    else:
        bruto = str(valor).strip()
    if not bruto:
        raise LinhaInvalida('Informe o preço.')

    limpo = re.sub(r'[^\d,.\-]', '', bruto)
    if not limpo:
        raise LinhaInvalida(f'Preço não reconhecido: {str(valor).strip()!r}.')

    # "1.234,50" é português; "1234.50" é máquina. A vírgula decide: quando ela
    # existe, o ponto é separador de milhar.
    if ',' in limpo:
        limpo = limpo.replace('.', '').replace(',', '.')
    try:
        preco = Decimal(limpo)
    except InvalidOperation:
        raise LinhaInvalida(f'Preço não reconhecido: {str(valor).strip()!r}.')
    if preco < 0:
        raise LinhaInvalida('O preço não pode ser negativo.')
    return preco


@dataclass
class ErroDeLinha:
    linha: int
    motivo: str


@dataclass
class Conferencia:
    validos: list = field(default_factory=list)
    erros: list = field(default_factory=list)


def conferir(linhas, *, primeira: int = 2) -> Conferencia:
    """Separa o que vira produto do que falhou. NÃO grava nada.

    Uma linha torta não derruba o arquivo: um cardápio de 80 itens com 2 linhas
    ruins importa 78 e diz quais 2 falharam. Abortar tudo obrigaria o dono a
    recomeçar do zero por causa de uma vírgula.

    `primeira` é o número da primeira linha: 2 na planilha (1 é o cabeçalho),
    1 na foto/PDF, onde o número é a posição do item no cardápio.
    """
    resultado = Conferencia()
    ja_vistos = set()

    for indice, linha in enumerate(linhas or [], start=primeira):
        nome = str((linha or {}).get('nome') or '').strip()
        if not nome:
            resultado.erros.append(ErroDeLinha(indice, 'Falta o nome do produto.'))
            continue

        chave = _chave(nome)
        if chave in ja_vistos:
            resultado.erros.append(
                ErroDeLinha(indice, f'{nome!r} está repetido no cardápio.')
            )
            continue

        try:
            preco = ler_preco(linha.get('preco'))
        except LinhaInvalida as exc:
            # O NOME na mensagem: "Linha 14: informe o preço" obriga o dono a
            # contar linhas; na foto nem existe linha para contar.
            resultado.erros.append(ErroDeLinha(indice, f'{nome}: {exc}'))
            continue

        ja_vistos.add(chave)
        resultado.validos.append({
            'nome': nome,
            'preco': preco,
            'categoria': str(linha.get('categoria') or '').strip(),
            'descricao': str(linha.get('descricao') or '').strip(),
        })

    return resultado


def _slug(texto: str, prefixo: str = '') -> str:
    from django.utils.text import slugify
    base = slugify(texto)[:200] or 'item'
    return f'{prefixo}{base}' if prefixo else base


def _categoria(store, nome: str, criado_por=None):
    """A categoria pelo nome, criando se não existir.

    `iexact` porque o dono escreve "Bebidas" numa linha e "bebidas" na outra —
    criar duas seções por causa de maiúscula seria entregar um cardápio pior
    que o digitado à mão.
    """
    from apps.stores.models import StoreCategory

    nome = (nome or '').strip()
    if not nome:
        return None
    existente = StoreCategory.objects.filter(store=store, name__iexact=nome).first()
    if existente:
        return existente
    return StoreCategory.objects.create(
        store=store, name=nome, slug=_slug(nome),
    )


def gravar(store, validos, *, criado_por=None) -> dict:
    """Cria ou atualiza os produtos conferidos. Devolve a contagem.

    ATUALIZA em vez de duplicar: o dono vai corrigir a planilha e subir de
    novo, e um importador que duplica deixa o cardápio em dobro para ele
    apagar item por item — o oposto do que esta feature existe para fazer.

    O casamento é por (loja, nome sem acento/caixa). Nome é o que o dono tem;
    SKU quase nunca existe num cardápio de restaurante.
    """
    from django.db import transaction
    from apps.stores.models import StoreProduct

    criados = atualizados = 0
    # Índice da loja em memória: `iexact` por produto seria uma query por linha,
    # e cardápio de 200 itens viraria 200 idas ao banco.
    existentes = {
        _chave(p.name): p
        for p in StoreProduct.objects.filter(store=store).only('id', 'name')
    }

    with transaction.atomic():
        for item in validos:
            categoria = _categoria(store, item.get('categoria'), criado_por)
            atual = existentes.get(_chave(item['nome']))
            if atual is not None:
                atual.price = item['preco']
                if categoria is not None:
                    atual.category = categoria
                if item.get('descricao'):
                    atual.description = item['descricao']
                atual.save(update_fields=['price', 'category', 'description', 'updated_at'])
                atualizados += 1
                continue

            novo = StoreProduct.objects.create(
                store=store,
                name=item['nome'],
                slug=_slug(item['nome']),
                price=item['preco'],
                category=categoria,
                description=item.get('descricao') or '',
                # Cardápio de restaurante não controla estoque por padrão; deixar
                # ligado faria 200 produtos nascerem "sem estoque" e sumirem da
                # vitrine no primeiro pedido.
                track_stock=False,
                status='active',
            )
            existentes[_chave(novo.name)] = novo
            criados += 1

    return {'criados': criados, 'atualizados': atualizados}


#: Assinatura de arquivo ZIP — todo .xlsx é um ZIP por dentro.
_ASSINATURA_XLSX = b'PK\x03\x04'

#: Ordem de tentativa para decodificar CSV.
#:
#: `utf-8-sig` primeiro porque come o BOM que o próprio modelo daqui escreve.
#: `cp1252` no fim porque é o que o Excel brasileiro salva: sem ele, "Preço"
#: vira "Pre?o", a coluna não casa com nenhum sinônimo e a tela dizia
#: "A planilha está vazia" para um arquivo cheio.
CODIFICACOES = ('utf-8-sig', 'utf-8', 'cp1252', 'latin-1')


def _linhas_do_xlsx(conteudo: bytes) -> list[dict]:
    """Lê a primeira aba de um .xlsx. É o formato que o lojista TEM.

    Excel e Google Sheets salvam .xlsx por padrão; pedir CSV é devolver ao
    dono o trabalho que o importador veio tirar.
    """
    import io
    from openpyxl import load_workbook

    wb = load_workbook(io.BytesIO(conteudo), read_only=True, data_only=True)
    aba = wb.worksheets[0]
    linhas = list(aba.iter_rows(values_only=True))
    if not linhas:
        return []

    cabecalho = [coluna_canonica(c) for c in linhas[0]]
    if not any(cabecalho):
        raise LinhaInvalida(
            'A primeira linha da planilha precisa ter os títulos das colunas '
            '(Nome, Preço, Categoria).'
        )

    saida = []
    for crua in linhas[1:]:
        linha = {
            col: valor for col, valor in zip(cabecalho, crua)
            if col and valor not in (None, '')
        }
        if linha:
            saida.append(linha)
    return saida


def _texto_do_csv(conteudo: bytes) -> str:
    for codec in CODIFICACOES:
        try:
            return conteudo.decode(codec)
        except UnicodeDecodeError:
            continue
    # `latin-1` nunca falha, então só chegamos aqui se a tupla mudar.
    return conteudo.decode('utf-8', errors='replace')


def ler_planilha(conteudo: bytes, nome: str = '') -> list[dict]:
    """O arquivo do lojista -> linhas com colunas canônicas.

    Decide pelo CONTEÚDO, não pela extensão: um .xlsx renomeado para .csv
    continua sendo um ZIP, e o lojista não tem como saber disso.
    """
    if not conteudo:
        raise LinhaInvalida('Envie a planilha com o cardápio.')

    if conteudo[:4] == _ASSINATURA_XLSX:
        return _linhas_do_xlsx(conteudo)

    texto = _texto_do_csv(conteudo)
    # Um PDF ou uma imagem viram lixo binário decodificado: sem linha nenhuma
    # com separador reconhecível. Recusar é certo; recusar calado, não.
    if '\x00' in texto[:200] or not any(s in texto[:400] for s in (',', ';', '\n')):
        raise LinhaInvalida(
            f'Não consegui ler {nome or "o arquivo"}. Envie a planilha em '
            'Excel (.xlsx) ou CSV.'
        )
    return ler_csv(texto)


def ler_csv(texto: str) -> list[dict]:
    """Texto CSV -> linhas com as colunas já canônicas.

    Aceita ',' e ';' porque o Excel brasileiro salva com ponto-e-vírgula e o
    dono não tem como saber disso — recusar o arquivo dele por causa do
    separador seria devolver o problema.
    """
    import csv
    import io

    bruto = (texto or '').strip()
    if not bruto:
        raise LinhaInvalida('Envie a planilha com o cardápio.')

    primeira = bruto.splitlines()[0]
    separador = ';' if primeira.count(';') > primeira.count(',') else ','

    linhas = []
    for crua in csv.DictReader(io.StringIO(bruto), delimiter=separador):
        linha = {}
        for cabecalho, valor in (crua or {}).items():
            coluna = coluna_canonica(cabecalho)
            if coluna:
                linha[coluna] = valor
        if linha:
            linhas.append(linha)
    return linhas


# ── Foto e PDF: outras portas, o mesmo funil ────────────────────────────────

_ASSINATURAS_DE_IMAGEM = (b'\xff\xd8\xff', b'\x89PNG\r\n\x1a\n', b'GIF87a', b'GIF89a')


def tipo_do_arquivo(conteudo: bytes) -> str:
    """'pdf', 'imagem', 'heic' ou 'planilha' — pelo CONTEÚDO, nunca pelo nome."""
    cabeca = (conteudo or b'')[:16]
    if cabeca.startswith(b'%PDF'):
        return 'pdf'
    if cabeca.startswith(_ASSINATURAS_DE_IMAGEM) or (
        cabeca[:4] == b'RIFF' and cabeca[8:12] == b'WEBP'
    ):
        return 'imagem'
    if cabeca[4:8] == b'ftyp' and cabeca[8:12] in (b'heic', b'heix', b'mif1', b'msf1'):
        return 'heic'
    return 'planilha'


def ler_foto(conteudos: list[bytes]) -> list[dict]:
    """Fotos do cardápio -> linhas no formato de `ler_planilha()`."""
    from apps.stores.services import cardapio_por_ia
    return cardapio_por_ia.ler_foto(conteudos)


def ler_pdf(conteudo: bytes) -> list[dict]:
    """PDF do cardápio -> linhas no formato de `ler_planilha()`."""
    from apps.stores.services import cardapio_por_ia
    return cardapio_por_ia.ler_pdf(conteudo)


def ler_arquivos(arquivos: list[tuple[str, bytes]]) -> tuple[list[dict], str]:
    """Os arquivos enviados -> (linhas, origem). Origem: planilha, foto ou pdf.

    Várias fotos são várias páginas do mesmo cardápio. Planilha e PDF vão um
    por vez: misturar portas no mesmo envio não tem leitura óbvia, e adivinhar
    aqui é gravar cardápio errado.
    """
    if not arquivos:
        raise LinhaInvalida('Envie a planilha, a foto ou o PDF do cardápio.')
    tipos = [tipo_do_arquivo(conteudo) for _, conteudo in arquivos]

    if 'heic' in tipos:
        raise LinhaInvalida(
            'Esta foto está em HEIC (formato do iPhone). Envie em JPG — ou tire '
            'um print da foto e envie o print.'
        )
    if all(t == 'imagem' for t in tipos):
        return ler_foto([conteudo for _, conteudo in arquivos]), 'foto'
    if len(arquivos) > 1:
        raise LinhaInvalida(
            'Envie uma planilha ou um PDF por vez. Várias fotos juntas podem — '
            'são as páginas do cardápio.'
        )
    nome, conteudo = arquivos[0]
    if tipos[0] == 'pdf':
        return ler_pdf(conteudo), 'pdf'
    return ler_planilha(conteudo, nome), 'planilha'
