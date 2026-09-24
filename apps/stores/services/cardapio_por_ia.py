"""Foto ou PDF do cardápio -> as MESMAS linhas que a planilha produz.

POR QUE ESTE MÓDULO EXISTE

A planilha resolveu quem tem planilha. O lojista típico tem o cardápio
impresso, a foto do Instagram ou o PDF da gráfica — e digitar isso é a maior
fatia das 7,9 h de implantação medidas por cliente.

O DESENHO EM UMA FRASE

O modelo só TRANSCREVE. Ele devolve `[{nome, preco, categoria, descricao}]`
com o preço como está escrito, e daí em diante é o funil da planilha
(`importador_de_cardapio.conferir`): mesmo leitor de preço, mesma regra de
repetido, mesma conferência antes de gravar. Uma regra só — o modelo não tem
voz sobre o que é um preço válido.

POR QUE ESTES MODELOS (medido em 24/09/2026, foto de cardápio de teste)

    nvidia/nemotron-3-nano-omni-30b-a3b-reasoning  5/5 itens, sem preço -> null
                                                   6,4 s com raciocínio desligado
                                                   (12,9 s ligado)
    meta/llama-3.2-11b-vision-instruct             4/5, pulou o "consulte" e
                                                   grudou a descrição no item
                                                   errado — 8,1 s (só reserva)
    meta/llama-3.2-90b-vision-instruct             timeout em 60 s e em 120 s
    google/gemma-3-*, phi-3-vision                 404 para a conta

A reserva existe porque o omni devolveu 503 "ResourceExhausted" numa das
chamadas: capacidade do provedor, não erro nosso. Só a NVIDIA NIM — regra da
casa; nunca OpenAI/Anthropic.
"""
from __future__ import annotations

import base64
import io
import json
import logging
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

#: Modelos de visão na ordem MEDIDA (ver docstring). Env sobrepõe o primeiro.
MODELOS_DE_VISAO = (
    'nvidia/nemotron-3-nano-omni-30b-a3b-reasoning',
    'meta/llama-3.2-11b-vision-instruct',
)

#: O gunicorn corta em 120 s e o Cloudflare em 100 s. Uma página leva ~7 s;
#: 45 s por chamada deixa espaço para a reserva sem virar 502 na tela.
TIMEOUT_SEGUNDOS = 45

#: Lado maior da imagem enviada. Foto de 12 MP em base64 passa de 5 MB,
#: estoura o limite do provedor e o tempo; 1600 px ainda lê letra de cardápio.
LADO_MAXIMO = 1600

#: Páginas por envio. Cada uma é uma chamada; acima disso o envio passa do
#: tempo que o proxy espera. Cardápio maior sobe em duas vezes.
MAX_PAGINAS = 8

MENSAGEM_FALHA_FOTO = (
    'Não consegui ler a foto. Tente uma foto mais nítida, de frente e com boa '
    'luz — ou use a planilha.'
)
MENSAGEM_FALHA_PDF = (
    'Não consegui ler o PDF. Tente de novo, envie fotos das páginas ou use a '
    'planilha.'
)

PROMPT = (
    'Você transcreve cardápios de restaurante brasileiros. Liste TODOS os itens '
    'vendidos que aparecem, na ordem em que aparecem. Responda SOMENTE um array '
    'JSON, sem nenhum texto antes ou depois, no formato '
    '[{"nome": "...", "preco": "...", "categoria": "...", "descricao": "..."}].\n'
    '- preco: exatamente como está escrito (ex.: "38,90"). Se o item não tem '
    'preço legível ("consulte", borrado, ausente), use null. NUNCA invente preço.\n'
    '- categoria: o título da seção onde o item está ("" se não houver).\n'
    '- descricao: ingredientes ou detalhes escritos logo abaixo do item, só '
    'daquele item ("" se não houver).\n'
    '- Não invente itens e não inclua títulos de seção como itens.'
)


class LeituraPorIAFalhou(Exception):
    """O modelo não entregou uma leitura utilizável. Mensagem é para o lojista."""


