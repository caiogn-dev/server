"""Uma pessoa, um perfil de CRM — com ou sem o nono dígito.

Produção, 15/set: 69 pessoas com 73 perfis a mais. O WhatsApp entrega o
telefone sem o nono dígito (556384289103) e o site grava com ele
(5563984289103). `UnifiedUser._phone_candidates` gerava variantes com/sem `+`
e 55, mas nunca com/sem o nono dígito — então cada porta criava o seu. O perfil
do site ficava com login, pedidos e endereços; o do WhatsApp com as mensagens.
"""
from io import StringIO

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command

from apps.stores.models import StoreCustomer
from apps.stores.tests.factories import make_store
from apps.users.models import UnifiedUser, UnifiedUserActivity, UserAddress

User = get_user_model()
SITE = '5563992338269'
WHATS = '556392338269'


@pytest.mark.django_db
def test_resolve_pelo_whatsapp_acha_o_perfil_do_site():
    site = UnifiedUser.objects.create(phone_number=SITE, name='Wanny Tapajos')

    achado, criado = UnifiedUser.resolve(phone=WHATS, name='Wanny')

    assert not criado
    assert achado.id == site.id
    assert UnifiedUser.objects.count() == 1


@pytest.fixture
def wanny(db):
    loja = make_store(name='Cê Perfis', city='Palmas', state='TO')
    login = User.objects.create_user(username='wanny_login', password='x')
    site = UnifiedUser.objects.create(phone_number=SITE, name='Wanny Tapajos',
                                      email='wanny@example.com', django_user=login)
    StoreCustomer.objects.create(store=loja, user=login, unified_user=site)
    UserAddress.objects.create(unified_user=site, tenant=loja, street='Quadra 501 Sul Avenida NS 1',
                               number='9', city='Palmas', state='TO', is_default=True)
    whats = UnifiedUser.objects.create(phone_number=WHATS, name='Wanny')
    for i in range(3):
        UnifiedUserActivity.objects.create(user=whats, activity_type='whatsapp_message', description=f'msg {i}')
    UserAddress.objects.create(unified_user=whats, tenant=loja, street='QUADRA 501 SUL AVENIDA NS 1',
                               number='9', city='Palmas', state='TO', zip_code='77016006')
    UserAddress.objects.create(unified_user=whats, tenant=loja, street='Avenida JK', number='100',
                               city='Palmas', state='TO')
    vazio = UnifiedUser.objects.create(phone_number='+' + WHATS, name='Wanny')
    return loja, site, whats, vazio


@pytest.mark.django_db
def test_simulacao_nao_grava(wanny):
    saida = StringIO()
    call_command('fundir_perfis_duplicados', stdout=saida)

    assert 'simulação' in saida.getvalue()
    assert UnifiedUser.objects.count() == 3


@pytest.mark.django_db
def test_fusao_fica_o_perfil_com_login_e_leva_tudo(wanny):
    loja, site, whats, vazio = wanny

    call_command('fundir_perfis_duplicados', '--aplicar', stdout=StringIO())

    assert list(UnifiedUser.objects.values_list('id', flat=True)) == [site.id]
    site.refresh_from_db()
    assert site.phone_number == SITE
    assert site.name == 'Wanny Tapajos'
    assert UnifiedUserActivity.objects.filter(user=site).count() == 3
    ruas = sorted(UserAddress.objects.filter(unified_user=site).values_list('street', flat=True))
    assert ruas == ['Avenida JK', 'Quadra 501 Sul Avenida NS 1']
    assert UserAddress.objects.get(unified_user=site, number='9').zip_code == '77016006'
    assert StoreCustomer.objects.get(store=loja).unified_user_id == site.id
