"""Importar o cardápio de uma FOTO ou de um PDF.

A planilha resolveu quem tem planilha. Quem mais precisa de implantação não
tem: tem o cardápio impresso na parede, a foto no Instagram, o PDF que a
gráfica mandou. Digitar isso é a fatia maior das 7,9 h medidas por cliente.

As decisões que os testes fixam:

- **Mesmo funil da planilha.** Foto e PDF viram as MESMAS linhas que
  `ler_planilha()` devolve e passam pelo MESMO `conferir()`. Preço em
  português, repetido, categoria — uma regra só, não duas.
- **Sem preço legível é ERRO nomeado, nunca preço 0.** O modelo lê "consulte"
  ou borrão; um produto de graça no cardápio é pior que uma linha recusada.
- **Modelo falhou é mensagem para o lojista, nunca 500.** Timeout, JSON torto
  e 503 do provedor viram "não consegui ler a foto; tente uma mais nítida ou
  use a planilha".
- **Confirmar NÃO chama o modelo de novo.** O que o dono conferiu é o que
  grava: a segunda leitura poderia sair diferente (e custa outra chamada).
"""
import io
import json
import os
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from apps.stores.models import Store, StoreProduct
from apps.stores.services import cardapio_por_ia as ia
from apps.stores.services import importador_de_cardapio as imp

User = get_user_model()

RESPOSTA_BOA = json.dumps([
    {'nome': 'Espaguete à Bolonhesa', 'preco': '38,90', 'categoria': 'MASSAS', 'descricao': ''},
    {'nome': 'Lasanha de Frango', 'preco': 'R$ 42,50', 'categoria': 'MASSAS',
     'descricao': 'molho branco e queijo gratinado'},
    {'nome': 'Vinho da casa (taça)', 'preco': None, 'categoria': 'BEBIDAS', 'descricao': ''},
])


def _jpeg(largura=300, altura=200):
    from PIL import Image
    buf = io.BytesIO()
    Image.new('RGB', (largura, altura), 'white').save(buf, 'JPEG')
    return buf.getvalue()


def _png():
    from PIL import Image
    buf = io.BytesIO()
    Image.new('RGB', (50, 50), 'white').save(buf, 'PNG')
    return buf.getvalue()


def _pdf_com_texto():
    from reportlab.pdfgen import canvas
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    c.drawString(72, 750, 'PIZZAS')
    c.drawString(72, 730, 'Margherita ........ R$ 45,00')
    c.drawString(72, 710, 'Calabresa ......... R$ 48,00')
    c.save()
    return buf.getvalue()


def _pdf_escaneado():
    """PDF sem texto: uma página que é só a foto do cardápio."""
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    c.drawImage(ImageReader(io.BytesIO(_jpeg())), 50, 400, width=300, height=200)
    c.save()
    return buf.getvalue()


class TestQueArquivoEEste:
    """Decide pelo CONTEÚDO, como a planilha já faz: o nome mente."""

    def test_reconhece_cada_formato(self):
        assert imp.tipo_do_arquivo(_jpeg()) == 'imagem'
        assert imp.tipo_do_arquivo(_png()) == 'imagem'
        assert imp.tipo_do_arquivo(_pdf_com_texto()) == 'pdf'
        assert imp.tipo_do_arquivo(b'PK\x03\x04resto') == 'planilha'
        assert imp.tipo_do_arquivo('Nome,Preço\nÁgua,5\n'.encode()) == 'planilha'


