"""Saladas criadas pelo cliente, guardadas pelo número dele (02/10).

O dono da Cê Saladas pediu: a salada que a pessoa montou e batizou fica salva.
Montada antes de entrar, mora no aparelho; ao entrar pelo código do WhatsApp,
sobe e passa a pertencer ao NÚMERO — qualquer aparelho que entrar com o código
daquele número vê as saladas.

A chave é o telefone PROVADO pelo código (`telefone_verificado`), nunca o
`profile.phone`, que o próprio cliente grava. A wishlist aceita o telefone que
vem no corpo e por isso lê a lista de qualquer número; aqui isso não pode.
"""
import uuid

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.core.models import UserProfile
from apps.stores.models import SaladaSalva, Store

User = get_user_model()
NUMERO = '5563991386719'
URL = '/api/v1/stores/{slug}/saladas/'


@pytest.fixture
def loja(db):
    dono = User.objects.create_user(username='dono-saladas', email='ds@t.local', password='x')
    return Store.objects.create(owner=dono, name='Cê', slug='ce-saladas-teste', store_type='food', status='active')


def _cliente(username, verificado='', phone=''):
    user = User.objects.create_user(username=username, email=f'{username}@t.local', password='x')
    perfil, _ = UserProfile.objects.get_or_create(user=user)
    perfil.phone = phone
    perfil.telefone_verificado = verificado
    perfil.save()
    user = User.objects.get(pk=user.pk)
    c = APIClient()
    c.force_authenticate(user)
    return c


def _salada(nome='Verde Power', client_id=None):
    return {
        'client_id': str(client_id or uuid.uuid4()),
        'nome': nome,
        'ingredientes': [
            {'id': 'b1', 'name': 'Alface', 'role': 'base', 'role_label': 'Base',
             'image_url': 'https://backend.pastita.com.br/media/alface.webp'},
            {'id': 'm4', 'name': 'Maracujá', 'role': 'molhos', 'role_label': 'Molhos'},
        ],
    }


@pytest.mark.django_db
class TestSaladasSalvas:
    def test_sobe_e_aparece_em_outro_aparelho_do_mesmo_numero(self, loja):
        celular = _cliente('cel', verificado=NUMERO)
        r = celular.post(URL.format(slug=loja.slug), {'saladas': [_salada()]}, format='json')
        assert r.status_code == 200, r.content

        # Outro login com o código do MESMO número (wa_id sem o nono dígito).
        notebook = _cliente('note', verificado='556391386719')
        r = notebook.get(URL.format(slug=loja.slug))
        assert [s['nome'] for s in r.json()['saladas']] == ['Verde Power']
        assert r.json()['saladas'][0]['ingredientes'][0]['role_label'] == 'Base'

    def test_sincronizar_de_novo_nao_duplica(self, loja):
        c = _cliente('cel', verificado=NUMERO)
        s = _salada(client_id=uuid.uuid4())
        c.post(URL.format(slug=loja.slug), {'saladas': [s]}, format='json')
        s['nome'] = 'Verde Power 2'
        r = c.post(URL.format(slug=loja.slug), {'saladas': [s]}, format='json')
        assert [x['nome'] for x in r.json()['saladas']] == ['Verde Power 2']
        assert SaladaSalva.objects.count() == 1

    def test_perfil_com_numero_alheio_nao_le_nem_grava(self, loja):
        _cliente('dono-do-numero', verificado=NUMERO).post(
            URL.format(slug=loja.slug), {'saladas': [_salada()]}, format='json')
        atacante = _cliente('atacante', phone=NUMERO)  # gravou o número no perfil, sem código
        assert atacante.get(URL.format(slug=loja.slug)).status_code == 403
        assert atacante.post(URL.format(slug=loja.slug), {'saladas': [_salada()]}, format='json').status_code == 403

    def test_visitante_sem_login_recebe_401_ou_403(self, loja):
        assert APIClient().get(URL.format(slug=loja.slug)).status_code in (401, 403)

    def test_outro_numero_nao_ve(self, loja):
        _cliente('a', verificado=NUMERO).post(URL.format(slug=loja.slug), {'saladas': [_salada()]}, format='json')
        r = _cliente('b', verificado='5511976457452').get(URL.format(slug=loja.slug))
        assert r.json()['saladas'] == []

    def test_apagar(self, loja):
        c = _cliente('cel', verificado=NUMERO)
        r = c.post(URL.format(slug=loja.slug), {'saladas': [_salada()]}, format='json')
        sid = r.json()['saladas'][0]['id']
        outro = _cliente('outro', verificado='5511976457452')
        assert outro.delete(f'{URL.format(slug=loja.slug)}{sid}/').status_code == 404
        assert c.delete(f'{URL.format(slug=loja.slug)}{sid}/').status_code == 204
        assert c.get(URL.format(slug=loja.slug)).json()['saladas'] == []

    @pytest.mark.parametrize('ruim', [
        {'nome': '', 'ingredientes': [{'id': 'b1', 'name': 'Alface'}]},
        {'nome': 'X', 'ingredientes': []},
        {'nome': 'X', 'ingredientes': 'Alface'},
        {'client_id': 'nao-e-uuid', 'nome': 'X', 'ingredientes': [{'id': 'b1', 'name': 'Alface'}]},
    ])
    def test_rejeita_salada_malformada(self, loja, ruim):
        c = _cliente('cel', verificado=NUMERO)
        payload = {'client_id': str(uuid.uuid4()), **ruim}
        assert c.post(URL.format(slug=loja.slug), {'saladas': [payload]}, format='json').status_code == 400

    def test_foto_so_aceita_https(self, loja):
        c = _cliente('cel', verificado=NUMERO)
        s = _salada()
        s['ingredientes'][0]['image_url'] = 'javascript:alert(1)'
        r = c.post(URL.format(slug=loja.slug), {'saladas': [s]}, format='json')
        assert r.json()['saladas'][0]['ingredientes'][0]['image_url'] == ''