class LeitorDeCardapio:
    """Fala com a NVIDIA NIM. Os dois `perguntar_*` são a costura dos testes."""

    def _chave(self) -> str:
        from django.conf import settings
        return os.getenv('NVIDIA_API_KEY') or getattr(settings, 'NVIDIA_API_KEY', '') or ''

    def _cliente(self, modelo: str, max_tokens: int):
        from langchain_openai import ChatOpenAI

        chave = self._chave()
        if not chave:
            raise LeituraPorIAFalhou('NVIDIA_API_KEY ausente')
        return ChatOpenAI(
            model=modelo,
            temperature=0,
            max_tokens=max_tokens,
            timeout=TIMEOUT_SEGUNDOS,
            # Sem isto cada tentativa ganha o timeout cheio e o teto é mentira.
            max_retries=0,
            api_key=chave,
            base_url=os.getenv('NVIDIA_API_BASE_URL') or 'https://integrate.api.nvidia.com/v1',
        )

    @staticmethod
    def _extra(modelo: str) -> dict:
        # Raciocínio ligado dobra a latência (12,9 s -> 6,4 s) e pode gastar o
        # orçamento de tokens antes do JSON. As duas grafias porque cada
        # template de chat da família lê uma; só vai para quem é nemotron —
        # chave desconhecida em outro modelo é convite a 400.
        if 'nemotron' in modelo:
            return {'chat_template_kwargs': {'thinking': False, 'enable_thinking': False}}
        return {}

    def _modelos_de_visao(self) -> list[str]:
        from apps.agents.runtime.modelos import catalogo_vivo

        preferidos = [os.getenv('NVIDIA_MODELO_VISAO') or '', *MODELOS_DE_VISAO]
        preferidos = list(dict.fromkeys(m for m in preferidos if m))
        catalogo = catalogo_vivo()
        if catalogo:
            vivos = [m for m in preferidos if m in catalogo]
            if vivos:
                return vivos
        return preferidos

    def perguntar_com_imagens(self, imagens: list[bytes]) -> str:
        """Uma página (uma ou mais imagens) -> texto cru do modelo."""
        from langchain_core.messages import HumanMessage

        conteudo = [{'type': 'text', 'text': PROMPT}] + [
            {'type': 'image_url', 'image_url': {
                'url': 'data:image/jpeg;base64,' + base64.b64encode(i).decode('ascii'),
            }}
            for i in imagens
        ]
        ultimo_erro = None
        for modelo in self._modelos_de_visao():
            llm = self._cliente(modelo, max_tokens=6000)
            extra = self._extra(modelo)
            if extra:
                llm = llm.bind(extra_body=extra)
            # O omni responde 503 "ResourceExhausted (16/16)" em rajadas de
            # segundos — medido 3 seguidos e depois 4 bons. Esperar um pouco e
            # repetir no MESMO modelo é melhor que cair na reserva, que lê pior.
            for tentativa in range(3):
                inicio = time.monotonic()
                try:
                    resposta = llm.invoke([HumanMessage(content=conteudo)])
                    logger.info('[cardapio-ia] %s leu em %.1fs', modelo, time.monotonic() - inicio)
                    return getattr(resposta, 'content', str(resposta))
                except Exception as exc:  # provedor fora, 503, 404 da conta
                    ultimo_erro = exc
                    texto = str(exc).lower()
                    # Timeout não tenta mais nada: somaria outros 45 s e a
                    # tela já teria caído no proxy.
                    if isinstance(exc, TimeoutError) or 'timed out' in texto or 'timeout' in texto:
                        raise
                    if ('503' in texto or 'resourceexhausted' in texto) and tentativa < 2:
                        time.sleep(2 * (tentativa + 1))
                        continue
                    logger.warning('[cardapio-ia] %s falhou (%s); tentando o próximo', modelo, exc)
                    break
        raise ultimo_erro or LeituraPorIAFalhou('nenhum modelo de visão')

    def perguntar_com_texto(self, texto: str) -> str:
        """Texto já extraído (PDF com texto) -> texto cru do modelo."""
        from django.conf import settings
        from apps.agents.runtime.modelos import corpo_extra_do_modelo, modelo_vivo

        modelo = modelo_vivo(getattr(settings, 'NVIDIA_INSIGHTS_MODEL', ''))
        llm = self._cliente(modelo, max_tokens=8000)
        extra = corpo_extra_do_modelo(modelo)
        if extra:
            llm = llm.bind(extra_body=extra)
        resposta = llm.invoke(PROMPT + '\n\nCARDÁPIO:\n' + texto)
        return getattr(resposta, 'content', str(resposta))


# ── Resposta do modelo -> linhas ────────────────────────────────────────────

_THINK = re.compile(r'<think>.*?</think>', re.IGNORECASE | re.DOTALL)
_NULOS = {'', 'null', 'none', 'nulo', 'n/a', '-'}


def _categoria(texto) -> str:
    t = re.sub(r'\s+', ' ', str(texto or '')).strip()
    # "MASSAS" é tipografia do cardápio impresso; na vitrine vira "Massas".
    return t.capitalize() if t.isupper() else t


def itens_da_resposta(texto) -> list[dict]:
    """Texto do modelo -> linhas canônicas. Levanta se não houver JSON."""
    bruto = _THINK.sub('', str(texto or ''))
    inicio, fim = bruto.find('['), bruto.rfind(']')
    if inicio < 0 or fim <= inicio:
        raise LeituraPorIAFalhou('resposta sem array JSON')
    try:
        dados = json.loads(bruto[inicio:fim + 1])
    except ValueError as exc:
        raise LeituraPorIAFalhou(f'JSON inválido: {exc}')

    linhas = []
    for item in dados if isinstance(dados, list) else []:
        if not isinstance(item, dict):
            continue
        nome = re.sub(r'\s+', ' ', str(item.get('nome') or '')).strip()
        preco = item.get('preco')
        if isinstance(preco, str) and preco.strip().lower() in _NULOS:
            preco = None
        linha = {
            'nome': nome,
            'preco': preco,
            'categoria': _categoria(item.get('categoria')),
            'descricao': re.sub(r'\s+', ' ', str(item.get('descricao') or '')).strip(),
        }
        if nome or preco is not None:
            linhas.append(linha)
    return linhas