class TestFotoViraAsMesmasLinhasDaPlanilha:
    def test_foto_devolve_linhas_canonicas(self):
        with patch.object(ia.LeitorDeCardapio, 'perguntar_com_imagens',
                          autospec=True, return_value=RESPOSTA_BOA) as modelo:
            linhas = imp.ler_foto([_jpeg()])

        assert modelo.call_count == 1
        assert [l['nome'] for l in linhas] == [
            'Espaguete à Bolonhesa', 'Lasanha de Frango', 'Vinho da casa (taça)',
        ]
        assert set(linhas[0]) <= {'nome', 'preco', 'categoria', 'descricao'}
        assert linhas[1]['descricao'] == 'molho branco e queijo gratinado'

    def test_categoria_GRITADA_na_foto_vira_nome_de_secao(self):
        """"MASSAS" em caixa alta é tipografia do cardápio, não o nome que o
        dono quer ver na vitrine."""
        with patch.object(ia.LeitorDeCardapio, 'perguntar_com_imagens',
                          autospec=True, return_value=RESPOSTA_BOA):
            linhas = imp.ler_foto([_jpeg()])
        assert linhas[0]['categoria'] == 'Massas'

    def test_item_sem_preco_vira_ERRO_com_o_nome_nunca_preco_zero(self):
        with patch.object(ia.LeitorDeCardapio, 'perguntar_com_imagens',
                          autospec=True, return_value=RESPOSTA_BOA):
            r = imp.conferir(imp.ler_foto([_jpeg()]), primeira=1)

        assert [v['nome'] for v in r.validos] == ['Espaguete à Bolonhesa', 'Lasanha de Frango']
        assert r.validos[1]['preco'] == Decimal('42.50')
        assert len(r.erros) == 1
        assert r.erros[0].linha == 3
        assert 'Vinho da casa' in r.erros[0].motivo
        assert 'preço' in r.erros[0].motivo.lower()

    def test_preco_null_escrito_como_texto_tambem_e_erro(self):
        resposta = json.dumps([{'nome': 'Vinho', 'preco': 'null', 'categoria': ''}])
        with patch.object(ia.LeitorDeCardapio, 'perguntar_com_imagens',
                          autospec=True, return_value=resposta):
            r = imp.conferir(imp.ler_foto([_jpeg()]), primeira=1)
        assert r.validos == []
        assert 'Vinho' in r.erros[0].motivo

    def test_json_embrulhado_em_markdown_e_raciocinio_e_aceito(self):
        """Modelo aberto escreve "Claro!" e cerca de ```json. Recusar isso é
        jogar fora uma leitura boa."""
        sujo = '<think>vou ler</think>Claro! ```json\n' + RESPOSTA_BOA + '\n``` Pronto.'
        with patch.object(ia.LeitorDeCardapio, 'perguntar_com_imagens',
                          autospec=True, return_value=sujo):
            assert len(imp.ler_foto([_jpeg()])) == 3

    def test_varias_fotos_sao_varias_paginas_na_ordem(self):
        pagina1 = json.dumps([{'nome': 'A', 'preco': '1'}])
        pagina2 = json.dumps([{'nome': 'B', 'preco': '2'}])
        with patch.object(ia.LeitorDeCardapio, 'perguntar_com_imagens',
                          autospec=True, side_effect=[pagina1, pagina2]) as modelo:
            linhas = imp.ler_foto([_jpeg(), _jpeg(400, 300)])

        assert modelo.call_count == 2
        assert [l['nome'] for l in linhas] == ['A', 'B']

    def test_foto_gigante_de_celular_e_reduzida_antes_de_ir_ao_modelo(self):
        """Foto de 12 MP em base64 estoura o limite do provedor e o tempo."""
        with patch.object(ia.LeitorDeCardapio, 'perguntar_com_imagens',
                          autospec=True, return_value='[]') as modelo:
            with pytest.raises(imp.LinhaInvalida):
                imp.ler_foto([_jpeg(4000, 3000)])
        imagens = modelo.call_args.args[1]
        from PIL import Image
        enviada = Image.open(io.BytesIO(imagens[0]))
        assert max(enviada.size) <= ia.LADO_MAXIMO


