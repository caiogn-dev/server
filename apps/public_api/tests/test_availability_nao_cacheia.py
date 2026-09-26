"""Loja aberta/fechada é a resposta de UM instante: nunca pode ir para cache.

Incidente de 26/09 (sábado): o lojista abriu o sábado no painel às 10:43 e o
cardápio seguiu dizendo "fechado". O banco estava certo e a origem respondia
`is_open: true` — mas o endpoint não mandava `Cache-Control` nenhum, e a regra
"cache everything" do Cloudflare (set09) guardou o JSON na borda pelo TTL
padrão (horas), com `cf-cache-status: HIT`. "Não cachear" precisa ser dito
explicitamente; silêncio virou "cacheie à vontade".
"""
from datetime import datetime, timezone as dt_tz
from unittest import mock

from django.test import TestCase
from rest_framework.test import APIClient

from apps.core.models import User
from apps.stores.models import Store


class AvailabilityNaoCacheiaTest(TestCase):
    def setUp(self):
        owner = User.objects.create_user(
            username='pub-avail', email='pub-avail@example.com', password='x'
        )
        self.store = Store.objects.create(
            owner=owner, name='Aberta', slug='aberta', status='active',
            whatsapp_number='63999990000', address='Rua X, 1', city='Palmas',
            state='TO', plan='free',
            operating_hours={
                'friday': {'open': '08:00', 'close': '17:00', 'is_open': True},
                'saturday': {'open': '08:00', 'close': '17:00', 'is_open': True},
            },
        )
        self.url = '/api/v1/public/aberta/availability/'

    def test_manda_no_store_para_borda_e_navegador(self):
        r = APIClient().get(self.url)
        self.assertEqual(r.status_code, 200)
        cc = r['Cache-Control']
        self.assertIn('no-store', cc)
        self.assertNotIn('s-maxage', cc)

    def test_dia_de_hoje_segue_o_fuso_da_loja_nao_o_utc(self):
        # Sexta 20:30 em Brasília = sábado 23:30 UTC. `today` tem que ser sexta,
        # senão o cardápio mostra o horário de amanhã (mesmo bug do bot em set16).
        sabado_utc = datetime(2026, 9, 26, 23, 30, tzinfo=dt_tz.utc)
        with mock.patch('django.utils.timezone.now', return_value=sabado_utc):
            r = APIClient().get(self.url)
        self.assertEqual(r.data['today'], 'saturday')
        # e às 23:30 UTC de sábado (20:30 local) a loja das 8-17 já fechou
        self.assertFalse(r.data['is_open'])

    def test_today_vinte_e_uma_horas_brasilia_ainda_e_o_mesmo_dia(self):
        # Sexta 21:30 local = sábado 00:30 UTC → `today` deve ser 'friday'.
        madrugada_utc = datetime(2026, 9, 26, 0, 30, tzinfo=dt_tz.utc)
        with mock.patch('django.utils.timezone.now', return_value=madrugada_utc):
            r = APIClient().get(self.url)
        self.assertEqual(r.data['today'], 'friday')
