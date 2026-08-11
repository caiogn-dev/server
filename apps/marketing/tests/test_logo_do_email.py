"""Logo de e-mail: leve o bastante para abrir e pequena o bastante para caber.

11/ago, olhando o arquivo real da Cê Saladas: 3531×3905 px, 698 KB, para ser
exibida com 48 px de altura. É o MESMO arquivo que causou o problema de LCP no
site em agosto. Num e-mail é pior: pesa na abertura, e anexo/imagem grande
conta ponto negativo em filtro de spam.
"""
import pytest
from PIL import Image

from apps.marketing.services.marca_da_loja import logo_para_email
from apps.stores.tests.factories import make_store


@pytest.fixture
def loja_com_logo(db, tmp_path):
    from django.core.files.base import ContentFile
    import io

    store = make_store(name='Cê Saladas')
    buf = io.BytesIO()
    Image.new('RGB', (3531, 3905), '#e87b21').save(buf, format='JPEG')
    store.logo.save('ce-saladas.jpg', ContentFile(buf.getvalue()), save=True)
    return store


def test_derivada_cabe_no_cabecalho(loja_com_logo):
    from django.core.files.storage import default_storage

    caminho = logo_para_email(loja_com_logo)

    with default_storage.open(caminho.split('/media/')[-1]) as fh:
        im = Image.open(fh)
        assert max(im.size) <= 480


def test_derivada_e_muito_mais_leve_que_a_original(loja_com_logo):
    from django.core.files.storage import default_storage

    caminho = logo_para_email(loja_com_logo)
    tamanho = default_storage.size(caminho.split('/media/')[-1])

    assert tamanho < 60_000, f'{tamanho} bytes ainda é grande demais para e-mail'


def test_devolve_url_absoluta(loja_com_logo):
    assert logo_para_email(loja_com_logo).startswith('https://')


def test_segunda_chamada_reusa_o_arquivo(loja_com_logo):
    """Gerar a cada envio seria refazer o mesmo trabalho por destinatário."""
    assert logo_para_email(loja_com_logo) == logo_para_email(loja_com_logo)


def test_loja_sem_logo_devolve_vazio(db):
    assert logo_para_email(make_store(name='Sem Logo')) == ''


def test_falha_ao_gerar_cai_na_original_e_nao_derruba_o_email(loja_com_logo, monkeypatch):
    """E-mail sem logo é aceitável; e-mail que não sai, não."""
    import apps.marketing.services.marca_da_loja as m

    monkeypatch.setattr(m.Image, 'open', lambda *a, **k: (_ for _ in ()).throw(OSError('corrompida')))

    assert logo_para_email(loja_com_logo).startswith('https://')
