"""Resumo do programa de fidelidade: agregado no banco, não na página.

A tela de Fidelidade mostrava "Participantes" e mais nada. Os números que o
dono realmente pergunta — quantos já podem resgatar, quantos brindes já saíram,
quantos estão a um item de fechar o cartão — não existiam.

Dava para somar no frontend a partir da lista, e é justamente o que NÃO se pode
fazer: a lista é paginada de 50 em 50. Somar a primeira página produz um número
menor que o real, com cara de total. Número errado com aparência de certo é pior
que número ausente, porque ninguém desconfia dele.

`quase_la` usa o corte de 1 item porque é o gatilho acionável: "falta 1 para
você ganhar" é uma mensagem que se manda hoje e converte. "Falta 5" não é.
"""
import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.stores.models import Store, StoreLoyaltyAccount

User = get_user_model()


@pytest.fixture
def loja(db):
    dono = User.objects.create_user(username='dono-loy', email='dono-loy@x.com', password='x')
    # `status='active'`: get_active_store() só enxerga loja ativa, e o default
    # do model não é esse.
    loja = Store.objects.create(
        name='Loja Loy', slug='loja-loy', owner=dono, status='active',
    )
    meta = loja.metadata or {}
    meta.update({'loyalty_enabled': True, 'loyalty_salads_required': 10})
    loja.metadata = meta
    loja.save(update_fields=['metadata'])
    return loja


@pytest.fixture
def api(loja):
    c = APIClient()
    c.force_authenticate(user=loja.owner)
    return c


def _conta(loja, i, qualificados, resgatados=0):
    user = User.objects.create_user(username=f'cli{i}', email=f'cli{i}@x.com', password='x')
    return StoreLoyaltyAccount.objects.create(
        store=loja, user=user,
        qualified_count=qualificados, redeemed_count=resgatados,
    )


def _resumo(api, loja):
    r = api.get(f'/api/v1/stores/{loja.slug}/loyalty/accounts/', {'resumo': '1'})
    assert r.status_code == 200, r.content
    return r.json()['resumo']


@pytest.mark.django_db
class TestResumoFidelidade:
    def test_conta_participantes_brindes_disponiveis_e_resgatados(self, api, loja):
        _conta(loja, 1, qualificados=25, resgatados=1)   # 2 ganhos, 1 usado → 1 disponível
        _conta(loja, 2, qualificados=10, resgatados=0)   # 1 ganho, 0 usado  → 1 disponível
        _conta(loja, 3, qualificados=3, resgatados=0)    # nada ainda

        r = _resumo(api, loja)
        assert r['participantes'] == 3
        assert r['brindes_disponiveis'] == 2
        assert r['brindes_resgatados'] == 1

    def test_quase_la_conta_quem_esta_a_um_item_do_brinde(self, api, loja):
        _conta(loja, 1, qualificados=9)    # falta 1 → quase lá
        _conta(loja, 2, qualificados=19)   # 19 % 10 = 9, falta 1 → quase lá
        _conta(loja, 3, qualificados=7)    # falta 3 → não
        _conta(loja, 4, qualificados=10)   # fechou o cartão, não está "quase"

        assert _resumo(api, loja)['quase_la'] == 2

    def test_agregado_cobre_alem_da_primeira_pagina(self, api, loja):
        # 60 contas: somar o que a página devolve daria 50. O agregado é do
        # banco inteiro — é a razão de existir deste endpoint.
        for i in range(60):
            _conta(loja, i, qualificados=10)

        r = _resumo(api, loja)
        assert r['participantes'] == 60
        assert r['brindes_disponiveis'] == 60

    def test_resgates_a_mais_nao_viram_saldo_negativo(self, api, loja):
        # Dado inconsistente acontece (resgate manual, restauração de backup).
        # Um "-3 brindes disponíveis" na tela destrói a confiança no número.
        _conta(loja, 1, qualificados=10, resgatados=5)
        assert _resumo(api, loja)['brindes_disponiveis'] == 0

    def test_sem_resumo_a_resposta_nao_muda(self, api, loja):
        # A lista existente é usada por outra tela: não pode passar a carregar
        # peso extra só porque um consumidor novo precisa de agregado.
        _conta(loja, 1, qualificados=10)
        r = api.get(f'/api/v1/stores/{loja.slug}/loyalty/accounts/')
        assert r.status_code == 200
        assert 'resumo' not in r.json()

    def test_loja_de_outro_dono_e_negada(self, loja):
        outro = User.objects.create_user(username='intruso', email='in@x.com', password='x')
        c = APIClient()
        c.force_authenticate(user=outro)
        r = c.get(f'/api/v1/stores/{loja.slug}/loyalty/accounts/', {'resumo': '1'})
        assert r.status_code == 403


@pytest.mark.django_db
class TestOrdemDaListaDeFidelidade:
    """A lista ordena por quem está mais perto de ganhar, não por quem comprou
    por último.

    Era `-updated_at`, que responde "quem comprou recentemente" — pergunta que
    a lista de pedidos já responde melhor. A pergunta desta tela é outra: a
    quem eu mando mensagem HOJE. Quem está a 1 item do brinde converte com um
    empurrão; quem acabou de começar o cartão, não.
    """

    def _linhas(self, api, loja):
        r = api.get(f'/api/v1/stores/{loja.slug}/loyalty/accounts/')
        assert r.status_code == 200, r.content
        return r.json()['results']

    def test_o_mais_perto_do_brinde_vem_primeiro(self, api, loja):
        _conta(loja, 1, qualificados=2)    # falta 8
        _conta(loja, 2, qualificados=9)    # falta 1  ← topo
        _conta(loja, 3, qualificados=5)    # falta 5

        faltas = [l['falta'] for l in self._linhas(api, loja)]
        assert faltas == [1, 5, 8], f'esperado do mais perto ao mais longe, veio {faltas}'

    def test_quem_acabou_de_fechar_o_cartao_vai_para_o_fim(self, api, loja):
        # Resto 0 significa cartão novo começando do zero — está LONGE do
        # próximo brinde, não perto. Tratar como "falta 0" o jogaria para o
        # topo e a lista viraria mentira.
        _conta(loja, 1, qualificados=10)   # fechou: falta 10 para o próximo
        _conta(loja, 2, qualificados=8)    # falta 2

        faltas = [l['falta'] for l in self._linhas(api, loja)]
        assert faltas == [2, 10]

    def test_empate_desempata_por_quem_comprou_mais(self, api, loja):
        # Dois a 1 item do brinde: o que já comprou mais no total vale mais.
        _conta(loja, 1, qualificados=9)    # falta 1, total 9
        _conta(loja, 2, qualificados=29)   # falta 1, total 29 ← topo

        totais = [l['qualified_count'] for l in self._linhas(api, loja)]
        assert totais == [29, 9]
