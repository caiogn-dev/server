"""O e-mail é da LOJA, não da plataforma.

10/ago/2026 saiu uma campanha real da Cê Saladas para 39 endereços. Ela foi
assinada `Pastita <contato@pastita.com.br>`, com o botão apontando para
`https://pastita.com.br/cardapio`, na paleta vinho `#722F37` da Pastita antiga,
e o rodapé dizia **"Massas Artesanais"** — numa loja de saladas.

Tudo o que faltava estava no banco e era ignorado: `name`, `tagline`
("A salada mais falada de Palmas!"), `logo`, `primary_color` (#396d3e) e
`secondary_color` (#e87b21).

E 15 dos 39 destinatários eram endereços INVENTADOS pelo próprio sistema para
cliente de WhatsApp (`@whatsapp.bot`, `@local.invalid`). Mandar para eles não
entrega nada e queima a reputação do domínio no Resend.

⚠️ O endereço do remetente continua em `@pastita.com.br` porque é o ÚNICO
domínio verificado no Resend. Só o nome exibido muda — trocar o domínio antes de
verificar derruba o envio inteiro.
"""
import pytest

from apps.marketing.services.marca_da_loja import (
    ENDERECOS_FALSOS, contatos_reais, marca_da_loja, moldura,
)
from apps.stores.tests.factories import make_store


@pytest.fixture
def loja(db):
    store = make_store(name='Cê Saladas', slug='ce-saladas-marca')
    store.tagline = 'A salada mais falada de Palmas!'
    store.primary_color = '#396d3e'
    store.secondary_color = '#e87b21'
    store.save(update_fields=['tagline', 'primary_color', 'secondary_color'])
    return store


class TestMarcaDaLoja:
    def test_usa_o_nome_da_loja_e_nao_o_da_plataforma(self, loja):
        assert marca_da_loja(loja)['nome'] == 'Cê Saladas'

    def test_usa_as_cores_da_loja(self, loja):
        marca = marca_da_loja(loja)
        assert marca['cor_primaria'] == '#396d3e'
        assert marca['cor_secundaria'] == '#e87b21'

    def test_assinatura_e_a_tagline_da_loja_nao_massas_artesanais(self, loja):
        assert marca_da_loja(loja)['assinatura'] == 'A salada mais falada de Palmas!'

    def test_link_aponta_para_a_loja_certa(self, loja):
        """O SSOT do endereço público já existe — usar, não reinventar."""
        from apps.stores.services.checkout_service import CheckoutService

        esperado = CheckoutService.get_storefront_base_url(loja).rstrip('/')
        assert marca_da_loja(loja)['url'] == esperado
        assert 'pastita.com.br' not in marca_da_loja(loja)['url']

    def test_remetente_leva_o_nome_da_loja(self, loja):
        assert marca_da_loja(loja)['from_name'] == 'Cê Saladas'

    def test_remetente_fica_no_dominio_verificado(self, loja):
        """Trocar para um domínio não verificado no Resend derruba tudo."""
        assert marca_da_loja(loja)['from_email'].endswith('@pastita.com.br')

    def test_loja_sem_tagline_nao_inventa_assinatura(self, db):
        """Melhor sem assinatura do que com a de outra loja."""
        sem = make_store(name='Loja Nova')
        assert marca_da_loja(sem)['assinatura'] == ''

    def test_sem_loja_cai_na_plataforma_sem_explodir(self):
        marca = marca_da_loja(None)
        assert marca['nome']
        assert marca['from_email']


class TestContatosReais:
    """Endereço inventado pelo sistema não é destinatário."""

    def test_descarta_os_enderecos_que_o_proprio_sistema_inventa(self):
        entrada = [
            'leaniseciju@gmail.com',
            'whatsapp_556399547790@whatsapp.bot',
            '81081742@local.invalid',
            'mls.empreender77@gmail.com',
            'x@cliente.pastita.com.br',
        ]

        assert contatos_reais(entrada) == [
            'leaniseciju@gmail.com', 'mls.empreender77@gmail.com',
        ]

    def test_todo_sufixo_falso_conhecido_e_descartado(self):
        for sufixo in ENDERECOS_FALSOS:
            assert contatos_reais([f'alguem{sufixo}']) == []

    def test_lista_vazia_nao_explode(self):
        assert contatos_reais([]) == []
        assert contatos_reais(None) == []

    def test_aceita_objetos_com_atributo_email(self):
        """O caminho real itera Subscriber/EmailRecipient, não strings."""
        class _R:
            def __init__(self, email):
                self.email = email

        saida = contatos_reais([_R('ok@gmail.com'), _R('z@whatsapp.bot')])
        assert [r.email for r in saida] == ['ok@gmail.com']