class TestModeloFalhouViraMensagem:
    def _espera_mensagem(self, **kw):
        with patch.object(ia.LeitorDeCardapio, 'perguntar_com_imagens', autospec=True, **kw):
            with pytest.raises(imp.LinhaInvalida) as e:
                imp.ler_foto([_jpeg()])
        msg = str(e.value).lower()
        assert 'foto' in msg and 'planilha' in msg
        assert 'traceback' not in msg and 'exception' not in msg
        return msg

    def test_timeout(self):
        self._espera_mensagem(side_effect=TimeoutError('read timed out'))

    def test_provedor_fora(self):
        self._espera_mensagem(side_effect=RuntimeError('503 ResourceExhausted'))

    def test_resposta_que_nao_e_json(self):
        self._espera_mensagem(return_value='Desculpe, não consigo ver imagens.')

    def test_nenhum_item_encontrado(self):
        self._espera_mensagem(return_value='[]')

    def test_arquivo_que_diz_ser_imagem_mas_esta_corrompido(self):
        with patch.object(ia.LeitorDeCardapio, 'perguntar_com_imagens', autospec=True) as m:
            with pytest.raises(imp.LinhaInvalida):
                imp.ler_foto([b'\xff\xd8\xff' + b'lixo' * 10])
        assert m.call_count == 0


class _LlmFalso:
    """Stand-in do ChatOpenAI: responde a sequência dada, em ordem."""

    def __init__(self, respostas):
        self.respostas = list(respostas)
        self.chamadas = 0

    def bind(self, **_):
        return self

    def invoke(self, _mensagens):
        self.chamadas += 1
        r = self.respostas.pop(0)
        if isinstance(r, Exception):
            raise r
        from types import SimpleNamespace
        return SimpleNamespace(content=r)


class TestProvedorSobCarga:
    """O omni devolve 503 "ResourceExhausted (16/16)" em rajadas de segundos."""

    def _ler(self, por_modelo):
        falsos = {m: _LlmFalso(r) for m, r in por_modelo.items()}
        with patch.object(ia.LeitorDeCardapio, '_modelos_de_visao', autospec=True,
                          return_value=list(por_modelo)), \
             patch.object(ia.LeitorDeCardapio, '_cliente', autospec=True,
                          side_effect=lambda self, modelo, max_tokens: falsos[modelo]), \
             patch.object(ia.time, 'sleep', autospec=True):
            texto = ia.LeitorDeCardapio().perguntar_com_imagens([b'x'])
        return texto, falsos

    def test_503_repete_no_mesmo_modelo_antes_da_reserva(self):
        texto, falsos = self._ler({
            'omni': [RuntimeError('503 ResourceExhausted'), '[{"nome": "A", "preco": "1"}]'],
            'reserva': ['[]'],
        })
        assert 'A' in texto
        assert falsos['omni'].chamadas == 2 and falsos['reserva'].chamadas == 0

    def test_erro_que_nao_e_carga_vai_direto_para_a_reserva(self):
        texto, falsos = self._ler({
            'omni': [RuntimeError('404 Not found for account')],
            'reserva': ['[{"nome": "B", "preco": "2"}]'],
        })
        assert 'B' in texto
        assert falsos['omni'].chamadas == 1

    def test_timeout_nao_tenta_a_reserva(self):
        with pytest.raises(TimeoutError):
            self._ler({'omni': [TimeoutError('timed out')], 'reserva': ['[]']})


