from django.test import TestCase

from apps.stores import billing


class BioBillingGatesTest(TestCase):
    def test_bio_gates_per_plan(self):
        for feature in ('bio_custom_links', 'bio_analytics'):
            self.assertFalse(billing.plan_allows('free', feature))
            self.assertTrue(billing.plan_allows('pro', feature))
            self.assertTrue(billing.plan_allows('premium', feature))
        # "Loja" (starter) leva o link na bio, mas as métricas dele ficam no
        # plano com WhatsApp — é lá que o BI mora.
        self.assertTrue(billing.plan_allows('starter', 'bio_custom_links'))
        self.assertFalse(billing.plan_allows('starter', 'bio_analytics'))
