"""A bandeira leva rotulo E logo — e nenhum dos dois mora no frontend.

O dono pediu um seletor com a logo da bandeira. A tentacao seria por os
arquivos no cardapio, e ai bandeira nova voltaria a exigir deploy de frontend —
o oposto do que o desenho inteiro existe para evitar. Entao a logo viaja pelo
mesmo caminho do rotulo: nasce no catalogo e chega por API.
"""
from django.test import TestCase, override_settings

from apps.stores.services.voucher import bandeiras
from apps.stores.services.voucher import logos


#: O harness de teste nao roda `collectstatic`, e o storage de producao exige
#: manifesto. Para exercitar a MONTAGEM da URL, trocamos por um storage simples
#: — o comportamento sob manifesto ausente tem teste proprio mais abaixo.
SEM_MANIFESTO = override_settings(
    STORAGES={
        'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
        'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
    },
    BASE_URL='https://backend.pastita.com.br',
)


@SEM_MANIFESTO
class CatalogoLevaLogoTests(TestCase):
    def test_toda_bandeira_do_catalogo_tem_logo(self):
        for b in bandeiras.CATALOGO:
            self.assertTrue(b.get('logo'), f"{b['value']} sem logo")

    def test_o_caminho_da_logo_e_relativo_no_catalogo(self):
        """O modulo do catalogo e puro — nao pode saber o dominio."""
        for b in bandeiras.CATALOGO:
            self.assertFalse(b['logo'].startswith('http'), b['value'])

    def test_a_api_devolve_url_absoluta(self):
        """O cardapio roda noutro dominio; caminho relativo apontaria errado."""
        for marca in logos.catalogo_com_logo():
            self.assertTrue(
                marca['logo'].startswith('http'),
                f"{marca['value']}: {marca['logo']!r}",
            )

    def test_bandeira_desconhecida_nao_quebra(self):
        """Sem logo a tela desenha so o nome — melhor que imagem quebrada."""
        self.assertEqual(bandeiras.logo('xpto'), '')
        self.assertEqual(logos.url_da_logo('xpto'), '')

    def test_sodexo_aparece_como_pluxee_mas_a_chave_nao_muda(self):
        """A marca virou Pluxee em 2024 e o cartao do cliente diz Pluxee. Mas o
        `value` segue 'sodexo' porque ja esta gravado nas lojas — trocar a
        chave orfanaria quem ja marcou a bandeira."""
        self.assertIn('sodexo', bandeiras.valores())
        self.assertEqual(bandeiras.rotulo('sodexo'), 'Pluxee')

    def test_marcas_da_loja_traz_os_tres_campos(self):
        marcas = logos.marcas_da_loja(['vr', 'ticket'])
        self.assertEqual([m['value'] for m in marcas], ['vr', 'ticket'])
        for m in marcas:
            self.assertTrue(m['label'])
            self.assertTrue(m['logo'])

    def test_bandeira_nova_nao_exige_deploy_de_frontend(self):
        """A prova da regra: acrescentar uma entrada no catalogo faz a API
        servi-la inteira — valor, rotulo e logo. O frontend so desenha."""
        nova = {'value': 'caju', 'label': 'Caju', 'logo': 'voucher/vr.svg'}
        original = bandeiras.CATALOGO
        try:
            bandeiras.CATALOGO = original + (nova,)
            servido = logos.catalogo_com_logo()
            caju = [m for m in servido if m['value'] == 'caju']
            self.assertEqual(len(caju), 1)
            self.assertEqual(caju[0]['label'], 'Caju')
            self.assertTrue(caju[0]['logo'].startswith('http'))
        finally:
            bandeiras.CATALOGO = original


class LogoAusenteNaoDerrubaOCheckoutTests(TestCase):
    """A logo e enfeite; a cobranca e o negocio. Enfeite nao pode derrubar."""

    def test_falha_no_estatico_vira_logo_vazia_e_nao_excecao(self):
        """O whitenoise roda com manifesto: sem `collectstatic`, `static()`
        levanta ValueError. Se isso subir, a config de pagamento devolve 500 e
        o cardapio inteiro morre por causa de uma imagem."""
        from unittest.mock import patch
        with patch('apps.stores.services.voucher.logos.static',
                   side_effect=ValueError('nao esta no manifesto')):
            self.assertEqual(logos.url_da_logo('vr'), '')
            marcas = logos.marcas_da_loja(['vr', 'sodexo'])
        # As bandeiras continuam la, com nome — so sem imagem.
        self.assertEqual([m['value'] for m in marcas], ['vr', 'sodexo'])
        self.assertEqual([m['label'] for m in marcas], ['VR Benefícios', 'Pluxee'])
        self.assertEqual([m['logo'] for m in marcas], ['', ''])
