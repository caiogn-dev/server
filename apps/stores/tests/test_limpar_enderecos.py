"""Faxina do caderno de endereços: simula por padrão, aplica com cópia."""
import json
from io import StringIO

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command

from apps.stores.models import Store, StoreCustomer, StoreCustomerAddress

User = get_user_model()
BASE = 'Quadra 501 Sul Avenida NS 1'
CAUDA = ', 9, Recepção da ortolife , espaço life - Centro, Palmas, TO'


@pytest.fixture
def cliente(db):
    dono = User.objects.create_user(username='dono_faxina', password='x')
    loja = Store.objects.create(owner=dono, name='Loja Faxina', slug='loja-faxina')
    pessoa = User.objects.create_user(username='flavia_faxina', password='x')
    c = StoreCustomer.objects.create(store=loja, user=pessoa)
    comum = dict(customer=c, number='9', complement='Recepção da ortolife , espaço life ',
                 neighborhood='Centro', city='Palmas', state='TO')
    # Vazio primeiro: o model deixa um padrão só, e o último salvo como padrão
    # é o que fica — igual à ordem em que isso aconteceu em produção.
    StoreCustomerAddress.objects.create(customer=c, street='', number='', is_default=True)
    StoreCustomerAddress.objects.create(street=BASE, zip_code='77016006', **comum)
    StoreCustomerAddress.objects.create(street=BASE + CAUDA, **comum)
    StoreCustomerAddress.objects.create(street=BASE + CAUDA * 2, is_default=True, **comum)
    StoreCustomerAddress.objects.create(customer=c, street='Quadra 401 Sul Avenida JK', number='S/N',
                                        complement='Medical Center 11 andar')
    return c


@pytest.mark.django_db
def test_simulacao_nao_grava(cliente):
    saida = StringIO()
    call_command('limpar_enderecos', stdout=saida)

    assert 'simulação' in saida.getvalue()
    assert StoreCustomerAddress.objects.filter(customer=cliente).count() == 5


@pytest.mark.django_db
def test_aplicar_deixa_um_por_lugar_e_um_padrao(cliente, tmp_path):
    copia = tmp_path / 'antes.json'
    call_command('limpar_enderecos', '--aplicar', '--backup', str(copia), stdout=StringIO())

    enderecos = list(StoreCustomerAddress.objects.filter(customer=cliente))
    assert sorted(e.street for e in enderecos) == ['Quadra 401 Sul Avenida JK', BASE]
    assert sum(e.is_default for e in enderecos) == 1
    ortolife = next(e for e in enderecos if e.street == BASE)
    assert ortolife.is_default
    assert ortolife.zip_code == '77016006'  # completado pelo que saiu
    assert len(json.loads(copia.read_text())) >= 3
