"""Vincular o parceiro ao cupom pela TELA, não pelo shell de produção.

O campo `metadata['owner_phone']` existia desde a construção do cashback e só
era alcançável pelo shell — que é exatamente onde se perde dinheiro sem
rastro: ninguém sabe quem vinculou, quando, nem com que taxa.

DOIS CAMPOS NOMEADOS, e não `metadata` cru. Abrir o JSON inteiro para
escrita deixaria o painel gravar qualquer chave no cupom, inclusive as que
outras partes do sistema leem. Aqui a API aceita exatamente o que faz sentido
pedir: o telefone do parceiro e a taxa dele.

O telefone é normalizado na entrada porque o crédito casa por STRING lá na
frente. "(63) 99990-0011" digitado no painel e "5563999900011" gravado pelo
checkout são a mesma pessoa e não casariam — o parceiro divulgaria o cupom o
mês inteiro e não receberia nada, sem erro nenhum em lugar algum.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.stores.models import Store, StoreCoupon

User = get_user_model()


class CupomDeParceiroNaApiTest(TestCase):
    def setUp(self):
        self.dono = User.objects.create_user(username='dona-api-parceiro', password='x')
        self.store = Store.objects.create(
            billing_exempt=True, name='Cê Saladas', slug='ce-api-parceiro', owner=self.dono,
            store_type='food', status='active', metadata={'cashback_enabled': True},
        )
        self.client = APIClient()
        self.client.force_authenticate(self.dono)
        self.url = '/api/v1/stores/coupons/'

    def _payload(self, **extra):
        base = {
            'store': str(self.store.id),
            'code': 'ACADEMIAFIT',
            'description': 'Parceria com a academia',
            'discount_type': 'percentage',
            'discount_value': '10',
            'valid_from': timezone.now().date().isoformat(),
            'valid_until': (timezone.now() + timezone.timedelta(days=365)).date().isoformat(),
            'is_active': True,
        }
        base.update(extra)
        return base

    def _criar(self, **extra):
        return self.client.post(self.url, self._payload(**extra), format='json')

    def test_cria_cupom_vinculado_a_um_parceiro(self):
        r = self._criar(parceiro_phone='5563999900011', parceiro_percent='3')

        self.assertIn(r.status_code, (200, 201), r.data)
        cupom = StoreCoupon.objects.get(store=self.store, code='ACADEMIAFIT')
        self.assertEqual(cupom.metadata.get('owner_phone'), '5563999900011')
        self.assertEqual(cupom.metadata.get('owner_percent'), '3')

    def test_normaliza_o_telefone_digitado_no_painel(self):
        """O crédito casa por string: formato diferente = parceiro sem receber."""
        self._criar(parceiro_phone='(63) 99990-0011', parceiro_percent='3')

        cupom = StoreCoupon.objects.get(store=self.store, code='ACADEMIAFIT')
        self.assertEqual(cupom.metadata.get('owner_phone'), '5563999900011')

    def test_a_tela_le_de_volta_o_que_gravou(self):
        """Sem isto o dono reabre o cupom e o campo aparece vazio."""
        self._criar(parceiro_phone='5563999900011', parceiro_percent='3')
        cupom = StoreCoupon.objects.get(store=self.store, code='ACADEMIAFIT')

        r = self.client.get(f'{self.url}{cupom.id}/')

        self.assertEqual(r.data['parceiro_phone'], '5563999900011')
        self.assertEqual(r.data['parceiro_percent'], '3')

    def test_cupom_comum_nao_ganha_parceiro(self):
        self._criar(code='PROMO10')

        cupom = StoreCoupon.objects.get(store=self.store, code='PROMO10')
        self.assertFalse((cupom.metadata or {}).get('owner_phone'))

    def test_desvincular_o_parceiro(self):
        """Parceria acaba. Mandar vazio tem que APAGAR, não ser ignorado."""
        self._criar(parceiro_phone='5563999900011', parceiro_percent='3')
        cupom = StoreCoupon.objects.get(store=self.store, code='ACADEMIAFIT')

        self.client.patch(
            f'{self.url}{cupom.id}/', {'parceiro_phone': ''}, format='json',
        )

        cupom.refresh_from_db()
        self.assertFalse(cupom.metadata.get('owner_phone'))

    def test_percentual_fora_da_faixa_e_recusado(self):
        """120% de comissão é a loja pagando para vender."""
        r = self._criar(parceiro_phone='5563999900011', parceiro_percent='120')

        self.assertEqual(r.status_code, 400, r.data)

    def test_telefone_curto_e_recusado(self):
        """Telefone incompleto vira parceiro que nunca recebe — falha muda."""
        r = self._criar(parceiro_phone='6399', parceiro_percent='3')

        self.assertEqual(r.status_code, 400, r.data)

    def test_editar_o_cupom_nao_apaga_o_resto_do_metadata(self):
        """`metadata` é compartilhado. Sobrescrever o dicionário perde chave."""
        self._criar(parceiro_phone='5563999900011', parceiro_percent='3')
        cupom = StoreCoupon.objects.get(store=self.store, code='ACADEMIAFIT')
        cupom.metadata = {**cupom.metadata, 'origem': 'importacao-2025'}
        cupom.save(update_fields=['metadata'])

        self.client.patch(
            f'{self.url}{cupom.id}/', {'parceiro_percent': '5'}, format='json',
        )

        cupom.refresh_from_db()
        self.assertEqual(cupom.metadata.get('origem'), 'importacao-2025')
        self.assertEqual(cupom.metadata.get('owner_percent'), '5')
        self.assertEqual(cupom.metadata.get('owner_phone'), '5563999900011')

    def test_loja_de_outro_dono_e_recusada(self):
        intruso = User.objects.create_user(username='intruso-cupom', password='x')
        self.client.force_authenticate(intruso)

        r = self._criar(parceiro_phone='5563999900011', parceiro_percent='3')

        # A loja nem existe para ele (o queryset é escopado por dono), então a
        # recusa vem como 400 "Loja não encontrada" em vez de 403. Qualquer uma
        # serve; o que importa é que o cupom NÃO nasce — cupom de parceiro é
        # dinheiro saindo da loja de outra pessoa.
        self.assertGreaterEqual(r.status_code, 400)
        self.assertFalse(StoreCoupon.objects.filter(code='ACADEMIAFIT').exists())
