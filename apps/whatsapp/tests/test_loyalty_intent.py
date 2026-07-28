from django.test import TestCase

from apps.whatsapp.intents.detector import IntentDetector, IntentType


class LoyaltyIntentDetectionTest(TestCase):
    def test_frases_de_fidelidade_detectadas(self):
        det = IntentDetector()
        for frase in ('quantos pontos eu tenho?', 'meu cartão fidelidade',
                      'quando ganho salada grátis', 'fidelidade'):
            intent = det.detect_regex(frase)
            assert intent == IntentType.LOYALTY_STATUS, f'{frase!r} -> {intent}'
