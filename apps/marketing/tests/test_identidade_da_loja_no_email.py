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
    ENDERECOS_FALSOS, REMETENTE_DA_PLATAFORMA, contatos_reais, marca_da_loja,
    moldura,
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
        """Trocar para um domínio não verificado no Resend derruba tudo.

        Travar a CONSTANTE e não o domínio da vez: em 11/ago ele mudou de
        pastita.com.br para cardapidex.com.br, e teste com literal só teria
        avisado depois do envio já ter caído.
        """
        assert marca_da_loja(loja)['from_email'] == REMETENTE_DA_PLATAFORMA

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


class TestLogoAbsolutaNoEmail:
    """Logo em caminho relativo não existe dentro de um e-mail.

    11/ago, teste real na caixa do dono: a logo não apareceu. `store.logo.url`
    devolve `/media/stores/logos/ce-saladas-logo.jpg`, que só resolve em quem
    está navegando no domínio do backend. O cliente abre no Gmail — para ele
    aquilo é caminho para lugar nenhum.

    O arquivo já era público (HEAD 200 image/jpeg em backend.pastita.com.br),
    só faltava o endereço completo.
    """

    def test_logo_relativa_vira_absoluta(self, loja):
        """Testa o resolvedor de endereço, não a derivada leve.

        `marca_da_loja` passou a devolver a versão reduzida (ver
        test_logo_do_email.py); quem transforma `/media/...` em URL completa
        continua sendo esta função.
        """
        from apps.marketing.services.marca_da_loja import _logo_absoluta

        loja.logo = 'stores/logos/ce-saladas.jpg'
        loja.save(update_fields=['logo'])

        logo = _logo_absoluta(loja)

        assert logo.startswith('https://')
        assert logo.endswith('/media/stores/logos/ce-saladas.jpg')

    def test_logo_ja_absoluta_nao_e_remexida(self, loja):
        loja.logo_url = 'https://cdn.exemplo.com/logo.png'
        loja.save(update_fields=['logo_url'])

        assert marca_da_loja(loja)['logo_url'] == 'https://cdn.exemplo.com/logo.png'

    def test_sem_logo_continua_vazio(self, db):
        assert marca_da_loja(make_store(name='Sem Logo'))['logo_url'] == ''

    def test_moldura_nao_desenha_img_quebrada(self, db):
        html = moldura(marca_da_loja(make_store(name='Sem Logo')), titulo='Oi', corpo='<p>x</p>')

        assert '<img' not in html


class TestRemetenteProprioDaLoja:
    """Opção B: loja com domínio próprio verificado envia do endereço dela.

    Decisão de 11/ago: manter a opção A como padrão (um domínio da plataforma
    serve todas as lojas, inclusive as que nunca terão domínio) e deixar a B
    pronta e DESLIGADA, como foi feito com o OAuth do Mercado Pago.

    A guarda que justifica o campo separado: se a loja preencher um domínio que
    NÃO está verificado no Resend, todo envio dela para de sair. Por isso o
    remetente próprio só vale quando alguém confirmou a verificação — o campo de
    texto sozinho não basta.
    """

    def test_desligado_por_padrao_usa_o_dominio_da_plataforma(self, loja):
        assert marca_da_loja(loja)['from_email'] == REMETENTE_DA_PLATAFORMA

    def test_endereco_proprio_sem_verificacao_e_ignorado(self, loja):
        """Estado perigoso: preencheu mas ninguém verificou no Resend."""
        loja.email_remetente = 'contato@cesaladas.com.br'
        loja.remetente_verificado = False
        loja.save(update_fields=['email_remetente', 'remetente_verificado'])

        assert marca_da_loja(loja)['from_email'] == REMETENTE_DA_PLATAFORMA

    def test_endereco_proprio_verificado_e_usado(self, loja):
        loja.email_remetente = 'contato@cesaladas.com.br'
        loja.remetente_verificado = True
        loja.save(update_fields=['email_remetente', 'remetente_verificado'])

        assert marca_da_loja(loja)['from_email'] == 'contato@cesaladas.com.br'

    def test_verificado_sem_endereco_nao_inventa(self, loja):
        loja.email_remetente = ''
        loja.remetente_verificado = True
        loja.save(update_fields=['email_remetente', 'remetente_verificado'])

        assert marca_da_loja(loja)['from_email'] == REMETENTE_DA_PLATAFORMA

    def test_reply_to_nao_repete_o_remetente_proprio(self, loja):
        """Com remetente próprio, responder para ele mesmo não acrescenta nada."""
        loja.email_remetente = 'contato@cesaladas.com.br'
        loja.remetente_verificado = True
        loja.email = 'contato@cesaladas.com.br'
        loja.save(update_fields=['email_remetente', 'remetente_verificado', 'email'])

        marca = marca_da_loja(loja)
        assert marca['reply_to'] != marca['from_email']


class TestRemetentePadraoDaPlataforma:
    """O domínio de envio da plataforma tem UMA fonte.

    11/ago: o dono trocou `pastita.com.br` por `cardapidex.com.br` no Resend e o
    envio caiu inteiro ("domain is not verified"), porque o endereço padrão
    estava escrito à mão em três arquivos (marca_da_loja, email_marketing_service
    e alerta_coex) e nenhum sabia da troca.
    """

    def test_o_padrao_e_o_dominio_verificado_atual(self):
        from apps.marketing.services.marca_da_loja import REMETENTE_DA_PLATAFORMA

        assert REMETENTE_DA_PLATAFORMA.endswith('@cardapidex.com.br')

    def test_loja_sem_remetente_proprio_usa_o_padrao(self, loja):
        from apps.marketing.services.marca_da_loja import REMETENTE_DA_PLATAFORMA

        assert marca_da_loja(loja)['from_email'] == REMETENTE_DA_PLATAFORMA

    def test_o_alerta_de_queda_usa_o_mesmo_remetente(self):
        """O aviso de ponte caída não pode ser o único que não sai."""
        import inspect

        from apps.whatsapp.services import alerta_coex

        assert 'pastita.com.br' not in inspect.getsource(alerta_coex)

    def test_variavel_de_ambiente_ainda_manda(self):
        """Trocar de domínio de novo não pode exigir deploy."""
        import importlib
        import os
        from unittest.mock import patch

        with patch.dict(os.environ, {'RESEND_FROM_EMAIL': 'x@outro.com'}):
            from apps.marketing.services import marca_da_loja as m
            importlib.reload(m)
            try:
                assert m.marca_da_loja(None)['from_email'] == 'x@outro.com'
            finally:
                importlib.reload(m)