# ── Entradas ────────────────────────────────────────────────────────────────

def preparar_imagem(conteudo: bytes) -> bytes:
    """Qualquer foto -> JPEG em pé, no máximo LADO_MAXIMO. Levanta se não abrir."""
    from PIL import Image, ImageOps

    try:
        img = Image.open(io.BytesIO(conteudo))
        img.load()
    except Exception:
        from apps.stores.services.importador_de_cardapio import LinhaInvalida
        raise LinhaInvalida(
            'Não consegui abrir a imagem. Envie a foto em JPG ou PNG.'
        )
    # Celular grava a foto deitada e anota o giro no EXIF; sem isto o modelo
    # lê o cardápio de lado.
    img = ImageOps.exif_transpose(img).convert('RGB')
    img.thumbnail((LADO_MAXIMO, LADO_MAXIMO))
    saida = io.BytesIO()
    img.save(saida, 'JPEG', quality=85)
    return saida.getvalue()


def _sem_itens(mensagem: str):
    from apps.stores.services.importador_de_cardapio import LinhaInvalida
    return LinhaInvalida(mensagem)


def _ler_paginas(paginas: list[bytes], mensagem: str) -> list[dict]:
    leitor = LeitorDeCardapio()

    def uma(pagina):
        return itens_da_resposta(leitor.perguntar_com_imagens([pagina]))

    try:
        if len(paginas) == 1:
            por_pagina = [uma(paginas[0])]
        else:
            # Em paralelo: 4 páginas em série seriam ~30 s olhando a tela.
            with ThreadPoolExecutor(max_workers=min(4, len(paginas))) as pool:
                por_pagina = list(pool.map(uma, paginas))
    except Exception as exc:
        logger.warning('[cardapio-ia] leitura falhou: %s', exc)
        raise _sem_itens(mensagem)

    linhas = [linha for pagina in por_pagina for linha in pagina]
    if not linhas:
        raise _sem_itens(mensagem)
    return linhas


def ler_foto(conteudos: list[bytes]) -> list[dict]:
    """Uma ou mais fotos (páginas) -> linhas no formato da planilha."""
    if not conteudos:
        raise _sem_itens('Envie a foto do cardápio.')
    if len(conteudos) > MAX_PAGINAS:
        raise _sem_itens(
            f'Envie no máximo {MAX_PAGINAS} fotos por vez. Cardápio maior sobe em duas vezes.'
        )
    paginas = [preparar_imagem(c) for c in conteudos]
    return _ler_paginas(paginas, MENSAGEM_FALHA_FOTO)


def ler_pdf(conteudo: bytes) -> list[dict]:
    """PDF -> linhas. Com texto: modelo de texto. Escaneado: modelo de visão.

    Extrair o texto sem LLM é de graça, determinístico e não erra dígito; o
    modelo só organiza. PDF que é só imagem (a gráfica exporta assim) não tem
    texto, e aí cada página vira foto.
    """
    from pypdf import PdfReader

    try:
        leitor_pdf = PdfReader(io.BytesIO(conteudo))
        paginas = list(leitor_pdf.pages)[:MAX_PAGINAS]
        texto = '\n\n'.join((p.extract_text() or '').strip() for p in paginas).strip()
    except Exception:
        raise _sem_itens('Não consegui abrir o PDF. Confira se o arquivo não está corrompido.')

    if len(re.sub(r'\W', '', texto)) >= 20:
        try:
            linhas = itens_da_resposta(LeitorDeCardapio().perguntar_com_texto(texto))
        except Exception as exc:
            logger.warning('[cardapio-ia] PDF com texto falhou: %s', exc)
            raise _sem_itens(MENSAGEM_FALHA_PDF)
        if not linhas:
            raise _sem_itens(MENSAGEM_FALHA_PDF)
        return linhas

    imagens = []
    for pagina in paginas:
        try:
            fotos = list(pagina.images)
        except Exception:
            fotos = []
        if fotos:
            # A maior imagem da página é o cardápio; as pequenas são logo e ícone.
            maior = max(fotos, key=lambda f: len(f.data))
            imagens.append(maior.data)
    if not imagens:
        raise _sem_itens(
            'O PDF não tem texto nem imagem que eu consiga ler. Envie fotos das '
            'páginas ou use a planilha.'
        )
    return _ler_paginas([preparar_imagem(i) for i in imagens], MENSAGEM_FALHA_PDF)
