"""O domínio próprio da loja precisa falar com a API sem um deploy antes.

O produto VENDE domínio próprio: "cesaladas.com.br" em vez de
"cardapidex.com.br/ce-saladas". Mas o CORS era uma lista estática em variável
de ambiente. Na prática:

    novo cliente assina → aponta o domínio dele → o cardápio abre → e NADA
    carrega, porque o navegador bloqueia toda chamada à API por CORS.

O conserto era editar a env e reiniciar o container. Ou seja: cada venda de
domínio próprio custava um deploy, e enquanto ele não acontecia o cliente via
a própria loja quebrada — no pior momento possível, o primeiro dia.

Medido em 06/09 contra a produção:

    https://cesaladas.com.br              → access-control-allow-origin OK
    https://dominio-de-cliente-novo.com   → SEM cabeçalho, navegador bloqueia

As duas lojas que hoje têm domínio próprio estão na lista porque alguém as
adicionou à mão. A terceira não estaria.

A saída é o sinal `check_request_enabled` do django-cors-headers: em vez de
uma lista fixa, o backend PERGUNTA se aquela origem é o domínio de alguma loja
ativa. A fonte da verdade passa a ser o cadastro da loja — que é onde o dono
já digita o domínio.
"""
import weakref

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.core.cors import origem_e_de_uma_loja
from apps.stores.models import Store

User = get_user_model()


class CorsDoDominioDaLojaTest(TestCase):
    def setUp(self):
        dona = User.objects.create_user(username='dona-cors', password='x')
        self.loja = Store.objects.create(
            billing_exempt=True, name='Cê Saladas', slug='ce-cors', owner=dona,
            store_type='food', status='active', custom_domain='cesaladas.com.br',
        )

    # ── o que precisa passar ────────────────────────────────────────────

    def test_dominio_cadastrado_e_liberado(self):
        self.assertTrue(origem_e_de_uma_loja('https://cesaladas.com.br'))

    def test_www_do_mesmo_dominio_tambem(self):
        """Quem digita o endereço escreve "www" na metade das vezes.

        Hoje o `www` só funciona por acidente: existe um redirecionamento 307
        no Cloudflare. Se ele cair, o CORS precisa aguentar sozinho.
        """
        self.assertTrue(origem_e_de_uma_loja('https://www.cesaladas.com.br'))

    def test_dominio_cadastrado_COM_www_libera_o_sem_www(self):
        self.loja.custom_domain = 'www.cesaladas.com.br'
        self.loja.save(update_fields=['custom_domain'])

        self.assertTrue(origem_e_de_uma_loja('https://cesaladas.com.br'))

    def test_o_dono_pode_digitar_o_dominio_com_esquema_e_barra(self):
        """`https://cesaladas.com.br/` é o que sai de um copiar e colar."""
        self.loja.custom_domain = 'https://cesaladas.com.br/'
        self.loja.save(update_fields=['custom_domain'])

        self.assertTrue(origem_e_de_uma_loja('https://cesaladas.com.br'))

    # ── o que NÃO pode passar ───────────────────────────────────────────

    def test_dominio_de_terceiro_nao_entra(self):
        self.assertFalse(origem_e_de_uma_loja('https://site-qualquer.com.br'))

    def test_dominio_parecido_nao_entra(self):
        """`cesaladas.com.br.evil.com` termina com o domínio e NÃO é ele.

        Casar por "termina com" é o erro clássico aqui, e ele entrega a API
        para qualquer um que registre um subdomínio.
        """
        self.assertFalse(origem_e_de_uma_loja('https://cesaladas.com.br.evil.com'))
        self.assertFalse(origem_e_de_uma_loja('https://naocesaladas.com.br'))

    def test_loja_inativa_nao_libera_nada(self):
        self.loja.status = 'inactive'
        self.loja.save(update_fields=['status'])

        self.assertFalse(origem_e_de_uma_loja('https://cesaladas.com.br'))

    def test_dominio_vazio_no_cadastro_nao_libera_origem_vazia(self):
        """`custom_domain=''` é o padrão de quem não tem domínio próprio.

        Sem esta guarda, string vazia casaria com qualquer coisa — e o
        `custom_domain` já causou um incidente por aceitar `''` (ago/16).
        """
        self.loja.custom_domain = ''
        self.loja.save(update_fields=['custom_domain'])

        self.assertFalse(origem_e_de_uma_loja(''))
        self.assertFalse(origem_e_de_uma_loja('https://qualquer.com'))

    def test_http_simples_nao_e_aceito(self):
        """Domínio de loja é https. Aceitar http abriria o token ao caminho."""
        self.assertFalse(origem_e_de_uma_loja('http://cesaladas.com.br'))

    def test_lixo_nao_derruba_a_requisicao(self):
        for entrada in (None, '', 'não é url', 'https://'):
            self.assertFalse(origem_e_de_uma_loja(entrada))


