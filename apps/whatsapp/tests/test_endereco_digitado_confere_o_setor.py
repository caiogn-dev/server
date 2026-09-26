"""O bot geocodifica a consulta normalizada e recusa resultado de outro setor.

Ver `apps/stores/tests/test_endereco_de_palmas_para_geocodificar.py` pela
história (25/09: 307 Norte virou Plano Diretor Sul, 14,1 km).
"""
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.automation.models import CompanyProfile
from apps.conversations.models import Conversation
from apps.stores.models import Store
from apps.whatsapp.intents.handlers.interactive import InteractiveReplyHandler
from apps.whatsapp.models import WhatsAppAccount

User = get_user_model()
TEXTO = 'Na 307 norte Al 19 lote 53 sala 03'
GEO_SUL = {'lat': -10.270231, 'lng': -48.3454664,
           'formatted_address': 'Alameda 19, 53 - 03 - Plano Diretor Sul, Palmas - TO, Brasil', 'address': {}}
GEO_NORTE = {'lat': -10.165818, 'lng': -48.351327,
             'formatted_address': 'Q. 307 Norte Alameda 19, 53 - Arno, Palmas - TO, Brasil', 'address': {}}


class EnderecoDigitadoTest(TestCase):
    def setUp(self):
        owner = User.objects.create_user(username='dona-ce-end', password='x')
        self.store = Store.objects.create(
            billing_exempt=True, name='Cê Saladas', slug='ce-saladas-end', owner=owner, city='Palmas',
        )
        self.account = WhatsAppAccount.objects.create(name='CeEnd', phone_number_id='PHEND', waba_id='WEND')
        self.store.whatsapp_account = self.account
        self.store.save(update_fields=['whatsapp_account'])
        self.profile = CompanyProfile.objects.get(store=self.store)
        self.profile.account = self.account
        CompanyProfile.objects.filter(account=self.account).exclude(pk=self.profile.pk).delete()
        self.profile.save()
        self.conversation = Conversation.objects.create(account=self.account, phone_number='5563981545075')
        self.handler = InteractiveReplyHandler(self.account, self.conversation, self.profile)

    @staticmethod
    def _texto(resultado):
        if resultado.use_interactive:
            return (resultado.interactive_data or {}).get('body') or ''
        return resultado.response_text or ''

    def test_manda_ao_google_a_consulta_com_a_quadra(self):
        with patch('apps.stores.services.geo.geo_service.geocode', return_value=GEO_NORTE) as geocode, \
                patch.object(InteractiveReplyHandler, '_process_location_and_ask_payment', autospec=True) as seguir:
            self.handler._handle_address_input(TEXTO)
        self.assertEqual(geocode.call_args.args[0], 'Quadra 307 Norte, Alameda 19, 53, Palmas - TO')
        seguir.assert_called_once()
        self.assertAlmostEqual(seguir.call_args.kwargs['lat'], GEO_NORTE['lat'])

    def test_resultado_de_outro_setor_nao_e_aceito(self):
        with patch('apps.stores.services.geo.geo_service.geocode', return_value=GEO_SUL), \
                patch.object(InteractiveReplyHandler, '_process_location_and_ask_payment', autospec=True) as seguir:
            resultado = self.handler._handle_address_input(TEXTO)
        seguir.assert_not_called()
        texto = self._texto(resultado)
        self.assertIn('307 Norte', texto)
        self.assertIn('localização', texto.lower())