class TestPdf:
    def test_pdf_com_texto_vai_ao_modelo_de_TEXTO_sem_foto(self):
        resposta = json.dumps([
            {'nome': 'Margherita', 'preco': '45,00', 'categoria': 'PIZZAS'},
            {'nome': 'Calabresa', 'preco': '48,00', 'categoria': 'PIZZAS'},
        ])
        with patch.object(ia.LeitorDeCardapio, 'perguntar_com_texto',
                          autospec=True, return_value=resposta) as texto, \
             patch.object(ia.LeitorDeCardapio, 'perguntar_com_imagens', autospec=True) as visao:
            linhas = imp.ler_pdf(_pdf_com_texto())

        assert visao.call_count == 0
        enviado = texto.call_args.args[1]
        assert 'Margherita' in enviado and '45,00' in enviado
        assert [l['nome'] for l in linhas] == ['Margherita', 'Calabresa']

    def test_pdf_escaneado_vira_foto(self):
        """Gráfica manda PDF que é só imagem: sem texto, o caminho é a visão."""
        resposta = json.dumps([{'nome': 'X-Burger', 'preco': '25', 'categoria': 'Lanches'}])
        with patch.object(ia.LeitorDeCardapio, 'perguntar_com_texto', autospec=True) as texto, \
             patch.object(ia.LeitorDeCardapio, 'perguntar_com_imagens',
                          autospec=True, return_value=resposta) as visao:
            linhas = imp.ler_pdf(_pdf_escaneado())

        assert texto.call_count == 0
        assert visao.call_count == 1
        assert linhas[0]['nome'] == 'X-Burger'

    def test_pdf_corrompido_diz_o_que_fazer(self):
        with pytest.raises(imp.LinhaInvalida) as e:
            imp.ler_pdf(b'%PDF-1.4 isto nao e um pdf')
        assert 'pdf' in str(e.value).lower()


class EndpointFotoTests(APITestCase):
    def setUp(self):
        self.dono = User.objects.create_user(
            username='dono-foto', password='x', email='foto@real.com',
        )
        self.store = Store.objects.create(
            name='Loja Foto', slug='loja-foto', owner=self.dono, status='active',
        )
        self.client.force_authenticate(user=self.dono)
        self.url = f'/api/v1/stores/{self.store.slug}/produtos/importar/'

    def _arquivo(self, conteudo, nome):
        f = io.BytesIO(conteudo)
        f.name = nome
        return f

    def test_foto_confere_sem_gravar_e_nomeia_o_item_sem_preco(self):
        with patch.object(ia.LeitorDeCardapio, 'perguntar_com_imagens',
                          autospec=True, return_value=RESPOSTA_BOA):
            r = self.client.post(
                self.url, {'arquivo': self._arquivo(_jpeg(), 'cardapio.jpg')},
                format='multipart',
            )

        assert r.status_code == 200, r.data
        assert r.data['origem'] == 'foto'
        assert [v['nome'] for v in r.data['validos']] == [
            'Espaguete à Bolonhesa', 'Lasanha de Frango',
        ]
        assert r.data['validos'][1]['descricao'] == 'molho branco e queijo gratinado'
        assert r.data['erros'][0]['linha'] == 3
        assert 'Vinho da casa' in r.data['erros'][0]['motivo']
        assert StoreProduct.objects.filter(store=self.store).count() == 0

    def test_varias_fotos_no_mesmo_envio(self):
        paginas = [json.dumps([{'nome': 'A', 'preco': '1'}]),
                   json.dumps([{'nome': 'B', 'preco': '2'}])]
        with patch.object(ia.LeitorDeCardapio, 'perguntar_com_imagens',
                          autospec=True, side_effect=paginas):
            r = self.client.post(self.url, {'arquivo': [
                self._arquivo(_jpeg(), 'p1.jpg'), self._arquivo(_png(), 'p2.png'),
            ]}, format='multipart')

        assert r.status_code == 200, r.data
        assert [v['nome'] for v in r.data['validos']] == ['A', 'B']

    def test_pdf_pelo_endpoint(self):
        resposta = json.dumps([{'nome': 'Margherita', 'preco': '45,00'}])
        with patch.object(ia.LeitorDeCardapio, 'perguntar_com_texto',
                          autospec=True, return_value=resposta):
            r = self.client.post(
                self.url, {'arquivo': self._arquivo(_pdf_com_texto(), 'menu.pdf')},
                format='multipart',
            )
        assert r.status_code == 200, r.data
        assert r.data['origem'] == 'pdf'
        assert r.data['validos'][0]['nome'] == 'Margherita'

    def test_modelo_fora_do_ar_responde_400_com_mensagem_nunca_500(self):
        with patch.object(ia.LeitorDeCardapio, 'perguntar_com_imagens',
                          autospec=True, side_effect=TimeoutError('timed out')):
            r = self.client.post(
                self.url, {'arquivo': self._arquivo(_jpeg(), 'cardapio.jpg')},
                format='multipart',
            )
        assert r.status_code == 400
        assert 'planilha' in r.data['detail'].lower()

    def test_confirmar_grava_o_que_foi_CONFERIDO_sem_chamar_o_modelo_de_novo(self):
        conferido = [
            {'nome': 'Espaguete à Bolonhesa', 'preco': '38.90', 'categoria': 'Massas',
             'descricao': ''},
            {'nome': 'Lasanha de Frango', 'preco': '42.50', 'categoria': 'Massas',
             'descricao': 'molho branco e queijo gratinado'},
        ]
        with patch.object(ia.LeitorDeCardapio, 'perguntar_com_imagens', autospec=True) as m:
            r = self.client.post(
                self.url, {'linhas': json.dumps(conferido), 'confirmar': 'true'},
                format='multipart',
            )

        assert m.call_count == 0
        assert r.status_code == 201, r.data
        assert r.data['criados'] == 2
        lasanha = StoreProduct.objects.get(store=self.store, name='Lasanha de Frango')
        assert lasanha.price == Decimal('42.50')
        assert lasanha.description == 'molho branco e queijo gratinado'

    def test_linhas_confirmadas_passam_pela_mesma_conferencia(self):
        """Quem manda `linhas` direto na API não pula a regra do preço."""
        r = self.client.post(self.url, {
            'linhas': [{'nome': 'Grátis', 'preco': ''}], 'confirmar': True,
        }, format='json')
        assert r.status_code == 201, r.data
        assert r.data['criados'] == 0
        assert StoreProduct.objects.filter(store=self.store).count() == 0

    def test_planilha_misturada_com_foto_e_recusada_com_explicacao(self):
        r = self.client.post(self.url, {'arquivo': [
            self._arquivo(_jpeg(), 'p1.jpg'),
            self._arquivo('Nome,Preço\nÁgua,5\n'.encode(), 'c.csv'),
        ]}, format='multipart')
        assert r.status_code == 400
        assert 'planilha' in r.data['detail'].lower()