class TestMoldura:
    """A moldura compartilhada pelos e-mails transacionais de marketing.

    Antes eram dois HTML duplicados (cupom e boas-vindas), cada um com a mesma
    paleta vinho, o mesmo 🍝 e o mesmo rodapé "Massas Artesanais" chumbados.
    Duplicata é como um dos dois fica para trás quando o outro é corrigido.
    """

    def test_pinta_com_a_cor_da_loja(self, loja):
        html = moldura(marca_da_loja(loja), titulo='Oi', corpo='<p>x</p>')

        assert '#396d3e' in html
        assert '#722F37' not in html

    def test_rodape_traz_o_nome_e_a_tagline_da_loja(self, loja):
        html = moldura(marca_da_loja(loja), titulo='Oi', corpo='<p>x</p>')

        assert 'Cê Saladas' in html
        assert 'A salada mais falada de Palmas!' in html
        assert 'Massas Artesanais' not in html

    def test_cta_aponta_para_a_loja(self, loja):
        html = moldura(
            marca_da_loja(loja), titulo='Oi', corpo='<p>x</p>',
            cta_texto='Ver cardápio', cta_url=marca_da_loja(loja)['url'],
        )

        assert 'Ver cardápio' in html
        assert 'pastita.com.br' not in html

    def test_sem_cta_nao_desenha_botao_vazio(self, loja):
        html = moldura(marca_da_loja(loja), titulo='Oi', corpo='<p>x</p>')

        assert '<a href' not in html

    def test_loja_sem_tagline_nao_imprime_linha_vazia(self, db):
        from apps.stores.tests.factories import make_store

        html = moldura(marca_da_loja(make_store(name='Loja Nova')), titulo='Oi', corpo='<p>x</p>')

        assert 'Loja Nova' in html
        assert '<br>\n' not in html.split('Loja Nova')[-1][:20]


class TestRespostaChegaEmAlguem:
    """Se o cliente responder o e-mail, alguém tem que receber.

    11/ago: o remetente é `contato@pastita.com.br` — endereço que existe só para
    ENVIAR (o Resend só exige o domínio verificado, não a caixa). O dono não tem
    essa caixa. E `cardapidex.com.br` não tem MX nenhum, então lá a resposta
    nem bounce gera: evapora.

    O `reply_to` caía em `store.email`, vazio na Cê Saladas — então a resposta
    voltava para a caixa inexistente. Agora cai no dono da loja.
    """

    def test_sem_email_na_loja_a_resposta_vai_para_o_dono(self, db):
        loja = make_store(name='Cê Saladas')
        loja.owner.email = 'dono@gmail.com'
        loja.owner.save(update_fields=['email'])

        assert marca_da_loja(loja)['reply_to'] == 'dono@gmail.com'

    def test_email_da_loja_ganha_do_email_do_dono(self, db):
        loja = make_store(name='Cê Saladas')
        loja.owner.email = 'dono@gmail.com'
        loja.owner.save(update_fields=['email'])
        loja.email = 'contato@cesaladas.com.br'
        loja.save(update_fields=['email'])

        assert marca_da_loja(loja)['reply_to'] == 'contato@cesaladas.com.br'

    def test_nunca_devolve_o_proprio_remetente_como_reply_to(self, db):
        """Responder para a caixa que ninguém lê é o mesmo que não ter reply_to."""
        loja = make_store(name='Sem Contato')
        loja.owner.email = ''
        loja.owner.save(update_fields=['email'])

        marca = marca_da_loja(loja)
        assert marca['reply_to'] != marca['from_email']
        assert marca['reply_to'] == ''
