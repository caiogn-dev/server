"""O painel pergunta ao backend quais templates existem.

A lista vivia escrita à mão em `StorefrontPage.tsx`, com um comentário dizendo
"espelha o backend" — e espelho é exatamente o problema: quando o `banquete`
entrou no storefront, o painel não soube. O template existia na tela pública,
era invisível no painel, e só dava para ligar por script no banco.

Agora quem sabe quais templates existem é quem valida: o model. O painel
consome, não copia. Adicionar um template passa a ser uma linha em
`StoreTemplate` + os arquivos do storefront — o painel se atualiza sozinho.
"""
import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.stores.models import Store


@pytest.fixture
def cliente():
    return APIClient()


@pytest.mark.django_db
class TestOCatalogoDeTemplates:
    def test_lista_todos_os_templates_do_model(self, cliente):
        r = cliente.get('/api/v1/stores/templates/')
        assert r.status_code == 200

        ids = [t['id'] for t in r.json()['results']]
        assert ids == [slug for slug, _ in Store.StoreTemplate.choices]

    def test_cada_template_traz_o_que_a_tela_precisa(self, cliente):
        r = cliente.get('/api/v1/stores/templates/')
        for t in r.json()['results']:
            # `label` nomeia, `description` diz PARA QUEM serve (é o que faz o
            # dono decidir), `preview` é o símbolo do cartão.
            assert t['label']
            assert 'ideal para' in t['description'].lower()
            assert t['preview']

    def test_o_banquete_esta_la(self, cliente):
        r = cliente.get('/api/v1/stores/templates/')
        banquete = next(t for t in r.json()['results'] if t['id'] == 'banquete')
        # A vantagem que decide a escolha: funciona sem foto.
        assert 'foto' in banquete['description'].lower()

    def test_template_novo_aparece_sem_tocar_no_painel(self, cliente):
        """O ponto da mudança: a lista é derivada, não copiada."""
        r = cliente.get('/api/v1/stores/templates/')
        assert len(r.json()['results']) == len(Store.StoreTemplate.choices)

    def test_e_publico_e_nao_exige_login(self, cliente):
        """A tela de aparência carrega antes de qualquer escolha de loja."""
        assert cliente.get('/api/v1/stores/templates/').status_code == 200
