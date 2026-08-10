"""
Quem recebe o dinheiro é decisão POR LOJA, explícita e visível.

A primeira versão disto foi uma allowlist de slugs no .env
(`PLATFORM_GATEWAY_STORE_SLUGS`). Errado por três motivos, todos sentidos na
prática no mesmo dia:

- lista escrita à mão: `agriao-comida-saudavel` existia e não estava nela, então
  nasceu com pagamento bloqueado sem ninguém saber;
- invisível: não aparece em lugar nenhum do painel, então o estado real da loja
  só era descoberto quando o pagamento falhava;
- e o default era pela negativa errada — o dono precisaria lembrar de editar um
  arquivo de ambiente toda vez que criasse uma loja sua.

Agora é `Store.usa_gateway_da_plataforma`. Default False: loja de cliente
precisa cadastrar a conta dela. As lojas do dono ficam True e continuam
recebendo na conta dele, com a contabilidade que já existe.
"""
import pytest
from django.test import override_settings

from apps.stores.models import StorePaymentGateway
from apps.stores.services.checkout_service import CheckoutService
from apps.stores.tests.factories import make_store


@pytest.fixture
def loja(db):
    return make_store()


@override_settings(MERCADO_PAGO_ACCESS_TOKEN='TOKEN-DA-PLATAFORMA')
def test_loja_do_dono_recebe_na_conta_da_plataforma(loja):
    loja.usa_gateway_da_plataforma = True
    loja.save(update_fields=['usa_gateway_da_plataforma'])

    creds = CheckoutService.get_payment_credentials(loja)

    assert creds['access_token'] == 'TOKEN-DA-PLATAFORMA'


@override_settings(MERCADO_PAGO_ACCESS_TOKEN='TOKEN-DA-PLATAFORMA')
def test_loja_de_cliente_nao_recebe_na_conta_da_plataforma(loja):
    """Default é False: dinheiro de terceiro não passa pela conta do dono."""
    assert loja.usa_gateway_da_plataforma is False

    assert CheckoutService.get_payment_credentials(loja) is None


@override_settings(MERCADO_PAGO_ACCESS_TOKEN='TOKEN-DA-PLATAFORMA')
def test_conta_propria_ganha_da_conta_da_plataforma(loja):
    """Cadastrou a conta dela, o dinheiro vai para ela — mesmo com a flag on."""
    loja.usa_gateway_da_plataforma = True
    loja.save(update_fields=['usa_gateway_da_plataforma'])
    StorePaymentGateway.objects.create(
        store=loja, name='MP', gateway_type=StorePaymentGateway.GatewayType.MERCADOPAGO,
        access_token='TOKEN-DA-LOJA', is_enabled=True,
    )

    creds = CheckoutService.get_payment_credentials(loja)

    assert creds['access_token'] == 'TOKEN-DA-LOJA'


@override_settings(
    MERCADO_PAGO_ACCESS_TOKEN='TOKEN-DA-PLATAFORMA',
    PLATFORM_GATEWAY_STORE_SLUGS=[],
)
def test_nao_depende_mais_da_lista_de_slugs(loja):
    """A flag manda sozinha; a lista do .env vira só rede de segurança."""
    loja.usa_gateway_da_plataforma = True
    loja.save(update_fields=['usa_gateway_da_plataforma'])

    assert CheckoutService.get_payment_credentials(loja) is not None


@override_settings(MERCADO_PAGO_ACCESS_TOKEN='')
def test_sem_token_da_plataforma_nao_inventa_credencial(loja):
    loja.usa_gateway_da_plataforma = True
    loja.save(update_fields=['usa_gateway_da_plataforma'])

    assert CheckoutService.get_payment_credentials(loja) is None