class CacheDoCorsTest(TestCase):
    """O domínio novo não pode esperar o cache vencer.

    A consulta é cacheada porque roda em TODA requisição com `Origin` — ir ao
    banco a cada uma faria do CORS um gargalo. Mas cache sem invalidação é o
    dono salvando o domínio, testando na hora e vendo a loja continuar
    quebrada por cinco minutos, sem entender por quê.
    """

    def setUp(self):
        from apps.core.cors import esquecer_dominios

        esquecer_dominios()
        dona = User.objects.create_user(username='dona-cache', password='x')
        self.loja = Store.objects.create(
            billing_exempt=True, name='Loja', slug='loja-cache', owner=dona,
            store_type='food', status='active', custom_domain='',
        )

    def test_salvar_o_dominio_libera_na_hora(self):
        self.assertFalse(origem_e_de_uma_loja('https://acabei-de-comprar.com.br'))

        self.loja.custom_domain = 'acabei-de-comprar.com.br'
        self.loja.save(update_fields=['custom_domain'])

        self.assertTrue(origem_e_de_uma_loja('https://acabei-de-comprar.com.br'))

    def test_tirar_o_dominio_bloqueia_na_hora(self):
        self.loja.custom_domain = 'vou-cancelar.com.br'
        self.loja.save(update_fields=['custom_domain'])
        self.assertTrue(origem_e_de_uma_loja('https://vou-cancelar.com.br'))

        self.loja.custom_domain = ''
        self.loja.save(update_fields=['custom_domain'])

        self.assertFalse(origem_e_de_uma_loja('https://vou-cancelar.com.br'))

    def test_desativar_a_loja_bloqueia_na_hora(self):
        self.loja.custom_domain = 'saiu-da-plataforma.com.br'
        self.loja.save(update_fields=['custom_domain'])
        self.assertTrue(origem_e_de_uma_loja('https://saiu-da-plataforma.com.br'))

        self.loja.status = 'inactive'
        self.loja.save(update_fields=['status'])

        self.assertFalse(origem_e_de_uma_loja('https://saiu-da-plataforma.com.br'))


class SinalConectadoTest(TestCase):
    """O handler existe E está ligado.

    Este projeto já se queimou exatamente assim: o `renovar()` do OAuth do
    Mercado Pago estava escrito, testado e SEM NENHUM CALLER — a loja
    conectava, funcionava, e pararia de vender seis meses depois. Handler de
    sinal tem o mesmo risco: passa em todo teste unitário e não roda nunca.
    """

    @staticmethod
    def _ligados(sinal):
        """Os handlers vivos de um sinal.

        Cada item de `Signal.receivers` é `(chave, receiver, ...)` — no Django
        5 virou 3-tupla por causa do suporte a async, então desempacotar em
        duas quebra. E `receiver` é uma `weakref` para função de módulo: sem
        dereferenciar, a comparação nunca casa.
        """
        vivos = []
        for entrada in sinal.receivers:
            receiver = entrada[1]
            vivos.append(receiver() if isinstance(receiver, weakref.ref) else receiver)
        return vivos

    def test_o_cors_pergunta_ao_cadastro_da_loja(self):
        from corsheaders.signals import check_request_enabled

        from apps.core.cors import liberar_dominio_de_loja

        self.assertIn(liberar_dominio_de_loja, self._ligados(check_request_enabled))

    def test_salvar_loja_derruba_o_cache_do_cors(self):
        from django.db.models.signals import post_save

        from apps.core.cors import esquecer_dominios_de_loja

        self.assertIn(esquecer_dominios_de_loja, self._ligados(post_save))
