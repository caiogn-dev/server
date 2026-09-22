"""Nenhum arquivo fixa a versão da Graph API da Meta.

19/09: havia v18, v21, v22 e v24 convivendo — cada arquivo com a sua, e
produção rodava o WhatsApp numa (v24, pelo .env) e o Instagram noutra (v22,
fixa no código). A versão vem só de WHATSAPP_API_VERSION / META_GRAPH_VERSION.
"""
import re
from pathlib import Path

VERSAO_FIXA = re.compile(r'graph\.(facebook|instagram)\.com/v\d+\.\d+')


def test_nenhuma_url_da_graph_com_versao_fixa():
    culpados = [
        f'{arquivo}:{n}'
        for arquivo in Path('apps').rglob('*.py')
        if '/tests/' not in str(arquivo) and not arquivo.name.startswith('test')
        for n, linha in enumerate(arquivo.read_text(errors='ignore').splitlines(), 1)
        if VERSAO_FIXA.search(linha)
    ]
    assert culpados == []
