"""Triagem: decidir o que a pessoa quer ANTES de olhar o estado da conversa.

Os casos abaixo são a conversa real da Yeda com a Cê Saladas em 13/ago, onde o
bot custou um pedido: montou R$ 20, a dona cancelou e refez R$ 100 na mão.

O que falhava não era falta de inteligência, era ordem de decisão:

- "Qual opção de hj"        → regex não casa → UNKNOWN → resposta genérica
- "Batatas"                 → regex não casa → UNKNOWN → SILÊNCIO
- "Quero salada"            → o estado `waiting_for_notes` engolia antes de
                              qualquer roteamento → "✅ Anotado: Quero salada"

Contrato da triagem:

1. Ela DECIDE, nunca age. Quem cria pedido, calcula frete e gera PIX continua
   sendo o handler determinístico.
2. Regex primeiro. O caminho quente ("oi", "cardápio", clique de botão) não
   chega a tocar em LLM — foi a latência de 3 min que motivou isso.
3. O LLM é injetado. Sem ele a triagem continua funcionando pelo catálogo, e
   todo teste aqui roda sem modelo nenhum.
4. Falha do classificador nunca vira silêncio: cai no determinístico.
"""
import pytest

from apps.automation.services.triagem import Decisao, Intencao, triar
from apps.stores.tests.factories import make_store


@pytest.fixture
def loja(db):
    from apps.stores.models import StoreProduct

    store = make_store(name='Cê Saladas')
    for nome in ('Monte sua Salada', 'Salada Caesar', 'Suco de laranja 400ml',
                 'Cebola roxa', 'Batata rústica', 'Molho'):
        StoreProduct.objects.create(
            store=store, name=nome, slug=nome.lower().replace(' ', '-'),
            price=20, is_active=True,
        )
    return store


class TestOsCasosDaYeda:
    def test_pergunta_aberta_vira_consultiva_e_nao_unknown(self, loja):
        """'Qual opção de hj' recebeu 'Como posso te ajudar? 👇'."""
        d = triar('Qual opção de hj', store=loja)

        assert d.intencao is Intencao.CONSULTIVA
        assert d.precisa_de_resposta is True

    def test_nome_de_produto_solto_vira_item(self, loja):
        """'Batatas' foi silêncio absoluto."""
        d = triar('Batatas', store=loja)

        assert d.intencao is Intencao.ITEM
        assert d.itens and d.itens[0].name == 'Batata rústica'

    def test_pedir_produto_esperando_observacao_e_item_nao_nota(self, loja):
        """O caso que custou o pedido."""
        d = triar('Quero salada', store=loja, esperando='observacao')

        assert d.intencao is Intencao.ITEM, d

    def test_frase_ambigua_devolve_os_candidatos_em_vez_de_chutar(self, loja):
        """'salada' casa 'Monte sua Salada' E 'Salada Caesar'.

        Escolher uma no chute é exatamente como item errado entra no carrinho.
        A ambiguidade tem que sobreviver até quem pergunta ao cliente.
        """
        d = triar('Quero salada', store=loja)

        nomes = {p.name for p in d.itens}
        assert {'Monte sua Salada', 'Salada Caesar'} <= nomes, nomes
        assert d.confianca < 1.0

    def test_observacao_de_verdade_continua_observacao(self, loja):
        """'Cebola roxa' é produto na Cê Saladas — negação tem que ganhar."""
        d = triar('sem cebola', store=loja, esperando='observacao')

        assert d.intencao is Intencao.OBSERVACAO
        assert d.texto == 'sem cebola'

    def test_fora_do_estado_de_observacao_negacao_nao_vira_nota(self, loja):
        d = triar('sem cebola', store=loja)

        assert d.intencao is not Intencao.OBSERVACAO


class TestCaminhoQuenteNaoTocaLLM:
    def test_saudacao_resolve_sem_classificador(self, loja):
        chamou = []
        d = triar('oi', store=loja, classificador=lambda *a, **k: chamou.append(1))

        assert d.intencao is Intencao.SAUDACAO
        assert chamou == [], 'saudação não pode custar uma chamada de LLM'

    def test_produto_do_catalogo_resolve_sem_classificador(self, loja):
        chamou = []
        triar('Suco de laranja 400ml', store=loja,
              classificador=lambda *a, **k: chamou.append(1))

        assert chamou == []

    def test_so_chama_o_classificador_quando_nao_sabe(self, loja):
        chamadas = []

        def classificador(texto, **_):
            chamadas.append(texto)
            return Decisao(intencao=Intencao.CONSULTIVA)

        # Não pode ser pergunta: interrogativa agora resolve como consultiva
        # SEM LLM, de propósito — pergunta é consultiva por definição, e uma
        # chamada de modelo para confirmar isso seria dinheiro e latência a
        # troco de nada.
        triar('acho que vou levar aquilo de sempre mesmo viu', store=loja,
              classificador=classificador)

        assert chamadas, 'frase que o regex não entende tem que chegar no LLM'


