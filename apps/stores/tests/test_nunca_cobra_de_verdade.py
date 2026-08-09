"""A suíte não pode gastar dinheiro.

Em 08/ago/2026 seis cobranças PIX reais de R$ 179 apareceram na conta Mercado
Pago da empresa, uma por execução da suíte. O harness roda com
`--env-file .env` — o de PRODUÇÃO —, então `BILLING_PIX_ENABLED=true` valia
dentro dos testes, e `test_active_untouched` chamava
`enforce_subscription_lifecycle()` sem mockar o SDK.

O rastro no extrato era `s4@cardapidex.com.br`: o padrão
`{slug}@cardapidex.com.br` que o serviço usa quando a loja não tem email, com
`s4` sendo o slug de uma loja de TESTE.

É a terceira vez que o `.env` de produção vaza para a suíte: primeiro o banco
(07/ago), depois o cache Redis (08/ago), agora as credenciais de pagamento.
Este arquivo é a catraca da terceira.
"""
import pytest
from django.test import override_settings

from apps.stores.services import subscription_service


def test_cobranca_pix_desligada_por_padrao_nos_testes():
    """A flag de produção não pode valer aqui.

    Sem isto, qualquer teste que exercite o ciclo de assinatura de uma loja com
    vencimento próximo emite cobrança de verdade.
    """
    from django.conf import settings

    assert getattr(settings, 'BILLING_PIX_ENABLED', False) is False


def test_credenciais_do_mercadopago_sao_falsas_nos_testes():
    from django.conf import settings

    token = getattr(settings, 'MERCADOPAGO_ACCESS_TOKEN', '') or ''
    assert 'FALSO' in token.upper() or not token, (
        'O token do Mercado Pago nos testes parece real — uma chamada que '
        'escape dos mocks mexeria na conta da empresa.'
    )


def test_chamar_o_sdk_sem_mock_estoura_em_vez_de_cobrar():
    """A trava do conftest pega qualquer caminho que escape de um mock.

    Desligar a flag resolve o caso conhecido; isto resolve a classe.
    """
    with pytest.raises(AssertionError, match='Mercado Pago DE VERDADE'):
        subscription_service._sdk()


@pytest.mark.django_db
@override_settings(BILLING_PIX_ENABLED=True, BILLING_ENFORCEMENT_ENABLED=True)
def test_o_cenario_exato_que_gerou_as_cobrancas_agora_falha_seguro():
    """Reprodução do `test_active_untouched`: loja com trial vencido e
    assinatura ativa, rodando o ciclo com a cobrança LIGADA.

    Antes isso emitia PIX real. Agora a trava impede a chamada, e a task
    engole a exceção no `except` dela — o teste passa sem tocar na conta.
    """
    from datetime import timedelta

    from django.contrib.auth.models import User
    from django.utils import timezone

    from apps.stores.models import Store, StoreSubscription, StorePayment
    from apps.stores.tasks import enforce_subscription_lifecycle

    dono = User.objects.create_user(username='owner_s4_regressao', password='x')
    loja = Store.objects.create(
        name='s4', slug='s4-regressao', owner=dono,
        trial_ends_at=timezone.now() - timedelta(days=30),
    )
    StoreSubscription.objects.create(store=loja, status='active')

    enforce_subscription_lifecycle()

    # Nenhuma fatura criada — nem local, nem no Mercado Pago.
    assert not StorePayment.objects.filter(store=loja).exists()
