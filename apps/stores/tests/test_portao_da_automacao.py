"""O painel só pode abrir o menu de Automação quando a loja ATENDE.

O hook `useAutomationEnabled` decidia por
`whatsapp_number || integrations_count > 0`. Os dois lados mentem:

- `whatsapp_number` é texto que o dono digita — foi o mesmo engano que deixou
  4 de 6 lojas com o checklist verde e nenhuma WABA (22/09).
- `integrations_count` conta QUALQUER integração ativa. Loja que conectou
  Mercado Pago e mais nada tem contagem 1 e abria as dez telas de automação
  como se o WhatsApp estivesse de pé.

A resposta honesta já existe no checklist. Este teste exige que a loja a
publique — uma fonte só, para as duas telas nunca divergirem.
"""
import pytest
from apps.stores.api.serializers import StoreSerializer
from apps.stores.tests.factories import make_store
from apps.stores.services.onboarding_checklist import whatsapp_conectado


@pytest.fixture
def loja(db):
    return make_store(name='Cê Saladas')


@pytest.mark.django_db
class TestOPortaoDizAVerdade:
    def test_numero_digitado_nao_abre_o_portao(self, loja):
        loja.whatsapp_number = '5563999999999'
        loja.save(update_fields=['whatsapp_number'])
        assert StoreSerializer(loja).data['whatsapp_conectado'] is False

    def test_integracao_de_pagamento_nao_abre_o_portao(self, loja):
        from apps.stores.models import StoreIntegration
        StoreIntegration.objects.create(
            store=loja,
            integration_type=StoreIntegration.IntegrationType.MERCADOPAGO,
            status=StoreIntegration.IntegrationStatus.ACTIVE,
            is_active=True,
        )
        assert StoreSerializer(loja).data['whatsapp_conectado'] is False

    def test_a_loja_e_o_checklist_respondem_a_mesma_coisa(self, loja):
        assert (StoreSerializer(loja).data['whatsapp_conectado']
                == whatsapp_conectado(loja))