class TestNuncaCalar:
    def test_classificador_que_explode_cai_no_deterministico(self, loja):
        def explode(*_a, **_k):
            raise TimeoutError('modelo fora do ar')

        d = triar('uma frase que o regex nao conhece', store=loja,
                  classificador=explode)

        assert d.precisa_de_resposta is True
        assert d.intencao is Intencao.CONSULTIVA

    def test_classificador_que_devolve_lixo_cai_no_deterministico(self, loja):
        d = triar('outra frase estranha', store=loja,
                  classificador=lambda *a, **k: {'intencao': 'inventada'})

        assert d.precisa_de_resposta is True

    def test_mensagem_vazia_nao_pede_resposta(self, loja):
        assert triar('', store=loja).precisa_de_resposta is False


class TestNaoAge:
    def test_decisao_nao_tem_efeito_colateral(self, loja):
        """A triagem não escreve. É o que separa 'entende' de 'executa'."""
        from apps.stores.models import StoreCart

        antes = StoreCart.objects.count()
        triar('Quero salada', store=loja, esperando='observacao')

        assert StoreCart.objects.count() == antes


class TestCombosContam:
    """A Cê Saladas vende salada por COMBO, não por produto avulso.

    Descoberto rodando contra o catálogo real: `candidatos_de_produto` varria só
    StoreProduct, então "Quero salada" — o caso que motivou tudo isto — voltava
    vazio e caía em observação de novo. O teste sintético passava porque a
    fixture só tinha produtos.
    """

    def test_combo_conta_como_item(self, db):
        from apps.stores.models import StoreCombo
        from apps.stores.tests.factories import make_store

        store = make_store(name='Cê Saladas Combos')
        StoreCombo.objects.create(
            store=store, name='COMBO 5 SALADAS', slug='combo-5-saladas',
            price=100, is_active=True,
        )

        d = triar('Quero salada', store=store, esperando='observacao')

        assert d.intencao is Intencao.ITEM, d
        assert d.itens[0].name == 'COMBO 5 SALADAS'


class TestEstadoNaoCapturaPedidoDeProduto:
    """O portão do checkout consulta a triagem antes de engolir o texto.

    `unified_service` tinha uma condição que dizia: se existe sessão esperando
    endereço ou observação, mande TODO texto para o handler de checkout. Era ela
    que fazia "Quero salada" virar nota antes de qualquer roteamento acontecer.

    Agora a pergunta muda de "existe estado?" para "existe estado E a mensagem
    pertence a ele?".
    """

    def _servico(self, store):
        """Serviço COM checkout aberto esperando observação.

        Sem a sessão pendente o portão nunca captura e o teste passa sem provar
        nada — foi o que aconteceu na primeira rodada.
        """
        from apps.automation.models import CompanyProfile, CustomerSession
        from apps.automation.services.unified_service import UnifiedService
        from apps.conversations.models import Conversation
        from apps.whatsapp.models import WhatsAppAccount

        conta = WhatsAppAccount.objects.create(
            name='T', phone_number_id='PHTRI', waba_id='WTRI',
        )
        # Loja e conta criam CADA UMA o seu profile por signal, e ele é 1:1 com
        # as duas pontas — descartar o órfão antes de juntar.
        CompanyProfile.objects.filter(store=store).exclude(account=conta).delete()
        perfil = CompanyProfile.objects.get(account=conta)
        perfil.store = store
        perfil.save(update_fields=['store'])
        conversa = Conversation.objects.create(account=conta, phone_number='5563900000000')
        CustomerSession.objects.create(
            company=perfil, phone_number='5563900000000',
            session_id='whatsapp_5563900000000_tri',
            status=CustomerSession.SessionStatus.CHECKOUT,
            cart_data={'waiting_for_notes': True},
        )
        servico = UnifiedService(conta, conversa, use_llm=False)
        servico.store = store
        return servico

    def test_pedido_de_produto_escapa_do_estado(self, loja):
        assert self._servico(loja)._estado_deve_capturar('Quero salada') is False

    def test_observacao_continua_sendo_capturada(self, loja):
        assert self._servico(loja)._estado_deve_capturar('sem cebola') is True

    def test_texto_qualquer_continua_sendo_capturado(self, loja):
        """Endereço digitado à mão não pode escapar — é o caso comum."""
        assert self._servico(loja)._estado_deve_capturar(
            'Quadra 110 Norte Alameda 23'
        ) is True