@pytest.mark.skipif(
    not (os.environ.get('IMPORTADOR_IA_REAL') and os.environ.get('NVIDIA_API_KEY')),
    reason='Prova real contra a NVIDIA NIM: rode com IMPORTADOR_IA_REAL=1 e a chave.',
)
def test_prova_real_foto_de_cardapio_na_nvidia():
    """UMA chamada de verdade: o modelo de visão lê a foto e o funil confere."""
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new('RGB', (900, 420), 'white')
    d = ImageDraw.Draw(img)
    try:
        fonte = ImageFont.truetype('DejaVuSans.ttf', 30)
    except OSError:
        fonte = ImageFont.load_default(size=30)
    for i, linha in enumerate([
        'MASSAS', 'Espaguete a Bolonhesa ...... R$ 38,90',
        'Lasanha de Frango ............ R$ 42,50', 'BEBIDAS',
        'Refrigerante lata ............ R$ 6,50', 'Vinho da casa (taca) ....... consulte',
    ]):
        d.text((40, 30 + i * 60), linha, fill='black', font=fonte)
    buf = io.BytesIO()
    img.save(buf, 'JPEG')

    r = imp.conferir(imp.ler_foto([buf.getvalue()]), primeira=1)

    precos = {v['nome'].lower(): v['preco'] for v in r.validos}
    assert any('lasanha' in n and p == Decimal('42.50') for n, p in precos.items()), precos
    assert all(v['preco'] > 0 for v in r.validos)
    assert any('vinho' in e.motivo.lower() for e in r.erros), r.erros
