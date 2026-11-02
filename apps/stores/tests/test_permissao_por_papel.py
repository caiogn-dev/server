"""Quem acessa o quê na loja: UMA regra, por papel (dono, 26/10).

A pergunta "em quais lojas esta pessoa pode fazer X?" estava escrita à mão em
~15 lugares, cada um com owner|staff e sem a equipe: o colaborador entrava em
Pedidos e era barrado no Início, nas Automações, no Agente e na Nutrição.
Decisão do dono: por papel — o bot é de dono e gerente; operador e
visualizador não mexem nele.
"""
from pathlib import Path

import pytest
from django.contrib.auth import get_user_model

from apps.stores.models import Store, StoreTeamMember
from apps.stores.permissions import get_member_role, lojas_com_permissao

User = get_user_model()


@pytest.fixture
def pessoas(db):
    dono = User.objects.create_user(username='p-dono', password='x')
    loja = Store.objects.create(owner=dono, name='Loja Papel', slug='loja-papel', status='active')
    gente = {'dono': dono}
    for papel in ('manager', 'operator', 'viewer'):
        u = User.objects.create_user(username=f'p-{papel}', password='x')
        StoreTeamMember.objects.create(tenant=loja, user=u, role=papel, is_active=True)
        gente[papel] = u
    legado = User.objects.create_user(username='p-legado', password='x')
    loja.staff.add(legado)
    gente['legado'] = legado
    inativo = User.objects.create_user(username='p-inativo', password='x')
    StoreTeamMember.objects.create(tenant=loja, user=inativo, role='manager', is_active=False)
    gente['inativo'] = inativo
    gente['estranho'] = User.objects.create_user(username='p-estranho', password='x')
    return loja, gente


@pytest.mark.parametrize('acao,entram', [
    ('whatsapp', {'dono', 'manager', 'legado'}),
    ('reports', {'dono', 'manager', 'operator', 'viewer', 'legado'}),
    ('orders', {'dono', 'manager', 'operator', 'legado'}),
    ('catalog', {'dono', 'manager', 'legado'}),
])
def test_quem_entra_por_acao(pessoas, acao, entram):
    loja, gente = pessoas
    quem = {nome for nome, u in gente.items() if loja.id in set(lojas_com_permissao(u, acao))}
    assert quem == entram


def test_staff_legado_vale_como_gerente(pessoas):
    loja, gente = pessoas
    assert get_member_role(gente['legado'], loja) == 'manager'


def test_ninguem_monta_a_regra_a_mao():
    """Catraca: `__staff=` / `staff=user` à mão nas telas que agora usam a regra."""
    apps = Path(__file__).resolve().parents[2]
    arquivos = [
        'automation/api/views/unified_views.py',
        'automation/api/views/scheduled_message_views.py',
        'automation/api/views/auto_message_views.py',
        'automation/api/views/automation_log_views.py',
        'automation/api/views/customer_session_views.py',
        'automation/api/views/flow_views.py',
        'automation/api/views/company_profile_views.py',
        'agents/views.py',
        'core/dashboard_views.py',
        'nutrition/api/permissions.py',
    ]
    for rel in arquivos:
        texto = (apps / rel).read_text()
        assert 'staff=' not in texto and 'staff__' not in texto, rel