class TestPerguntaNaoEhPedido:
    """Interrogativa que cita produto é DÚVIDA, não pedido.

    Descoberto na avaliação com 4 personas (13/ago), 3 erros em 20 e todos do
    mesmo tipo:

        "voces so tem salada?"               -> item (era consultiva)
        "qual a diferenca do combo 5 pro 8?" -> item (era consultiva)
        "o molho vem junto?"                 -> item (era consultiva)

    O terceiro é o mais grave: é a dúvida do molho que abriu esta sessão. O bot
    ia ADICIONAR molho ao carrinho em vez de explicar que ele é vendido à parte.

    É o espelho da regra de negação: o casador de catálogo dispara antes de
    alguém perguntar que tipo de frase é aquela.
    """

    def test_pergunta_com_interrogacao_nao_vira_item(self, loja):
        d = triar('voces so tem salada?', store=loja)
        assert d.intencao is Intencao.CONSULTIVA, d

    def test_pergunta_sobre_o_que_acompanha_nao_adiciona_o_acompanhamento(self, loja):
        """O caso do molho — a dúvida que começou tudo."""
        from apps.stores.models import StoreProduct

        StoreProduct.objects.create(
            store=loja, name='Molho branco', slug='molho-branco',
            price=8, is_active=True,
        )

        d = triar('o molho vem junto?', store=loja)

        assert d.intencao is Intencao.CONSULTIVA, d

    def test_interrogativa_sem_ponto_tambem_conta(self, loja):
        """Cliente no WhatsApp quase nunca põe o ponto de interrogação."""
        for frase in ('qual a diferenca da salada caesar',
                      'quanto custa o suco de laranja',
                      'tem salada de frango'):
            assert triar(frase, store=loja).intencao is Intencao.CONSULTIVA, frase

    def test_pedido_de_verdade_continua_item(self, loja):
        """A regra não pode engolir quem está comprando."""
        for frase in ('quero salada', 'manda um suco de laranja', 'mais um molho'):
            assert triar(frase, store=loja).intencao is Intencao.ITEM, frase


class TestRankingPorPalavrasQueCasam:
    def test_ganha_quem_casa_mais_palavras_nao_quem_tem_nome_curto(self, db):
        """'quero 2 combos de 5 saladas' devolvia 'Combo Salmão'.

        O desempate era só pelo nome mais curto, então qualquer 'Combo X' ganhava
        de 'COMBO 5 SALADAS', que casa DUAS palavras da frase.
        """
        from apps.stores.models import StoreCombo
        from apps.stores.tests.factories import make_store

        store = make_store(name='CS')
        for nome in ('COMBO 5 SALADAS', 'Combo Salmão', 'Combo Tilápia'):
            StoreCombo.objects.create(
                store=store, name=nome, slug=nome.lower().replace(' ', '-'),
                price=100, is_active=True,
            )

        d = triar('quero 2 combos de 5 saladas', store=store)

        assert d.itens[0].name == 'COMBO 5 SALADAS', [p.name for p in d.itens]


class TestNegacaoNaoCasaDentroDePalavra:
    """"sempre" contém "sem" — e isso quebrava o pedido do cliente fiel.

    `tem_negacao` fazia `n.strip()` e comparava por SUBSTRING, então 'sem '
    virava 'sem' e casava dentro de "sempre", "semana", "sementes". "quero o de
    sempre" era lido como negação e nunca chegava a virar item.

    Descoberto na avaliação com personas, não em teste sintético: a frase que
    expõe isso é coisa de cliente habitual, não de caso de teste.
    """

    def test_sempre_nao_e_negacao(self, loja):
        from apps.stores.services.busca_de_produto import tem_negacao

        assert tem_negacao('quero o de sempre') is False

    def test_semana_e_sementes_tambem_nao(self, loja):
        from apps.stores.services.busca_de_produto import tem_negacao

        assert tem_negacao('toda semana eu peço') is False
        assert tem_negacao('poe sementes') is False

    def test_negacao_de_verdade_continua_pegando(self, loja):
        from apps.stores.services.busca_de_produto import tem_negacao

        for frase in ('sem cebola', 'sem o tomate', 'tirar a alface',
                      'nao quero queijo', 'nada de azeitona'):
            assert tem_negacao(frase) is True, frase
